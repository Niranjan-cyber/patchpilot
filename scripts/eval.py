"""B14 eval runner (host only, run overnight): each case in eval/cases.json -> a real PatchPilot run ->
the official tests on PatchPilot's fix -> eval/results.json, which /eval shows.

Needs the worker running (`uv run python -m backend.worker.main`) and Docker. Usage:
    uv run python scripts/eval.py [--only <case id>] [--timeout-min 45]
"""
import argparse
import base64
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import artifacts, db  # noqa: E402
from backend.eval import official_result, parse_ra  # noqa: E402
from backend.github.reader import check_issue  # noqa: E402
from backend.sandbox import docker  # noqa: E402
from backend.sandbox.steps import cname, image, snap  # noqa: E402

CASES, RESULTS = ROOT / "eval" / "cases.json", ROOT / "eval" / "results.json"
MAX_SCRIPT = 24000   # Windows command line limit is ~32k chars


def official(case: dict, run) -> tuple[str | None, str | None]:
    """Apply PatchPilot's fix + the benchmark's test patch in a fresh sandbox and grade the official tests."""
    if not (run.patch and run.env and run.env.image_id):
        return None, "no fix to check"
    fix = artifacts.get(run.patch.fix_diff_id)
    if fix is None:
        return None, "fix diff artifact missing"
    b64 = lambda b: base64.b64encode(b if isinstance(b, bytes) else b.encode()).decode()
    files = sorted({t.split("::")[0] for t in case["fail_to_pass"] + case["pass_to_pass"]})
    script = (f"echo {b64(fix)} | base64 -d > /tmp/fix.diff && echo {b64(case['test_patch'])} | base64 -d > /tmp/test.diff"
              " && git apply /tmp/fix.diff && git apply /tmp/test.diff || { echo APPLY_FAILED; exit 3; };"
              f" python -m pytest -rA -p no:cacheprovider {' '.join(files)} 2>&1 | grep -E '^(PASSED|FAILED|ERROR) '")
    if len(script) > MAX_SCRIPT:
        return None, "patch too large to check"
    r = docker.run(image(run.run_id), script, name=cname(run.run_id, "eval"), timeout=900, snapshot_volume=snap(run.run_id))
    if "APPLY_FAILED" in r.out:
        return None, "official test patch didn't apply on top of the fix"
    return official_result(case["fail_to_pass"], case["pass_to_pass"], parse_ra(r.out)), None


def run_case(case: dict, timeout_s: float) -> dict:
    out = {k: case.get(k) for k in ("id", "kind", "issue_url")} | {"run_id": None, "outcome": None, "official": None,
                                                                   "seconds": None, "note": case.get("note")}
    if not case.get("issue_url"):
        return out
    c, t0 = db.connect(), time.monotonic()
    chk = check_issue(case["issue_url"])
    v = db.create_run(c, chk.issue, base_sha=case.get("base_commit") or chk.base_sha or "pending", owner_session_hash="eval")
    out["run_id"] = v.run_id
    while time.monotonic() - t0 < timeout_s:
        v = db.get_run(c, v.run_id)
        if v.outcome:
            break
        time.sleep(10)
    else:
        db.request_stop(c, v.run_id)
        out["note"] = "timed out; run stopped"
        return out
    out["outcome"], out["seconds"] = v.outcome.value, round(time.monotonic() - t0, 1)
    if case["kind"] == "swebench":
        out["official"], note = official(case, v)
        out["note"] = note
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--timeout-min", type=float, default=45)
    a = ap.parse_args()
    cases = json.loads(CASES.read_text())["cases"]
    old = {r["id"]: r for r in json.loads(RESULTS.read_text())["cases"]} if RESULTS.exists() else {}
    res = []
    for case in cases:
        if a.only and case["id"] != a.only:
            res.append(old.get(case["id"], run_case({**case, "issue_url": None}, 0)))
            continue
        print(f"[eval] {case['id']} …", flush=True)
        try:
            r = run_case(case, a.timeout_min * 60)
        except Exception as e:   # one broken case must not lose the others' results
            r = run_case({**case, "issue_url": None}, 0) | {"note": f"runner error: {type(e).__name__}: {e}"[:200]}
        print(f"[eval] {case['id']}: {r['outcome']} official={r['official']} {r['note'] or ''}", flush=True)
        res.append(r)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    RESULTS.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                   "commit": sha or None, "cases": res}, indent=1))
    print(f"[eval] wrote {RESULTS}")


if __name__ == "__main__":
    main()
