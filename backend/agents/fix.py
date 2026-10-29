"""FIX (B07): the Fixer edits source (never tests) until the reproduction test passes in its sandbox; G4 decides the diff.
A G4 rejection goes back to the Fixer with the reason and counts as an attempt (contracts §1.1)."""
import uuid

from backend import artifacts, db
from backend.agents import loop
from backend.config import limits
from backend.contracts.models import CheckStatus, GateResult, Patch
from backend.gates.diff_policy import MAX_FILES, MAX_LINES, g4_result
from backend.llm_gateway import BudgetExceeded, QuotaPause
from backend.sandbox import docker
from backend.sandbox.steps import image, snap
from backend.worker.nodes import StepContext

WHY = {"edits_tests": "it changed a test file; tests are fixed, only change source files",
       "dependency_change": "it changed a dependency file (requirements, pyproject, setup, lock files)",
       "ci_change": "it changed .github/", "too_many_files": f"it changed more than {MAX_FILES} files",
       "too_many_lines": f"it changed more than {MAX_LINES} lines", "empty_diff": "it changed nothing",
       "binary_change": "it changed a binary file"}


def task_prompt(run, previous: str | None, feedback: str | None) -> str:
    i, d = run.issue, run.diagnosis
    tests = " ".join(run.repro.test_ids) if run.repro else "tests"
    where = ", ".join(f"{l.path}:{l.line}" if l.line else l.path for l in (d.locations if d else []))
    return f"""Fix this bug with the smallest change to the project's SOURCE code.

Issue #{i.number}: {i.title}
Likely cause: {d.hypothesis if d else "(unknown)"}
Where: {where or "(unknown)"}

Rules (checked by code; a violation rejects your fix):
- Never edit, delete, skip or add tests; never touch requirements/pyproject/setup/lock files or .github/.
- At most {MAX_FILES} files and {MAX_LINES} changed lines.
- Check your fix: python -m pytest -q -p no:cacheprovider {tests} must pass, and the existing tests near your change should still pass.
- When done, run: echo {loop.DONE} '{{"summary": "<one line: what you changed and why>"}}'
{"The user asked for this change to the previous fix: " + feedback if feedback else ""}
{"Your previous fix was rejected: " + previous if previous else ""}"""


def fix(ctx: StepContext) -> GateResult | None:
    rid, run = ctx.run_id, ctx.run
    if not run.repro:
        return GateResult(gate="G4", status=CheckStatus.NOT_RUN, reason="no_reproduction")
    test_diff = (artifacts.get(run.repro.test_diff_id) or b"").decode("utf-8", "replace")
    feedback = db.get_kv(db.connect(), f"revise:{rid}") if run.revision else None
    attempts, previous, last = limits()["retries"]["fixer"] + 1, ctx.scratch.pop("verify_feedback", None), None   # A: G5 failure → Fixer (B08)
    for attempt in range(1, attempts + 1):
        name = f"pp-{rid[:8]}-fix-{attempt}-{uuid.uuid4().hex[:4]}"
        if docker.start(image(rid), name, snap(rid)).code:
            raise RuntimeError("could not start the agent sandbox")
        try:
            # the reproduction test is committed first, so the Fixer's diff is only its own change (and shows any test edit)
            setup = docker.exec_(name, f"cat > /tmp/t.diff <<'PP_EOF'\n{test_diff}\nPP_EOF\ngit apply /tmp/t.diff && git add -A && "
                                       "git -c user.name=pp -c user.email=pp@local commit -qm repro", timeout=60)
            if setup.code:
                raise RuntimeError("could not apply the reproduction test in the fixer sandbox")
            ex = lambda cmd: (lambda r: (r.code, r.out))(docker.exec_(name, cmd, timeout=180))
            try:
                res, transcript = loop.run(task_prompt(run, previous, feedback), exec_=ex, run_id=rid, role="fixer", step_limit=25,
                                           on_step=lambda s, cmd: ctx.emit("step.progress", "fix", message=f"Step {s + 1}: {cmd[:120]}"))
            except QuotaPause as q:
                ctx.scratch["pause"] = q
                ctx.scratch["headline"] = "Paused: the free AI capacity is used up for now."
                return GateResult(gate="G4", status=CheckStatus.NOT_RUN, reason="paused_for_quota")
            except BudgetExceeded as b:
                ctx.scratch.update(end_reason="token_limit", headline=f"Stopped: the {b.scope} AI budget is used up.")
                return GateResult(gate="G4", status=CheckStatus.NOT_RUN, reason=f"budget_{b.scope}")
            diff = docker.exec_(name, "git add -A >/dev/null && git diff --cached --binary HEAD").out
        finally:
            docker.rm(name)
        ev = [artifacts.put("\n\n".join(f"[{m['role']}]\n{m['content']}" for m in transcript))]
        if diff.strip():
            ev.append(artifacts.put(diff))
        last = g4_result(diff, evidence_ids=ev) if res else GateResult(gate="G4", status=CheckStatus.FAILED,
                                                                     reason="no_fix_written", evidence_ids=ev)
        if last.status == CheckStatus.PASSED:
            run = db.get_run(db.connect(), rid)
            run.patch = Patch(fix_diff_id=ev[1], test_diff_id=run.repro.test_diff_id, attempt=attempt,
                              policy_result=CheckStatus.PASSED, policy_reason=str(res.get("summary", ""))[:300] or None)
            db.save_run(db.connect(), run)
            files = diff.count("\ndiff --git ") + diff.startswith("diff --git ")
            ctx.scratch["headline"] = f"Wrote a fix ({files} file{'s' if files != 1 else ''}) that passed the change rules."
            return last
        previous = WHY.get(last.reason, "you didn't finish with a fix and the PATCHPILOT_DONE line.")
        ctx.emit("attempt.retry", "fix", role="fixer", attempt=attempt, max=attempts, reason=last.reason, evidence_ids=ev)
    ctx.scratch["headline"] = f"None of {attempts} fixes followed the change rules ({WHY.get(last.reason, last.reason)})."
    return last
