"""Build the static, read-only showcase of the UI (frontend only, e.g. for Vercel): no backend, recorded runs.

Builds web/ with VITE_SHOWCASE=1 into web/dist-showcase, then records every GET the screens need from a running local
API (sample runs + your real runs) into dist-showcase/showcase/... as JSON, plus report downloads. The SPA reads those
files instead of /api (web/src/api.ts). Recorded error answers keep the backend's own code and message.

Usage (API running locally, e.g. `uv run uvicorn backend.api.main:app --port 8014`):
    uv run python scripts/build_showcase.py --base http://localhost:8014 --token <pp_sid of the session owning --run> --run <real run id>
Then deploy the folder:  vercel deploy web/dist-showcase --prod
"""
import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "dist-showcase"
TRY_ISSUE = "https://github.com/Niranjan-cyber/tinycalc/issues/1"
TRY_REPO = "https://github.com/Niranjan-cyber/tinycalc"
slug = lambda s: re.sub(r"[^a-z0-9]+", "_", s, flags=re.I)   # same as web/src/api.ts


def save(path: str, r: httpx.Response) -> None:
    f = OUT / "showcase" / (path.lstrip("/") + ".json")
    f.parent.mkdir(parents=True, exist_ok=True)
    if r.status_code == 200:
        f.write_text(r.text, encoding="utf-8")
    else:   # keep the backend's own answer, e.g. EVAL_NOT_RUN, so the screen shows its designed state
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        f.write_text(json.dumps({"__error": {"code": body.get("code", "NOT_FOUND"), "message": body.get("message", "Not available.")}}), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8014")
    ap.add_argument("--token", help="pp_sid cookie of the session that owns --run")
    ap.add_argument("--run", help="a real run to feature (Try it, My runs, Start run)")
    ap.add_argument("--github-from", help="API to record the GitHub-backed answers from (issue check, explore, eval), e.g. the live Funnel URL")
    a = ap.parse_args()

    shutil.rmtree(OUT, ignore_errors=True)
    npm = shutil.which("npm") or "npm"
    subprocess.run([npm, "exec", "--", "vite", "build", "--outDir", "dist-showcase"], cwd=ROOT / "web", check=True,
                   env={**os.environ, "VITE_SHOWCASE": "1"})

    c = httpx.Client(base_url=a.base, timeout=60, cookies={"pp_sid": a.token} if a.token else None)
    fixtures = c.get("/api/fixtures").json()
    save("/api/fixtures", c.get("/api/fixtures"))
    for p in ("/api/me", "/api/me/runs", "/api/me/progress"):
        save(p, c.get(p))
    runs = fixtures + ([a.run] if a.run else [])
    for rid in runs:
        save(f"/api/runs/{rid}", c.get(f"/api/runs/{rid}"))
        save(f"/api/runs/{rid}/events", c.get(f"/api/runs/{rid}/events", params={"after": 0}))
        for sub in ("bisect", "pauses", "approval"):
            save(f"/api/runs/{rid}/{sub}", c.get(f"/api/runs/{rid}/{sub}"))
        for dl in ("report.md", "diff.patch"):   # plain links, so they live at the real path
            r = c.get(f"/api/runs/{rid}/{dl}")
            if r.status_code == 200:
                (OUT / "api" / "runs" / rid).mkdir(parents=True, exist_ok=True)
                (OUT / "api" / "runs" / rid / dl).write_bytes(r.content)
    if a.run:
        save("/api/runs/_started", c.get(f"/api/runs/{a.run}"))
    g = httpx.Client(base_url=a.github_from, timeout=60) if a.github_from else c   # public, read-only endpoints
    save(f"/api/issues/check/{slug(TRY_ISSUE)}", g.post("/api/issues/check", json={"url": TRY_ISSUE}))
    save(f"/api/repos/explore/{slug(TRY_REPO)}", g.post("/api/repos/explore", json={"url": TRY_REPO}))
    save("/api/eval", g.get("/api/eval"))

    # SPA routes fall back to index.html; recorded data and downloads are served as files
    (OUT / "vercel.json").write_text(json.dumps({"rewrites": [{"source": "/((?!assets/|showcase/|api/).*)", "destination": "/index.html"}],
                                                 "headers": [{"source": "/api/(.*)", "headers": [{"key": "Content-Type", "value": "text/plain; charset=utf-8"}]}]},
                                                indent=1), encoding="utf-8")
    print(f"showcase: {len(runs)} runs -> {OUT}")


if __name__ == "__main__":
    main()
