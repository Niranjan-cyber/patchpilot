"""#48 / contracts v0.4: UNSUPPORTED and ASSESSMENT_ONLY issues end at G0 as a finished report; nothing executes."""
import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.api import main
from backend.contracts.models import CheckStatus as S, EndReason, Outcome, PublishBlocker, RepoPolicy, IssueSpec, decide_outcome
from backend.github.assess import assess, new_warnings
from backend.github.reader import IssueCheck

URL = "https://github.com/o/r/issues/1"
OK = {"open": S.PASSED, "public": S.PASSED, "python": S.PASSED, "tests_found": S.PASSED, "unassigned": S.PASSED, "no_linked_pr": S.PASSED}
BUG = "```python\ndivide(1, 0)\n```\nExpected: ZeroDivisionError\nActual: 0"


def check(title="divide(1, 0) returns 0", body=BUG, labels=("bug",), checks=OK, unsupported=None, warnings=(), policy="unknown",
          model="bug"):
    w = list(warnings)
    a = assess(title=title, body=body, labels=list(labels), names=["pyproject.toml", "tests"], state="open", checks=checks,
               unsupported=unsupported, warnings=w, linked=[], extracted={"issue_type": model} if model else None,
               base_sha="abc", forbids_ai=policy == "forbidden")
    w += new_warnings(a)
    return IssueCheck(issue=IssueSpec(html_url=URL, repo="o/r", number=1, title=title, checks=checks), base_sha="abc",
                      default_branch="main", language="Python", policy=RepoPolicy(ai_policy=policy), warnings=w,
                      unsupported=unsupported, assessment=a, fetched_at=db.now())


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))


def post(monkeypatch, chk, **body):
    monkeypatch.setattr(main, "check_issue", lambda url: chk)
    return TestClient(main.app, base_url="https://testserver").post("/api/runs", json={"issue_url": URL, **body})


def jobs(rid):
    return db.connect().execute("SELECT COUNT(*) FROM jobs WHERE run_id=?", (rid,)).fetchone()[0]


def test_feature_request_becomes_a_finished_assessment_with_no_job(monkeypatch):
    r = post(monkeypatch, check(title="Add a power() function", body="It would be nice to have power().", labels=("enhancement",), model="enhancement"))
    assert r.status_code == 201
    v = r.json()
    assert v["status"] == "finished" and v["outcome"] == "ASSESSMENT_ONLY" and v["end_reason"] == "completed"
    assert v["gates"]["G0"] == "blocked" and v["assessment"]["handling_decision"] == "ASSESSMENT_ONLY"
    assert v["readiness"] == "Assessment only: no fix attempted" and "outcome_not_verified" in v["publish_blockers"]
    assert jobs(v["run_id"]) == 0          # the worker can never reach the Fixer


def test_non_python_repo_is_an_unsupported_assessment_not_a_422(monkeypatch):
    r = post(monkeypatch, check(checks={**OK, "python": S.FAILED}, unsupported="not_python"))
    v = r.json()
    assert r.status_code == 201 and v["outcome"] == "ASSESSMENT_ONLY" and v["assessment"]["handling_decision"] == "UNSUPPORTED"
    assert jobs(v["run_id"]) == 0


def test_assessments_do_not_use_up_run_limits(monkeypatch):
    lim = main.limits()
    feature = check(title="Add power()", body="Would be nice.", labels=("enhancement",), model="enhancement")
    monkeypatch.setattr(main, "check_issue", lambda url: feature)
    c = TestClient(main.app, base_url="https://testserver")
    for _ in range(lim["session_runs_per_day"] + 1):
        assert c.post("/api/runs", json={"issue_url": URL}).status_code == 201


def test_ready_bug_still_queues_a_job_and_records_the_assessment(monkeypatch):
    v = post(monkeypatch, check()).json()
    assert v["status"] == "queued" and v["assessment"]["handling_decision"] == "READY" and jobs(v["run_id"]) == 1


def test_needs_information_is_an_overridable_warning(monkeypatch):
    chk = check(title="divide is odd", body="divide is weird sometimes.")
    assert chk.assessment.handling_decision == "NEEDS_INFORMATION" and "needs_info" in chk.warnings
    r = post(monkeypatch, chk)
    assert r.status_code == 409 and "needs_info" in r.json()["message"]
    v = post(monkeypatch, chk, continue_despite=["needs_info"]).json()
    assert v["status"] == "queued" and jobs(v["run_id"]) == 1


def test_unclear_type_is_an_overridable_warning(monkeypatch):
    chk = check(title="divide", body="See title.", labels=(), model="unknown")
    assert chk.assessment.handling_decision == "HUMAN_DECISION" and "unclear_type" in chk.warnings
    assert post(monkeypatch, chk).status_code == 409
    assert post(monkeypatch, chk, continue_despite=["unclear_type"]).json()["status"] == "queued"


