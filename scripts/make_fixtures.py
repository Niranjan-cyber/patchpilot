"""Generate fixtures/runs/<case>/{state.json,events.jsonl} (contracts §8). Run: uv run python scripts/make_fixtures.py"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.contracts.models import (
    CheckStatus as C, Diagnosis, EndReason as E, Event, IssueSpec, Location, Outcome as O, Patch,
    PauseInfo, PublishBlocker as P, PullRequestRef, ReproTest, RunStatus as R, RunView, SGReport, StepId as S,
    StepState, TestRun, TourItem, Verification, decide_outcome, end_blockers, readiness,
)

T0 = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)
ORDER = [S.PREFLIGHT, S.SETUP, S.BASELINE, S.REPRODUCE, S.DIAGNOSE, S.FIX, S.VERIFY, S.REVIEW]
GATE_OF = {S.PREFLIGHT: "G1", S.SETUP: "G2", S.REPRODUCE: "G3", S.FIX: "G4", S.VERIFY: "G5", S.REVIEW: "G6"}
HEAD = {
    S.PREFLIGHT: "We checked the project's dependencies for known-bad packages.",
    S.SETUP: "We installed the project in a fresh sandbox.",
    S.BASELINE: "We ran the existing tests to see what already passes.",
    S.REPRODUCE: "We wrote a test that fails because of this bug. It failed twice, as expected.",
    S.DIAGNOSE: "We found the likely cause in the code.",
    S.FIX: "We wrote a small fix that only touches source files.",
    S.VERIFY: "In a brand-new sandbox, the new test passes and the old tests still pass.",
    S.REVIEW: "A reviewer checked the fix for shortcuts and scope creep.",
}
EV = lambda n: f"sha256:{n:064x}"
ISSUE = IssueSpec(html_url="https://github.com/patchpilot-demo/tinycalc/issues/1", repo="patchpilot-demo/tinycalc",
                  number=1, title="divide() returns 0 instead of raising on zero", expected="ZeroDivisionError",
                  actual="returns 0", checks={k: C.PASSED for k in
                  ("open", "public", "python", "tests_found", "unassigned", "no_linked_pr")})
DIAG = Diagnosis(locations=[Location(path="tinycalc/ops.py", line=12)], hypothesis="divide() catches ZeroDivisionError and returns 0.",
                 tour=[TourItem(path="tinycalc/ops.py", why="where divide() lives"),
                       TourItem(path="tests/test_ops.py", why="existing tests for ops")], evidence_ids=[EV(4)])


def case(name, passed_upto, fail_at=None, fail_status=C.FAILED, end=E.COMPLETED, *, status=None, extra=None, **kw):
    gates, steps, events, seq = {}, {}, [], 0
    def ev(t, step=None, **p):
        nonlocal seq; seq += 1
        events.append(Event(run_id=name, seq=seq, ts=T0 + timedelta(seconds=20 * seq), type=t, step=step, payload=p))
    ev("run.queued", position=1); ev("run.started", from_step="preflight")
    for st in ORDER:
        if st == fail_at or (passed_upto is not None and ORDER.index(st) > ORDER.index(passed_upto)):
            if st == fail_at:
                ev("step.started", st, attempt=1, headline=HEAD[st])
                steps[st] = StepState(status=fail_status, attempt=1, headline=kw.pop("fail_headline", "This step did not pass."))
                if st in GATE_OF: gates[GATE_OF[st]] = fail_status
                ev("step.finished", st, status=fail_status.value, headline=steps[st].headline, evidence_ids=[EV(99)])
            break
        ev("step.started", st, attempt=1, headline=HEAD[st])
        steps[st] = StepState(status=C.PASSED, attempt=1, headline=HEAD[st], started_at=T0, finished_at=T0)
        if st in GATE_OF: gates[GATE_OF[st]] = C.PASSED
        ev("step.finished", st, status="passed", headline=HEAD[st], evidence_ids=[EV(ORDER.index(st) + 1)])
    g = dict(gates, **kw.pop("gate_override", {}))
    sd = kw.pop("stopped_during_diagnose", False)
    outcome = decide_outcome(g, end, diagnosis_valid=S.DIAGNOSE in steps, stopped_during_diagnose=sd,
                             readiness_capped=kw.get("capped", False))
    blockers = end_blockers(end, outcome) + kw.pop("blockers", [])
    if outcome in (O.VERIFIED_FIX, O.FIX_NEEDS_ATTENTION) and P.RUN_STOPPED not in blockers:
        blockers.append(P.NOT_APPROVED)
    ev("analysis.finished", outcome=outcome.value, end_reason=end.value,
       readiness=readiness(outcome), publish_blockers=[b.value for b in blockers])
    if status is None:
        status = R.AWAITING_APPROVAL if P.NOT_APPROVED in blockers else R.FINISHED
    v = RunView(run_id=name, status=status, outcome=outcome, end_reason=end,
                readiness=readiness(outcome, capped=kw.pop("capped", False)), issue=ISSUE, base_sha="a1b2c3d" * 5 + "a1b2c",
                gates=g, steps=steps, publish_blockers=blockers, created_at=T0, updated_at=events[-1].ts,
                baseline=TestRun(pass_set=["tests/test_ops.py::test_add", "tests/test_ops.py::test_sub"],
                                 fail_set=["tests/test_ops.py::test_pow_big"], evidence_ids=[EV(3)]) if S.BASELINE in steps else None,
                repro=ReproTest(test_diff_id=EV(10), test_ids=["tests/test_issue_1.py::test_divide_zero"],
                                expected_failure="AssertionError: DID NOT RAISE ZeroDivisionError",
                                runs_on_base=[C.FAILED, C.FAILED]) if S.REPRODUCE in steps else None,
                diagnosis=DIAG if S.DIAGNOSE in steps else None,
                patch=Patch(fix_diff_id=EV(11), test_diff_id=EV(10), attempt=1, policy_result=C.PASSED) if S.FIX in steps else None,
                verify=Verification(new_test_runs=[C.PASSED, C.PASSED], container_id="pp-verify-1") if S.VERIFY in steps else None,
                supplyguard=SGReport(report_id=EV(20), status=C.PASSED, files=["pyproject.toml"]) if S.PREFLIGHT in steps else None,
                **(extra or {}))
    for k, val in kw.items(): setattr(v, k, val)
    d = Path("fixtures/runs") / name; d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(v.model_dump_json(indent=2))
    (d / "events.jsonl").write_text("".join(e.model_dump_json() + "\n" for e in events))


case("verified_fix", S.REVIEW)
case("needs_attention_deps_inconclusive", S.REVIEW, capped=True, blockers=[P.DEPS_INCONCLUSIVE], gate_override={"G1": C.INCONCLUSIVE},
     supplyguard=SGReport(report_id=EV(21), status=C.INCONCLUSIVE, failures=["OSV lookup timed out"]))
case("triage_only", S.FIX, fail_at=S.VERIFY, end=E.RETRIES_EXHAUSTED, fail_headline="The fix didn't pass in a fresh sandbox after 3 tries.")
case("cannot_reproduce", S.BASELINE, fail_at=S.REPRODUCE, end=E.RETRIES_EXHAUSTED, fail_headline="We couldn't make the bug happen in a test.")
case("env_failed", S.PREFLIGHT, fail_at=S.SETUP, end=E.RETRIES_EXHAUSTED, fail_headline="We couldn't install this project.")
case("blocked", None, fail_at=S.PREFLIGHT, fail_status=C.BLOCKED, fail_headline="A dependency looks like a typosquat of a popular package.")
case("paused_quota_unknown_reset", S.BASELINE, end=E.COMPLETED, status=R.PAUSED,
     pause=PauseInfo(reason="provider_quota", provider="gemini", resume_at=None), outcome=None, end_reason=None, readiness=None)
case("pause_timeout", S.BASELINE, end=E.PAUSE_TIMEOUT)
case("interrupted_then_resumed", S.DIAGNOSE, status=R.RUNNING, outcome=None, end_reason=None, readiness=None)
case("stopped_during_setup", S.PREFLIGHT, end=E.USER_STOPPED)
case("stopped_after_verify", S.VERIFY, end=E.USER_STOPPED)
case("upstream_changed", S.REVIEW, blockers=[P.UPSTREAM_CHANGED], status=R.FINISHED)
case("published_fork", S.REVIEW, status=R.PUBLISHED, pr=PullRequestRef(url="https://github.com/patchpilot-demo/tinycalc/pull/2",
     number=2, head_branch="patchpilot/issue-1-publishe", fork_owner="pp-contributor", state="open"))
case("publish_branch_only", S.REVIEW, status=R.PUBLISHED, pr=PullRequestRef(head_branch="patchpilot/issue-1-branchon",
     fork_owner="pp-contributor", compare_url="https://github.com/patchpilot-demo/tinycalc/compare/main...pp-contributor:patchpilot/issue-1-branchon?expand=1"))
case("details_expired", S.REVIEW, status=R.FINISHED, details_expired_at=T0 + timedelta(days=31))
print("wrote", len(list(Path("fixtures/runs").iterdir())), "fixture runs")
