"""REPRODUCE node (B06): the Test designer writes a test that fails because of the bug; G3 (B's gate) decides."""
import re
import uuid

from backend import artifacts, db
from backend.agents import loop
from backend.config import limits
from backend.contracts.models import CheckStatus, GateResult, ReproTest
from backend.gates.reproduction import g3_result
from backend.llm_gateway import BudgetExceeded, QuotaPause
from backend.sandbox import docker
from backend.sandbox.steps import image, snap
from backend.worker.nodes import StepContext

ERR = re.compile(r"\b([A-Z]\w*(?:Error|Exception))\b")


def task_prompt(ctx: StepContext, attempt: int, previous: str | None) -> str:
    i = ctx.run.issue
    return f"""Write a NEW pytest test that reproduces this GitHub issue. It must FAIL on the current code because of the bug
(an assertion failure, or the error the issue describes), not because of an import or syntax error.

Issue #{i.number}: {i.title}
Expected: {i.expected or "(not stated)"}
Actual: {i.actual or "(not stated)"}
Description:
{(i.summary or "")[:3000]}

Rules:
- Only add or edit files under tests/ (create tests/test_patchpilot_issue_{i.number}.py). Never modify source files.
- Run your test with `python -m pytest -q -p no:cacheprovider <file>` and check it fails for the right reason.
- When done, run: echo {loop.DONE} '{{"test_ids": ["tests/test_patchpilot_issue_{i.number}.py::<name>"], "expected_failure": "<one line>"}}'
{"Previous attempt was rejected: " + previous if previous else ""}(attempt {attempt})"""


def issue_error(ctx: StepContext) -> str | None:
    m = ERR.search(f"{ctx.run.issue.actual or ''} {ctx.run.issue.summary or ''}")
    return m.group(1) if m else None


def _check_run(rid: str, diff: str, tests: list[str]) -> str:
    """Apply the test diff to pristine source in a FRESH container and run only the new test(s)."""
    files = " ".join(sorted({t.split("::")[0] for t in tests})) or "tests"
    r = docker.run(image(rid), f"cat > /tmp/t.diff <<'PP_EOF'\n{diff}\nPP_EOF\n"
                   f"git apply /tmp/t.diff && python -m pytest -p no:cacheprovider -rfE {files} 2>&1 | tail -c 20000",   # no -q: G3 needs the full summary
                   name=f"pp-{rid[:8]}-g3-{uuid.uuid4().hex[:6]}", timeout=300, snapshot_volume=snap(rid))
    return r.out


def reproduce(ctx: StepContext) -> GateResult:
    rid, retries = ctx.run_id, limits()["retries"]["test_designer"]
    previous, last = None, None
    for attempt in range(1, retries + 2):
        name = f"pp-{rid[:8]}-td-{attempt}-{uuid.uuid4().hex[:4]}"
        if docker.start(image(rid), name, snap(rid)).code:
            raise RuntimeError("could not start the agent sandbox")
        try:
            ex = lambda cmd: (lambda r: (r.code, r.out))(docker.exec_(name, cmd, timeout=180))
            try:
                res, transcript = loop.run(task_prompt(ctx, attempt, previous), exec_=ex, run_id=rid, role="test_designer",
                                           on_step=lambda s, cmd: ctx.emit("step.progress", "reproduce", message=f"Step {s + 1}: {cmd[:120]}"))
            except QuotaPause as q:
                ctx.scratch["pause"] = q
                ctx.scratch["headline"] = "Paused: the free AI capacity is used up for now."
                return GateResult(gate="G3", status=CheckStatus.NOT_RUN, reason="paused_for_quota")
            except BudgetExceeded as b:
                ctx.scratch["end_reason"] = "token_limit"
                ctx.scratch["headline"] = f"Stopped: the {b.scope} AI budget is used up."
                return GateResult(gate="G3", status=CheckStatus.NOT_RUN, reason=f"budget_{b.scope}")
            diff = docker.exec_(name, "git add -A >/dev/null && git diff --cached --binary").out
            paths = re.findall(r"^diff --git a/\S+ b/(\S+)$", diff, re.M)
        finally:
            docker.rm(name)
        transcript_id = artifacts.put("\n\n".join(f"[{m['role']}]\n{m['content']}" for m in transcript))
        tests = (res or {}).get("test_ids") or []
        if not res or not diff.strip():
            previous, last = "you didn't finish with a test and the PATCHPILOT_DONE line.", GateResult(
                gate="G3", status=CheckStatus.FAILED, reason="no_test_written", evidence_ids=[transcript_id])
            ctx.emit("attempt.retry", "reproduce", role="test_designer", attempt=attempt, max=retries + 1, reason="no_test_written")
            continue
        outs = [_check_run(rid, diff, tests) for _ in range(2)]
        ev = [transcript_id, artifacts.put(diff), *[artifacts.put(o) for o in outs]]
        last = g3_result(paths, outs, issue_error(ctx), evidence_ids=ev)
        if last.status == CheckStatus.PASSED:
            run = db.get_run(db.connect(), rid)
            run.repro = ReproTest(test_diff_id=ev[1], test_ids=tests, expected_failure=str(res.get("expected_failure", ""))[:300],
                                  runs_on_base=[CheckStatus.FAILED, CheckStatus.FAILED], evidence_ids=ev)
            db.save_run(db.connect(), run)
            ctx.scratch["headline"] = "We wrote a test that fails because of this bug. It failed twice, as expected."
            return last
        previous = f"G3 said '{last.reason}'. The test must fail twice, on an assertion or the issue's error, and touch only tests/."
        ctx.emit("attempt.retry", "reproduce", role="test_designer", attempt=attempt, max=retries + 1, reason=last.reason)
    ctx.scratch["headline"] = "We couldn't make the bug happen in a test after 3 tries."
    return GateResult(gate="G3", status=CheckStatus.FAILED, reason=last.reason if last else "no_attempt",
                      evidence_ids=last.evidence_ids if last else [])
