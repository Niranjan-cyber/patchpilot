"""B17 / S4: a hidden test variant the Fixer never sees (written after the fix, against the ORIGINAL code).
It can only LOWER readiness, through the Reviewer (contracts: only the Reviewer lowers readiness)."""
import re
import uuid

from backend import artifacts, db
from backend.agents import loop
from backend.agents.bisect import probe_result
from backend.contracts.models import CheckStatus, Verification
from backend.gates.diff_policy import is_test_path
from backend.llm_gateway import BudgetExceeded, QuotaPause
from backend.sandbox import docker
from backend.sandbox.steps import image, snap
from backend.worker.nodes import StepContext


def variant_result(on_base: str, on_fix: str) -> tuple[CheckStatus, str]:
    if probe_result(on_base) != "fail":
        return CheckStatus.NOT_RUN, "variant_not_failing_on_base"   # a variant that doesn't catch the bug proves nothing
    r = probe_result(on_fix)
    if r == "pass":
        return CheckStatus.PASSED, "ok"
    if r == "fail":
        return CheckStatus.FAILED, "fix_fails_hidden_variant"
    return CheckStatus.INCONCLUSIVE, "variant_run_unclear"


def review_concern(v: Verification | None) -> dict | None:
    """For the Reviewer: a FAILED hidden variant is a high concern. Anything else adds nothing (never a pass)."""
    if v and v.hidden_variant == CheckStatus.FAILED:
        return {"severity": "high", "text": "The fix passes the visible test but fails a hidden variant of it, so it may only "
                                            "handle the exact case in the test."}
    return None


def _task(run, n: int) -> str:
    i, tests = run.issue, ", ".join(run.repro.test_ids)
    return f"""Write ONE extra pytest test for the same bug as the existing test {tests}, but with DIFFERENT inputs, so that a
fix that only special-cases the existing test would fail it. It must fail on the current (unfixed) code because of the bug.
Issue #{i.number}: {i.title}
Only create tests/test_patchpilot_hidden_{n}.py (never edit other files). Check it fails with:
python -m pytest -q -p no:cacheprovider tests/test_patchpilot_hidden_{n}.py
When done, run: echo {loop.DONE} '{{"test_ids": ["tests/test_patchpilot_hidden_{n}.py::<name>"]}}'"""


def _run(rid: str, diffs: list[str], test_file: str) -> str:
    script = "".join(f"cat > /tmp/d{k}.diff <<'PP_EOF'\n{d}\nPP_EOF\ngit apply /tmp/d{k}.diff && " for k, d in enumerate(diffs))
    r = docker.run(image(rid), script + f"python -m pytest -p no:cacheprovider -rfE {test_file} 2>&1 | tail -c 6000",
                   name=f"pp-{rid[:8]}-hv-{uuid.uuid4().hex[:6]}", timeout=300, snapshot_volume=snap(rid))
    return r.out


REASON = {"no_sandbox": "the sandbox for writing the variant didn't start", "ai_unavailable": "the AI was unavailable or over budget",
          "no_variant_written": "no variant test was written", "edits_non_test_files": "the variant changed non-test files",
          "variant_not_failing_on_base": "the variant didn't fail on the original code, so it would prove nothing",
          "variant_run_unclear": "the variant's run didn't give a clean pass or fail", "ok": "", "fix_fails_hidden_variant": ""}


def hidden_variant(ctx: StepContext) -> CheckStatus:
    """Call after G5 passed. Sets run.verify.hidden_variant + kv variant:<run_id> {status, reason}. Never PASSED by default:
    any failure to produce or run a variant is NOT_RUN with the reason (also on an unexpected error)."""
    import json
    rid = ctx.run_id
    try:
        status, reason, ev = _hidden_variant(rid)
    except Exception as e:
        status, reason, ev = CheckStatus.NOT_RUN, f"error: {type(e).__name__}", []
    run = db.get_run(db.connect(), rid)
    if run.verify:
        run.verify.hidden_variant = status
        run.verify.evidence_ids = [*run.verify.evidence_ids, *ev]
        db.save_run(db.connect(), run)
    db.put_kv(db.connect(), f"variant:{rid}", json.dumps({"status": status.value, "reason": reason}))
    ctx.emit("step.progress", "verify", message=f"Hidden test variant: {status.value}" + (f" ({REASON.get(reason, reason)})." if REASON.get(reason, reason) else "."))
    return status


def _hidden_variant(rid: str) -> tuple[CheckStatus, str, list[str]]:
    run = db.get_run(db.connect(), rid)
    if not (run.repro and run.patch and run.verify):
        return CheckStatus.NOT_RUN, "no_verified_fix", []
    name = f"pp-{rid[:8]}-hvtd-{uuid.uuid4().hex[:4]}"
    if docker.start(image(rid), name, snap(rid)).code:
        return CheckStatus.NOT_RUN, "no_sandbox", []
    try:
        ex = lambda cmd: (lambda r: (r.code, r.out))(docker.exec_(name, cmd, timeout=180))
        try:
            res, transcript = loop.run(_task(run, run.issue.number), exec_=ex, run_id=rid, role="test_designer", step_limit=12)
        except (QuotaPause, BudgetExceeded):
            return CheckStatus.NOT_RUN, "ai_unavailable", []
        diff = docker.exec_(name, "git add -A >/dev/null && git diff --cached --binary").out
    finally:
        docker.rm(name)
    ev = [artifacts.put("\n\n".join(f"[{m['role']}]\n{m['content']}" for m in transcript))] if transcript else []
    paths = re.findall(r"^diff --git a/\S+ b/(\S+)$", diff, re.M)
    if not (res and diff.strip() and paths):
        return CheckStatus.NOT_RUN, "no_variant_written", ev
    if not all(is_test_path(p) for p in paths):
        return CheckStatus.NOT_RUN, "edits_non_test_files", ev
    fix = (artifacts.get(run.patch.fix_diff_id) or b"").decode("utf-8", "replace")
    test_file = " ".join(sorted(set(paths)))
    base_out, fix_out = _run(rid, [diff], test_file), _run(rid, [fix, diff], test_file)
    status, reason = variant_result(base_out, fix_out)
    return status, reason, [*ev, artifacts.put(diff), artifacts.put(base_out), artifacts.put(fix_out)]
