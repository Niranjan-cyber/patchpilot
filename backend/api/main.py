"""FastAPI app: serves the SPA and the run API (contracts §4). RUN_MODE=fixture serves fixtures/runs."""
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import uuid

from pydantic import BaseModel

from backend import db
from backend.api import session
from backend.config import limits, llm_budget_set
from backend.contracts.models import CONTRACTS_VERSION, Event, PublishBlocker, RunView
from backend.github.reader import GitHubError, IssueCheck, check_issue

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "runs"
DIST = ROOT / "web" / "dist"
RUN_MODE = os.getenv("RUN_MODE", "fixture")

app = FastAPI(title="PatchPilot", version=CONTRACTS_VERSION)


class ApiErr(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        self.status, self.body = status, {"code": code, "message": message, "retry_after": retry_after}


@app.exception_handler(ApiErr)
async def _api_err(_: Request, e: ApiErr):
    return JSONResponse(e.body, status_code=e.status)


@app.middleware("http")
async def _headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Robots-Tag"] = "noindex"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def _fixture(run_id: str) -> Path:
    d = FIXTURES / run_id
    if RUN_MODE != "fixture" or not run_id.replace("_", "").isalnum() or not d.is_dir():
        raise ApiErr(404, "NOT_FOUND", "This run isn't available.")
    return d


def _is_real(run_id: str) -> bool:
    try:
        return str(uuid.UUID(run_id)) == run_id
    except ValueError:
        return False


def _own(request: Request, run_id: str) -> None:
    """Enumeration-safe: "doesn't exist" and "not yours" are the same 404 (contracts §4)."""
    if not db.owns(db.connect(), run_id, session.current(request)):
        raise ApiErr(404, "NOT_FOUND", "This run isn't available. Sign in with the GitHub account that owns it.")


class CheckBody(BaseModel):
    url: str


def _check(url: str) -> IssueCheck:
    try:
        return check_issue(url)
    except GitHubError as e:
        raise ApiErr(422 if e.code in ("INVALID_URL", "NOT_AN_ISSUE") else 404 if e.code == "PRIVATE_REPO" else 503,
                     e.code, str(e), e.retry_after)


@app.post("/api/issues/check", response_model=IssueCheck)
def issues_check(body: CheckBody):
    return _check(body.url)


class NewRun(BaseModel):
    issue_url: str
    continue_despite: list[str] = []


@app.post("/api/runs", response_model=RunView, status_code=201)
def create_run(body: NewRun, request: Request, response: Response):
    sid = session.ensure(request, response)
    c, lim = db.connect(), limits()
    today, active = db.owner_counts(c, sid, None)
    if active >= lim["active_runs_per_owner"]:
        raise ApiErr(429, "LIMIT_ACTIVE_RUN", "You already have a run going. Open it from My runs, or stop it first.")
    if today >= lim["session_runs_per_day"]:
        raise ApiErr(429, "LIMIT_SESSION_DAILY", f"You've used today's {lim['session_runs_per_day']} free runs. "
                     "Sign in with GitHub for more, or come back tomorrow (resets 00:00 UTC).")
    chk = _check(body.issue_url)   # G0 (contracts §1.1)
    if chk.unsupported:
        raise ApiErr(422, "UNSUPPORTED_REPO", {"not_python": "PatchPilot can only run Python projects today.",
                     "no_tests": "We couldn't find tests in this repository, so we can't verify a fix."}[chk.unsupported])
    missing = [w for w in chk.warnings if w not in body.continue_despite]
    if missing:
        raise ApiErr(409, "ELIGIBILITY_WARNING", "This issue has warnings you need to accept first: " + ", ".join(missing))
    v = db.create_run(c, chk.issue, base_sha=chk.base_sha or "pending", owner_session_hash=sid)
    if chk.policy.ai_policy == "forbidden":
        v.policy = chk.policy
        v.publish_blockers.append(PublishBlocker.REPO_FORBIDS_AI)
        db.save_run(db.connect(), v)
    return v


@app.post("/api/runs/{run_id}/stop", response_model=RunView)
def stop_run(run_id: str, request: Request):
    c = db.connect()
    if not _is_real(run_id):
        raise ApiErr(404, "NOT_FOUND", "This run isn't available.")
    _own(request, run_id)
    if not db.request_stop(c, run_id):
        raise ApiErr(404, "NOT_FOUND", "This run isn't available or has already finished.")
    v = db.get_run(c, run_id)
    if v.status.value == "queued":   # never leased: finish it here
        from backend.contracts.models import EndReason, Outcome, PublishBlocker, RunStatus, readiness
        v.status, v.outcome, v.end_reason = RunStatus.FINISHED, Outcome.STOPPED, EndReason.USER_STOPPED
        v.readiness, v.publish_blockers = readiness(Outcome.STOPPED), [PublishBlocker.OUTCOME_NOT_VERIFIED, PublishBlocker.RUN_STOPPED]
        with db.tx(c):
            c.execute("UPDATE jobs SET state='succeeded' WHERE run_id=? AND state='queued'", (run_id,))
        db.save_run(c, v)
        db.emit(c, run_id, "analysis.finished", None, v.revision, outcome="STOPPED", end_reason="user_stopped",
                readiness=v.readiness, publish_blockers=[b.value for b in v.publish_blockers])
    return v


@app.get("/healthz")
def healthz():
    beat = db.get_kv(db.connect(), "worker_heartbeat")
    alive = beat is not None and (db.now() - db.datetime.fromisoformat(beat)).total_seconds() < 30
    return {"db": True, "worker": alive,
            "docker": shutil.which("docker") is not None, "llm_budget": "set" if llm_budget_set() else "unset",
            "run_mode": RUN_MODE, "contracts": CONTRACTS_VERSION}


@app.get("/api/runs/{run_id}", response_model=RunView)
def get_run(run_id: str, request: Request):
    if _is_real(run_id):
        _own(request, run_id)
        v = db.get_run(db.connect(), run_id)
        if not v:
            raise ApiErr(404, "NOT_FOUND", "This run isn't available.")
        return v
    return RunView.model_validate_json((_fixture(run_id) / "state.json").read_text())


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: str, request: Request, after: int = 0):
    if _is_real(run_id):
        _own(request, run_id)
        evs = db.events_after(db.connect(), run_id, after)
        return {"events": [e.model_dump(mode="json") for e in evs], "next_after": evs[-1].seq if evs else after}
    lines = (_fixture(run_id) / "events.jsonl").read_text().splitlines()
    evs = [e for e in (Event.model_validate_json(l) for l in lines) if e.seq > after]
    return {"events": [e.model_dump(mode="json") for e in evs], "next_after": evs[-1].seq if evs else after}