def test_repo_forbids_ai_stays_a_hard_blocker_on_assessments_too(monkeypatch):
    v = post(monkeypatch, check(title="Docs: fix typo", body="typo in readme", labels=("documentation",), policy="forbidden", model="docs")).json()
    assert v["outcome"] == "ASSESSMENT_ONLY" and "repo_forbids_ai" in v["publish_blockers"]


def test_row0_only_for_g0_blocked_not_an_accepted_warning():
    # G0 "failed" = the user accepted closed/assigned/linked_pr and the run went ahead: must NOT become ASSESSMENT_ONLY
    assert decide_outcome({"G0": S.FAILED, "G3": S.PASSED, "G5": S.PASSED}, EndReason.COMPLETED) == Outcome.VERIFIED_FIX
    assert decide_outcome({"G0": S.BLOCKED}, EndReason.COMPLETED) == Outcome.ASSESSMENT_ONLY
    # a G0-blocked run can never be a fix, whatever else is recorded
    assert decide_outcome({"G0": S.BLOCKED, "G5": S.PASSED}, EndReason.COMPLETED) == Outcome.ASSESSMENT_ONLY


def test_report_explains_an_assessment_only_run(monkeypatch):
    from backend.report import render
    v = post(monkeypatch, check(title="Add a power() function", body="Would be nice.", labels=("enhancement",), model="enhancement")).json()
    md = render(db.get_run(db.connect(), v["run_id"]))
    assert "## Assessment" in md and "**ASSESSMENT_ONLY**" in md and "doesn't change any code" in md
    assert "Suggested next step" in md and "Outcome: **ASSESSMENT_ONLY**" in md


# ---- A's review of #50 (2026-11-07 20:18), one regression test per confirmed bug ----
def test_bug1_save_assessment_never_queues_a_job_even_if_the_issue_now_reads_as_ready(monkeypatch):
    # S-01 showed ASSESSMENT_ONLY; by the time "Save the assessment report" is clicked the model says bug (READY)
    v = post(monkeypatch, check(), assessment_only=True).json()
    assert v["status"] == "finished" and v["outcome"] == "ASSESSMENT_ONLY" and jobs(v["run_id"]) == 0


def test_bug4_accepted_new_warning_records_g0_failed_not_passed(monkeypatch):
    chk = check(title="divide", body="See title.", labels=(), model="unknown")
    v = post(monkeypatch, chk, continue_despite=["unclear_type"]).json()
    assert v["gates"]["G0"] == "failed"
    ev = db.connect().execute("SELECT payload FROM events WHERE run_id=? AND type='gate.result'", (v["run_id"],)).fetchone()[0]
    assert '"unclear_type"' in ev


def test_bug5_assessment_and_policy_are_written_in_the_create_transaction(monkeypatch):
    # no second save_run after the job is committed: it could overwrite a worker that already leased the run
    saves = []
    monkeypatch.setattr(db, "save_run", lambda c, v: saves.append(v.run_id))
    v = post(monkeypatch, check(policy="forbidden")).json()
    assert saves == [] and v["assessment"]["handling_decision"] == "READY" and "repo_forbids_ai" in v["publish_blockers"]
    stored = db.get_run(db.connect(), v["run_id"])
    assert stored.assessment is not None and stored.policy.ai_policy == "forbidden"


# ---- A's second review of #50 ----
def test_saved_assessment_says_saved_not_ready(monkeypatch):
    from backend.report import render
    v = post(monkeypatch, check(), assessment_only=True).json()
    assert v["assessment"]["handling_decision"] == "ASSESSMENT_ONLY" and "saved_by_user" in v["assessment"]["decision_reasons"]
    assert "You saved this assessment" in render(db.get_run(db.connect(), v["run_id"]))


def test_unsupported_without_an_assessment_fails_closed(monkeypatch):
    chk = check(checks={**OK, "python": S.FAILED}, unsupported="not_python").model_copy(update={"assessment": None})
    assert post(monkeypatch, chk).status_code == 422


def test_warnings_accepted_at_the_start_are_not_an_issue_change_later(monkeypatch):
    # tablib#723 (d971a7b0): the user accepted linked_pr to start; at Approve the same PR made ISSUE_CHANGED, approval locked
    import json
    chk = check(warnings=("linked_pr",))
    v = post(monkeypatch, chk, continue_despite=["linked_pr"]).json()
    assert json.loads(db.get_kv(db.connect(), f"issue_change_accepted:{v['run_id']}")) == ["linked_pr"]
