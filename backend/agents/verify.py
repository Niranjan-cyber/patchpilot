"""VERIFY node (B08, the winning feature): FRESH containers (never the agent's), original + test diff + fix diff.
G5: the new test passes in BOTH runs and every baseline-passing test still passes. Retries go back to the Fixer
(≤ fixer retries), then one re-diagnosis, then TRIAGE_ONLY (contracts §1.1)."""
import base64
import uuid

from backend import artifacts, db
from backend.config import limits
from backend.contracts.models import CheckStatus, GateResult, Verification
from backend.sandbox import docker
from backend.sandbox.rules import junit_outcomes
from backend.sandbox.steps import image, snap
from backend.worker.nodes import StepContext


def evaluate_g5(new_ids: list[str], baseline_pass: list[str], suite: dict[str, bool], second: dict[str, bool]):
    """→ (status, reason, regressions). A baseline test with no result counts as a regression: unknown is never a pass."""
    runs = [all(suite.get(t) is True for t in new_ids), all(second.get(t) is True for t in new_ids)] if new_ids else [False, False]
    regressions = sorted(t for t in baseline_pass if suite.get(t) is not True)
    if regressions:
        return CheckStatus.FAILED, "regression", regressions
    if all(runs):
        return CheckStatus.PASSED, "verified", []
    if any(runs):
        return CheckStatus.INCONCLUSIVE, "flaky_1_of_2", []
    return CheckStatus.FAILED, "new_test_fails", []


def _fresh_run(rid: str, diffs: list[str], args: str) -> tuple[dict[str, bool], str, str]:
    name = f"pp-{rid[:8]}-verify-{uuid.uuid4().hex[:6]}"
    b64 = lambda s: base64.b64encode(s.encode()).decode()
    apply = " && ".join(f"echo {b64(d)} | base64 -d > /tmp/d{i}.diff && git apply /tmp/d{i}.diff" for i, d in enumerate(diffs))
    r = docker.run(image(rid), f"{apply} || {{ echo APPLY_FAILED; exit 3; }}; python -m pytest -p no:cacheprovider -rfE "
                   f"--junitxml=/tmp/j.xml {args} > /tmp/o.log 2>&1; tail -c 20000 /tmp/o.log; echo '<<<JUNIT>>>'; cat /tmp/j.xml",
                   name=name, timeout=600, snapshot_volume=snap(rid))
    log, _, xml = r.out.partition("<<<JUNIT>>>")
    return ({} if "APPLY_FAILED" in log else junit_outcomes(xml.strip())), log, name


def _verify_once(ctx: StepContext) -> GateResult:
    run = db.get_run(db.connect(), ctx.run_id)
    diffs = [artifacts.get(run.patch.test_diff_id), artifacts.get(run.patch.fix_diff_id)]
    if any(d is None for d in diffs):
        return GateResult(gate="G5", status=CheckStatus.FAILED, reason="diff_missing")
    diffs = [d.decode("utf-8", "replace") for d in diffs]
    new_ids = run.repro.test_ids
    files = " ".join(sorted({t.split("::")[0] for t in new_ids}))
    suite, log1, c1 = _fresh_run(ctx.run_id, diffs, "")              # full suite: new test + regressions
    second, log2, c2 = _fresh_run(ctx.run_id, diffs, files)          # second, independent run of the new test
    status, reason, regs = evaluate_g5(new_ids, run.baseline.pass_set if run.baseline else [], suite, second)
    ev = [artifacts.put(log1), artifacts.put(log2)]
    run.verify = Verification(new_test_runs=[CheckStatus.PASSED if all(s.get(t) for t in new_ids) else CheckStatus.FAILED
                                             for s in (suite, second)], regressions=regs, container_id=f"{c1},{c2}", evidence_ids=ev)
    db.save_run(db.connect(), run)
    ctx.scratch["verify_log"] = log1[-3000:]
    return GateResult(gate="G5", status=status, reason=reason, evidence_ids=ev)


def _hidden_variant(ctx: StepContext) -> None:
    """B17 (C): after G5 passed, a hidden variant the Fixer never saw. It can only lower readiness (via REVIEW)."""
    from backend.agents.variant import hidden_variant
    try:
        hidden_variant(ctx)
    except Exception as e:   # never fails verification; the row shows not run
        ctx.emit("step.progress", "verify", message=f"Hidden test variant not run ({type(e).__name__}).")


def verify(ctx: StepContext) -> GateResult:
    from backend.agents.diagnose import diagnose
    from backend.agents.fix import fix
    res = _verify_once(ctx)
    tries = limits()["retries"]["fixer"]
    rediagnosed = False
    for i in range(tries + limits()["retries"]["rediagnose"]):
        if res.status == CheckStatus.PASSED:
            ctx.scratch["headline"] = "In a brand-new sandbox, the new test passes twice and every test that passed before still passes."
            _hidden_variant(ctx)
            return res
        why = {"regression": f"it broke tests that passed before: {', '.join((db.get_run(db.connect(), ctx.run_id).verify.regressions or [])[:5])}",
               "new_test_fails": "the reproduction test still fails after your fix", "flaky_1_of_2": "the reproduction test passed only once of two runs"
               }.get(res.reason, res.reason)
        ctx.emit("attempt.retry", "verify", role="fixer", attempt=i + 1, max=tries + 1, reason=res.reason)
        if i >= tries and not rediagnosed:                            # fixer attempts used: one re-diagnosis
            rediagnosed = True
            ctx.emit("step.progress", "verify", message="Fix attempts used up; re-examining the cause once.")
            diagnose(ctx)
        ctx.scratch["verify_feedback"] = f"{why}. Test output:\n{ctx.scratch.get('verify_log', '')[-1500:]}"
        ctx.run = db.get_run(db.connect(), ctx.run_id)
        g4 = fix(ctx)
        if g4 is not None and g4.status != CheckStatus.PASSED:
            break
        res = _verify_once(ctx)
    if res.status == CheckStatus.PASSED:
        ctx.scratch["headline"] = "In a brand-new sandbox, the new test passes twice and every test that passed before still passes."
        _hidden_variant(ctx)
        return res
    ctx.scratch["headline"] = "The fix didn't pass in a fresh sandbox after every attempt, so this is a triage report."
    return GateResult(gate="G5", status=CheckStatus.FAILED,   # flaky (inconclusive) after all attempts also ends as triage
                      reason=res.reason, evidence_ids=res.evidence_ids)
