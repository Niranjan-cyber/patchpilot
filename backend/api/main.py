"""FastAPI app: serves the SPA and the run API (contracts §4). RUN_MODE=fixture serves fixtures/runs."""
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.contracts.models import CONTRACTS_VERSION, Event, RunView

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


@app.get("/healthz")
def healthz():
    # shortcut: worker/llm_budget report false/unset until B04/B06 wire them.
    return {"db": False, "worker": False, "docker": shutil.which("docker") is not None,
            "llm_budget": "unset", "run_mode": RUN_MODE, "contracts": CONTRACTS_VERSION}


@app.get("/api/runs/{run_id}", response_model=RunView)
def get_run(run_id: str):
    return RunView.model_validate_json((_fixture(run_id) / "state.json").read_text())


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: str, after: int = 0):
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
