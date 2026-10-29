"""B11: GitHub sign-in (OAuth app, scope public_repo) and the publish endpoint. Screens S-06 / S-07."""
import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

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
