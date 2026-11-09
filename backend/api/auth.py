"""B11: GitHub sign-in (OAuth app, scope public_repo) and the publish endpoint. Screens S-06 / S-07."""
import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from backend import db
from backend.api import session
from backend.contracts.models import PublishBlocker, RunStatus
from backend.publisher import oauth, tokens

router = APIRouter()
STATE = "pp_oauth"


def _err(status, code, msg):
    from backend.api.main import ApiErr
    return ApiErr(status, code, msg)


def _base(request: Request) -> str:
    return os.getenv("PUBLIC_URL", str(request.base_url)).rstrip("/")


def oauth_ready() -> bool:
    return bool(os.getenv("GITHUB_OAUTH_CLIENT_ID") and os.getenv("GITHUB_OAUTH_CLIENT_SECRET") and tokens.configured())


@router.get("/api/me")
def me(request: Request):
    a = session.account(request)
    return {"signed_in": a is not None, "login": a["login"] if a else None, "oauth_ready": oauth_ready()}


@router.get("/auth/github/start")
def start(request: Request, run: str = ""):
    if not oauth_ready():
        return RedirectResponse(f"/connect?run={run}&error=not_configured", 303)
    resp = RedirectResponse("", 303)
    session.ensure(request, resp)
    state = secrets.token_urlsafe(24)
    resp.headers["location"] = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": os.environ["GITHUB_OAUTH_CLIENT_ID"], "scope": "public_repo", "state": state,
        "redirect_uri": f"{_base(request)}/auth/github/callback", "allow_signup": "true"})
    resp.set_cookie(STATE, f"{state}:{run}", max_age=600, httponly=True, secure=True, samesite="lax", path="/auth")
    return resp