@app.get("/api/me/runs")
def my_runs(request: Request):
    sid = session.current(request)
    if not sid:
        return []
    return [{"run_id": v.run_id, "title": v.issue.title, "repo": v.issue.repo, "number": v.issue.number,
             "status": v.status, "outcome": v.outcome, "readiness": v.readiness, "created_at": v.created_at,
             "pr_url": v.pr.url if v.pr else None} for v in db.list_runs(db.connect(), sid, None)]


@app.delete("/api/runs/{run_id}/access", status_code=204)
def forget_run(run_id: str, request: Request):
    sid = session.current(request)
    if not (_is_real(run_id) and sid and db.forget(db.connect(), run_id, sid)):
        raise ApiErr(404, "NOT_FOUND", "This run isn't available.")
    return Response(status_code=204)


from backend.api.approval import router as _approval  # noqa: E402  (needs ApiErr/_own defined above)
app.include_router(_approval)


@app.get("/api/fixtures")
def list_fixtures():
    return sorted(p.name for p in FIXTURES.iterdir()) if RUN_MODE == "fixture" else []


if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise ApiErr(404, "NOT_FOUND", "Unknown API path.")
    index = DIST / "index.html"
    if not index.exists():
        raise ApiErr(503, "UI_NOT_BUILT", "Run `npm run build` in web/.")
    return FileResponse(index)
