"""Worker side of publishing: the only place a user's GitHub token is decrypted."""
from backend import db
from backend.contracts.models import RunStatus
from backend.github import reader
from backend.publisher import tokens
from backend.publisher.publisher import GitHubWriter, PublishRefused, publish


def run_publish(job: dict) -> None:
    c, rid = db.connect(), job["run_id"]
    v = db.get_run(c, rid)
    emit = lambda **p: db.emit(c, rid, "publish.finished", "publish", v.revision, **p)
    aid = db.get_kv(c, f"publish_account:{rid}")
    row = c.execute("SELECT token_enc FROM accounts WHERE id=?", (int(aid),)).fetchone() if aid else None
    token = tokens.decrypt(row[0]) if row and row[0] else None
    try:
        if not token:
            raise PublishRefused("AUTH_REQUIRED", "Your GitHub connection expired. Connect GitHub again.")
        default_branch = reader.check_issue(v.issue.html_url).default_branch or "main"
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
        emit(status="failed", pr_url=None, compare_url=None, error_code="GITHUB_UNAVAILABLE",
             message=f"Nothing was published: {type(e).__name__}. Try again.")
    finally:
        token = None
        with db.tx(c):
            c.execute("UPDATE jobs SET state='succeeded', lease_owner=NULL WHERE id=?", (job["id"],))