@router.get("/auth/github/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    saved, _, run = (request.cookies.get(STATE) or "").partition(":")
    back = f"/connect?run={run}"
    if error or not code:
        return RedirectResponse(back + "&error=cancelled", 303)
    if not saved or not secrets.compare_digest(saved, state):
        return RedirectResponse(back + "&error=state", 303)
    sid = session.current(request)
    if not sid:
        return RedirectResponse(back + "&error=session", 303)
    try:
        user, token_enc, scopes = oauth.exchange(code, f"{_base(request)}/auth/github/callback")
    except Exception:
        return RedirectResponse(back + "&error=github", 303)
    c = db.connect()
    with db.tx(c):
        c.execute("""INSERT INTO accounts(github_id,login,token_enc,scopes,created_at) VALUES(?,?,?,?,?)
                     ON CONFLICT(github_id) DO UPDATE SET login=excluded.login, token_enc=excluded.token_enc, scopes=excluded.scopes""",
                  (user["id"], user["login"], token_enc, scopes, db.now().isoformat()))
        aid = c.execute("SELECT id FROM accounts WHERE github_id=?", (user["id"],)).fetchone()[0]
        c.execute("UPDATE sessions SET account_id=? WHERE id_hash=?", (aid, sid))
        # Sign-in claims only this browser's UNCLAIMED runs, and claimed runs stop being reachable by the cookie alone,
        # so a second account signing in on a shared browser can't see the first account's runs (C review #1).
        c.execute("UPDATE runs SET owner_account_id=? WHERE owner_session_hash=? AND owner_account_id IS NULL", (aid, sid))
        c.execute("UPDATE runs SET owner_session_hash=NULL WHERE owner_session_hash=? AND owner_account_id IS NOT NULL", (sid,))
    resp = RedirectResponse(back + "&signed_in=1", 303)
    resp.delete_cookie(STATE, path="/auth")
    return resp


@router.post("/auth/logout", status_code=204)
def logout(request: Request):
    from fastapi import Response
    sid = session.current(request)
    if sid:
        c = db.connect()
        with db.tx(c):
            c.execute("UPDATE sessions SET revoked_at=? WHERE id_hash=?", (db.now().isoformat(), sid))
    r = Response(status_code=204); r.delete_cookie(session.COOKIE, path="/")
    return r


@router.post("/api/runs/{run_id}/publish")
def publish(run_id: str, request: Request):
    from backend.api.approval import _run
    v = _run(request, run_id)
    acct = session.account(request)
    if not acct:
        raise _err(401, "AUTH_REQUIRED", "Connect GitHub to publish. Until then you can download the diff and report.")
    if v.status not in (RunStatus.AWAITING_APPROVAL, RunStatus.PUBLISHED) or v.approval is None:
        raise _err(409, "APPROVAL_STALE", "Approve the current version of the change first.")
    if v.consent is None:   # v0.5 §2.2: enforced here and again by the publisher
        from backend.publisher.publisher import NO_CONSENT
        raise _err(409, "PUBLISH_BLOCKED", NO_CONSENT)
    blocked = [b for b in v.publish_blockers if b not in (PublishBlocker.NOT_SIGNED_IN,)]
    if blocked:
        raise _err(409, "PUBLISH_BLOCKED", "Publishing is blocked: " + ", ".join(b.value for b in blocked))
    c = db.connect()
    with db.tx(c):   # conditional transition: a double click can't enqueue two publish jobs (C review #8)
        if c.execute("UPDATE runs SET status='publishing' WHERE run_id=? AND status IN ('awaiting_approval','published')",
                     (run_id,)).rowcount != 1:
            raise _err(409, "ALREADY_PUBLISHING", "Publishing is already in progress.")
    v.status = RunStatus.PUBLISHING
    db.save_run(c, v)
    with db.tx(c):
        db.put_kv(c, f"publish_account:{run_id}", str(acct["id"]))
        c.execute("INSERT INTO jobs(run_id,kind,state,available_at) VALUES(?,?,?,?)", (run_id, "publish", "queued", db.now().isoformat()))
    db.emit(c, run_id, "publish.progress", "publish", v.revision, stage="queued")
    return {"status": "publishing"}


class AskBody(BaseModel):
    body: str = Field(min_length=20, max_length=2000)


@router.get("/api/runs/{run_id}/ask-maintainer")
def ask_state(run_id: str, request: Request):
    """'Ask the maintainer first' (human decision 2026-11-09): the default comment, and the posted link or error once done."""
    import json
    from backend.api.approval import _run
    from backend.publisher.publisher import ask_comment
    v, c = _run(request, run_id), db.connect()
    pending = c.execute("SELECT 1 FROM jobs WHERE run_id=? AND kind='ask' AND state IN ('queued','running')", (run_id,)).fetchone()
    return {"draft": ask_comment(v) if v.approval else None, "pending": bool(pending),
            **json.loads(db.get_kv(c, f"ask:{run_id}") or "{}")}


@router.post("/api/runs/{run_id}/ask-maintainer")
def ask_maintainer(run_id: str, body: AskBody, request: Request):
    import json
    from backend.api.approval import _run
    v = _run(request, run_id)
    acct = session.account(request)
    if not acct:
        raise _err(401, "AUTH_REQUIRED", "Connect GitHub to comment on the issue.")
    if v.status not in (RunStatus.AWAITING_APPROVAL, RunStatus.PUBLISHED) or v.approval is None or v.approval.revision != v.revision:
        raise _err(409, "APPROVAL_STALE", "Approve the current version of the change first.")
    blocked = [b for b in v.publish_blockers if b not in (PublishBlocker.NOT_SIGNED_IN, PublishBlocker.NO_MAINTAINER_CONSENT)]
    if blocked:
        raise _err(409, "PUBLISH_BLOCKED", "Publishing is blocked: " + ", ".join(b.value for b in blocked))
    c = db.connect()
    with db.tx(c):   # one comment per click: refuse while one is queued or running
        if c.execute("SELECT 1 FROM jobs WHERE run_id=? AND kind='ask' AND state IN ('queued','running')", (run_id,)).fetchone():
            raise _err(409, "ALREADY_ASKING", "The comment is already being posted.")
        if "url" in json.loads(db.get_kv(c, f"ask:{run_id}") or "{}"):   # one ask per run: never ping the maintainer twice
            raise _err(409, "ALREADY_ASKED", "You already asked on the issue. Wait for the maintainer's reply.")
        db.put_kv(c, f"publish_account:{run_id}", str(acct["id"]))
        db.put_kv(c, f"ask_body:{run_id}", body.body)
        c.execute("DELETE FROM kv WHERE key=?", (f"ask:{run_id}",))
        c.execute("INSERT INTO jobs(run_id,kind,state,available_at) VALUES(?,?,?,?)", (run_id, "ask", "queued", db.now().isoformat()))
    return {"status": "asking"}


class ConsentBody(BaseModel):
    attest_comment_url: str | None = Field(default=None, max_length=500)
    override_reason: str | None = Field(default=None, min_length=20, max_length=1000)


def _consent_state(v, request: Request) -> dict:
    import json
    from backend.github import consent, reader
    c = db.connect()
    asked = json.loads(db.get_kv(c, f"ask:{v.run_id}") or "{}").get("url")
    aid = db.get_kv(c, f"publish_account:{v.run_id}")
    poster = c.execute("SELECT login FROM accounts WHERE id=?", (int(aid),)).fetchone() if aid else None
    me = (poster or [None])[0] or (session.account(request) or {}).get("login")
    try:
        return consent.check(v.issue.repo, v.issue.number, asked_url=asked, me=me)
    except reader.GitHubError as e:   # unknown is never consent
        raise _err(503, "GITHUB_UNAVAILABLE", f"We couldn't read the issue to check for a maintainer's reply. {e}")


def _out(v, st: dict) -> dict:
    return {"consent": v.consent.model_dump(mode="json") if v.consent else None, "state": "recorded" if v.consent else st["state"],
            "replies": st.get("replies", []), "why": st.get("why")}


@router.get("/api/runs/{run_id}/consent")
def consent_state(run_id: str, request: Request):
    """v0.5 §2.2: what GitHub says now. Records nothing."""
    from backend.api.approval import _run
    v = _run(request, run_id)
    return _out(v, {"state": "recorded"} if v.consent else _consent_state(v, request))


@router.post("/api/runs/{run_id}/consent")
def record_consent(run_id: str, body: ConsentBody, request: Request):
    """v0.5 §2.2: {} records consent GitHub shows; {attest_comment_url} a maintainer reply the user confirms;
    {override_reason} the user's typed override (shown in the report, never in the PR body)."""
    from backend.api.approval import _run
    from backend.contracts.models import ConsentEvidence
    v = _run(request, run_id)
    if v.status not in (RunStatus.AWAITING_APPROVAL, RunStatus.PUBLISHED):
        raise _err(409, "APPROVAL_STALE", "This run isn't waiting to be published.")
    st = {"state": "recorded"}
    if body.override_reason:
        ev = ConsentEvidence(kind="user_override", override_reason=body.override_reason.strip(), recorded_at=db.now())
    else:
        st = _consent_state(v, request)
        if body.attest_comment_url:
            r = next((r for r in st["replies"] if r["url"] == body.attest_comment_url), None)
            if not r or r["declined"]:
                raise _err(409, "NOT_CONSENT", "That isn't a maintainer's reply to your question (or it declined). "
                                               "You can still publish with a typed reason.")
            ev = ConsentEvidence(kind="maintainer_reply", source_url=r["url"], author=r["author"], author_association=r["association"],
                                 quote=r["quote"], attested_by_user=True, recorded_at=db.now())
        else:
            ev = st.get("evidence")
    if ev:
        v.consent = ev
        v.publish_blockers = [b for b in v.publish_blockers if b != PublishBlocker.NO_MAINTAINER_CONSENT]
        db.save_run(db.connect(), v)
    return _out(v, st)
