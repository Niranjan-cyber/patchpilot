"""FastAPI app: serves the SPA and the run API (contracts §4). RUN_MODE=fixture serves fixtures/runs."""
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import re
import uuid

from pydantic import BaseModel

from backend import db
from backend.config import llm_budget_set
from backend.contracts.models import CONTRACTS_VERSION, Event, IssueSpec, RunView

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


ISSUE_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/issues/(\d+)/?$")


class NewRun(BaseModel):
    issue_url: str
    continue_despite: list[str] = []


@app.post("/api/runs", response_model=RunView, status_code=201)
def create_run(body: NewRun):
    m = ISSUE_URL.match(body.issue_url.strip())
    if not m:
        raise ApiErr(422, "INVALID_URL", "Paste a link to a GitHub issue, like https://github.com/owner/repo/issues/123.")
    owner, repo, num = m.groups()
    # shortcut: title/checks/base_sha come from the B03 issue reader (role C); B05 pins base_sha from the tarball.
    issue = IssueSpec(html_url=body.issue_url.strip(), repo=f"{owner}/{repo}", number=int(num), title=f"{owner}/{repo} #{num}")
    return db.create_run(db.connect(), issue, base_sha="pending")


@app.post("/api/runs/{run_id}/stop", response_model=RunView)
def stop_run(run_id: str):
    c = db.connect()
    if not _is_real(run_id) or not db.request_stop(c, run_id):
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
def get_run(run_id: str):
    if _is_real(run_id):
        v = db.get_run(db.connect(), run_id)
        if not v:
            raise ApiErr(404, "NOT_FOUND", "This run isn't available.")
        return v
    return RunView.model_validate_json((_fixture(run_id) / "state.json").read_text())


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: str, after: int = 0):
    if _is_real(run_id):
        evs = db.events_after(db.connect(), run_id, after)
        return {"events": [e.model_dump(mode="json") for e in evs], "next_after": evs[-1].seq if evs else after}
    lines = (_fixture(run_id) / "events.jsonl").read_text().splitlines()
    evs = [e for e in (Event.model_validate_json(l) for l in lines) if e.seq > after]
    return {"events": [e.model_dump(mode="json") for e in evs], "next_after": evs[-1].seq if evs else after}


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
