"""Host only, no LLM: can each SWE-bench case in eval/cases.json give an honest number in our sandbox?

Uses PatchPilot's own PREFLIGHT fetch and SETUP install (pp-base:3.12, PyPI-only proxy), then grades the official tests the way
scripts/eval.py does, twice: with the test patch only (FAIL_TO_PASS must fail) and with the reference fix too (all must pass).
Most SWE-bench Lite code predates Python 3.12, so a case can fail here before PatchPilot ever runs.

Needs Docker and pp-base:3.12 (`docker build -t pp-base:3.12 -f infra/Dockerfile.base infra`). Usage:
    uv run python scripts/check_eval_cases.py [--cases eval/cases.json] [--only <case id>]
"""
import argparse
import base64
import json
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import limits  # noqa: E402
from backend.contracts.models import CheckStatus  # noqa: E402
from backend.eval import case_gradable, parse_ra  # noqa: E402
from backend.sandbox import docker  # noqa: E402
from backend.sandbox.rules import evaluate_setup  # noqa: E402
from backend.sandbox.steps import INSTALL, WORK, cname, fetch_source, image, snap  # noqa: E402

MAX_SCRIPT = 24000   # same limit as scripts/eval.py: a case over it can't be graded there either


def tests(rid: str, case: dict, patches: list[str]) -> tuple[dict | None, str | None]:
    b64 = lambda s: base64.b64encode(s.encode()).decode()
    files = sorted({t.split("::")[0] for t in case["fail_to_pass"] + case["pass_to_pass"]})
    apply = " && ".join(f"echo {b64(p)} | base64 -d > /tmp/p{i}.diff && git apply /tmp/p{i}.diff" for i, p in enumerate(patches))
    script = (f"{{ {apply}; }} || {{ echo APPLY_FAILED; exit 3; }};"
              f" python -m pytest -rA -p no:cacheprovider {' '.join(files)} 2>&1 | grep -E '^(PASSED|FAILED|ERROR) '")
    if len(script) > MAX_SCRIPT:
        return None, "patch_too_large"
    r = docker.run(image(rid), script, name=cname(rid, "chk"), timeout=900, snapshot_volume=snap(rid))
    return (None, "patch_did_not_apply") if "APPLY_FAILED" in r.out else (parse_ra(r.out), None)


def check(case: dict) -> dict:
    rid, t0 = f"chk{uuid.uuid4().hex[:8]}", time.monotonic()   # t0: setup time only
    out = {"id": case["id"]}
    try:
        _, src = fetch_source(case["repo"], rid, case["base_commit"])
        docker.ensure_infra()
        docker.make_snapshot(snap(rid), src)
        name = cname(rid, "setup")
        r = docker.run("pp-base:3.12", INSTALL, name=name, network=docker.SETUP_NET, timeout=limits()["setup_seconds"],
                       snapshot_volume=snap(rid), read_only=False, keep=True)
        num = lambda k: int(m.group(1)) if (m := re.search(rf"{k}=(\d+)", r.out)) else -1
        status, reason = evaluate_setup(num("INSTALL_EXIT"), r.timed_out, num("COLLECT_EXIT"), num("COLLECTED"))
        out["setup_seconds"] = round(time.monotonic() - t0)
        if status != CheckStatus.PASSED:
            docker.rm(name)
            return out | {"gradable": False, "reason": f"setup_{reason}", "log_tail": r.out[-1500:]}
        docker.commit(name, image(rid))
        docker.rm(name)
        before, e1 = tests(rid, case, [case["test_patch"]])
        after, e2 = tests(rid, case, [case["patch"], case["test_patch"]])   # fix first, as scripts/eval.py applies them
        ok, why = case_gradable(case["fail_to_pass"], case["pass_to_pass"], before, after)
        bad = sorted(t for t in case["fail_to_pass"] + case["pass_to_pass"] if (after or {}).get(t) != "PASSED")
        return out | {"gradable": ok, "reason": e1 or e2 or why, "not_passing_after": bad[:10]}
    except Exception as e:   # one broken case must not stop the others
        return out | {"gradable": False, "reason": f"error: {e!r}"[:300]}
    finally:
        docker.rm_image(image(rid))
        docker.rm_volume(snap(rid))
        shutil.rmtree(WORK / rid, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(ROOT / "eval" / "cases.json"))
    ap.add_argument("--only")
    a = ap.parse_args()
    cases = [c for c in json.loads(Path(a.cases).read_text(encoding="utf-8"))["cases"]
             if c["kind"] == "swebench" and (not a.only or c["id"] == a.only)]
    for c in cases:
        if not c.get("patch"):
            print(json.dumps({"id": c["id"], "gradable": False, "reason": "no reference patch in cases.json"}), flush=True)
            continue
        t0 = time.monotonic()
        print(json.dumps(check(c) | {"seconds": round(time.monotonic() - t0)}), flush=True)


if __name__ == "__main__":
    main()
