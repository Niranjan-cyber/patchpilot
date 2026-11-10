"""Worker side of publishing: the only place a user's GitHub token is decrypted."""
from backend import db
from backend.contracts.models import RunStatus
from backend.github import reader
from backend.publisher import tokens
from backend.publisher.publisher import GitHubWriter, PublishRefused, ask, publish


def _allowed(c, rid: str, v) -> None:
    """#100: checked again here, for the account whose token is about to be used, before any GitHub call."""
    from backend.config import PUBLISH_LIMITED, may_publish
    aid = db.get_kv(c, f"publish_account:{rid}")
    row = c.execute("SELECT login FROM accounts WHERE id=?", (int(aid),)).fetchone() if aid else None
    if not may_publish(row[0] if row else None, v.issue.repo):
        raise PublishRefused("PUBLISH_BLOCKED", PUBLISH_LIMITED)


def _token(c, rid: str) -> str | None:
    aid = db.get_kv(c, f"publish_account:{rid}")
    row = c.execute("SELECT token_enc FROM accounts WHERE id=?", (int(aid),)).fetchone() if aid else None
    return tokens.decrypt(row[0]) if row and row[0] else None


SIGN_IN_AGAIN = "Your GitHub sign-in has expired or was revoked. Sign in with GitHub again, then try once more."


def _github_refused(e: Exception) -> str | None:
    """A message the user can act on when GitHub refused the token itself; None for other errors (live run e335ce16:
    a 401 on GET /user was shown as "HTTPStatusError. Try again", and trying again can never work)."""
    code = getattr(getattr(e, "response", None), "status_code", None)
    if code == 401:
        return SIGN_IN_AGAIN
    if code == 403:
        return "GitHub refused this with your sign-in (403). Check you granted PatchPilot access, then sign in again."
    return None


def run_ask(job: dict) -> None:
    """'Ask the maintainer first': post the user's comment on the issue. Result in kv ask:<run_id> for the UI."""
    import json
    c, rid = db.connect(), job["run_id"]
    v, token = db.get_run(c, rid), _token(c, rid)
    try:
        if not token:
            raise PublishRefused("AUTH_REQUIRED", "Your GitHub connection expired. Connect GitHub again.")
        _allowed(c, rid, v)
        out = {"url": ask(v, GitHubWriter(token), db.get_kv(c, f"ask_body:{rid}") or "")}
    except PublishRefused as e:
        out = {"error": str(e)}
    except Exception as e:   # nothing is claimed as posted
        out = {"error": _github_refused(e) or f"The comment wasn't posted: {type(e).__name__}. Try again."}
    finally:
        token = None
    with db.tx(c):
        db.put_kv(c, f"ask:{rid}", json.dumps(out))
        c.execute("UPDATE jobs SET state='succeeded', lease_owner=NULL WHERE id=?", (job["id"],))


def run_publish(job: dict) -> None:
    c, rid = db.connect(), job["run_id"]
    v = db.get_run(c, rid)
    emit = lambda **p: db.emit(c, rid, "publish.finished", "publish", v.revision, **p)
    token = _token(c, rid)
    try:
        if not token:
            raise PublishRefused("AUTH_REQUIRED", "Your GitHub connection expired. Connect GitHub again.")
        _allowed(c, rid, v)
        default_branch = reader.check_issue(v.issue.html_url, extract_model=False).default_branch or "main"
        db.emit(c, rid, "publish.progress", "publish", v.revision, stage="apply")
        res = publish(v, GitHubWriter(token), default_branch)
        v.pr, v.status = res.pr, RunStatus.PUBLISHED
        db.save_run(c, v)
        emit(status=res.status, pr_url=res.pr.url, compare_url=res.pr.compare_url, error_code=None)
    except PublishRefused as e:
        v.status = RunStatus.FINISHED if e.code == "UPSTREAM_CHANGED" else RunStatus.AWAITING_APPROVAL
        db.save_run(c, v)
        emit(status="failed", pr_url=None, compare_url=None, error_code=e.code, message=str(e))
    except Exception as e:   # GitHub/git errors: nothing half-published is claimed as done
        from backend.llm_gateway import redact   # operator log only (the user sees the generic line); git stderr may hold URLs
        err = getattr(e, "stderr", None)
        err = err.decode("utf-8", "replace") if isinstance(err, bytes) else (err or str(e))
        print(f"publish {rid[:8]} failed: {type(e).__name__} {list(getattr(e, 'cmd', []))[3:5]} {redact(err)[-600:]}", flush=True)
        v.status = RunStatus.AWAITING_APPROVAL
        db.save_run(c, v)
        why = _github_refused(e)
        emit(status="failed", pr_url=None, compare_url=None, error_code="AUTH_REQUIRED" if why else "GITHUB_UNAVAILABLE",
             message=f"Nothing was published. {why}" if why else f"Nothing was published: {type(e).__name__}. Try again.")
    finally:
        token = None
        with db.tx(c):
            c.execute("UPDATE jobs SET state='succeeded', lease_owner=NULL WHERE id=?", (job["id"],))
