import pytest
from fastapi.testclient import TestClient

from backend import artifacts, db
from backend.api import approval, main
from backend.contracts.models import (CheckStatus, IssueSpec, Location, Outcome, Patch, PublishBlocker, RepoPolicy, RunStatus,
                                      SGReport)
from backend.github.reader import IssueCheck

URL = "https://github.com/o/r/issues/1"
FIX = "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
TEST = "diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -0,0 +1 @@\n+def test(): pass\n"
OK = {"read_diff": True, "understands_change": True, "ai_note_ok": True}
OWN = {"what_was_broken": "Division by zero returned None silently.", "why_this_fix": "It now raises ZeroDivisionError like the docs say.", "what_the_test_proves": "The new test fails on the old code and passes now."}


@pytest.fixture
def ready(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    chk = IssueCheck(issue=IssueSpec(html_url=URL, repo="o/r", number=1, title="t"), base_sha="abc", default_branch="main",
                     language="Python", policy=RepoPolicy(), fetched_at=db.now())
    monkeypatch.setattr(main, "check_issue", lambda url: chk)
    stale = []
    monkeypatch.setattr(approval, "stale_checks", lambda v, d: list(stale))
    b = TestClient(main.app, base_url="https://testserver")
    rid = b.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    c = db.connect(); v = db.get_run(c, rid)
    v.status, v.outcome = RunStatus.AWAITING_APPROVAL, Outcome.VERIFIED_FIX
    v.gates = {"G5": CheckStatus.PASSED}; v.publish_blockers = [PublishBlocker.NOT_APPROVED]
    v.patch = Patch(fix_diff_id=artifacts.put(FIX), test_diff_id=artifacts.put(TEST), attempt=1, policy_result=CheckStatus.PASSED)
    v.supplyguard = SGReport(report_id="sha256:" + "1" * 64, status=CheckStatus.PASSED)
    db.save_run(c, v)
    return b, rid, stale


def body(ctx, **kw):
    return {"revision": ctx["revision"], "diff_hash": ctx["diff_hash"], "evidence_hash": ctx["evidence_hash"],
            "checklist": OK, "explanation": "it raises now", "ownership": OWN, "pr_title": "t", "pr_summary": "s", **kw}


def test_approve_records_exact_hashes(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    assert ctx["files"] == ["src/a.py", "tests/test_a.py"]
    r = b.post(f"/api/runs/{rid}/approve", json=body(ctx))
    assert r.status_code == 200
    v = r.json()
    assert v["approval"]["diff_hash"] == ctx["diff_hash"] and v["approval"]["explanation"] == "it raises now"
    assert "not_approved" not in v["publish_blockers"]


def test_checklist_required(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    r = b.post(f"/api/runs/{rid}/approve", json=body(ctx, checklist={**OK, "ai_note_ok": False}))
    assert r.status_code == 422 and r.json()["code"] == "CHECKLIST_INCOMPLETE"


def test_stale_hash_refused(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    r = b.post(f"/api/runs/{rid}/approve", json=body(ctx, diff_hash="sha256:" + "0" * 64))
    assert r.status_code == 409 and r.json()["code"] == "APPROVAL_STALE"


def test_upstream_change_is_permanent(ready):
    b, rid, stale = ready
    stale.append(PublishBlocker.UPSTREAM_CHANGED)
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    r = b.post(f"/api/runs/{rid}/approve", json=body(ctx))
    assert r.status_code == 409 and r.json()["code"] == "UPSTREAM_CHANGED"
    assert b.get(f"/api/runs/{rid}").json()["status"] == "finished"


def test_recheck_deps_voids_approval(ready, monkeypatch):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    b.post(f"/api/runs/{rid}/approve", json=body(ctx))
    from backend.sandbox import steps
    monkeypatch.setattr(steps, "run_supplyguard", lambda r: SGReport(report_id="sha256:" + "2" * 64, status=CheckStatus.PASSED))
    v = b.post(f"/api/runs/{rid}/recheck-deps").json()
    assert v["approval"] is None and "not_approved" in v["publish_blockers"]
    assert b.get(f"/api/runs/{rid}/approval").json()["evidence_hash"] != ctx["evidence_hash"]


def test_revise_voids_and_queues(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    b.post(f"/api/runs/{rid}/approve", json=body(ctx))
    v = b.post(f"/api/runs/{rid}/revise", json={"feedback": "keep the public name"}).json()
    assert v["revision"] == 1 and v["status"] == "revising" and v["approval"] is None and len(v["revisions"]) == 1
    assert db.connect().execute("SELECT COUNT(*) FROM jobs WHERE kind='revise' AND state='queued'").fetchone()[0] == 1


def test_revise_can_target_the_test(ready):
    b, rid, _ = ready
    assert b.post(f"/api/runs/{rid}/revise", json={"feedback": "drop the zstd check", "target": "tests"}).status_code == 422
    v = b.post(f"/api/runs/{rid}/revise", json={"feedback": "drop the zstd check", "target": "test"}).json()
    assert v["status"] == "revising" and v["revisions"][-1]["revise_target"] == "test"
    assert v["revisions"][-1]["feedback"] == "drop the zstd check"


def test_revise_refused_when_run_budget_spent(ready, monkeypatch):
    """rev 1 of 3e1efde6 ended at once with budget_run: say so up front instead of queueing a revision that can't run."""
    from backend import llm_gateway
    b, rid, _ = ready
    assert b.get(f"/api/runs/{rid}/approval").json()["revise_blocked"] is None
    monkeypatch.setattr(llm_gateway, "tokens_used", lambda run_id=None, day=None: 10**9)
    assert "AI budget" in b.get(f"/api/runs/{rid}/approval").json()["revise_blocked"]
    r = b.post(f"/api/runs/{rid}/revise", json={"feedback": "keep the public name"})
    assert r.status_code == 409 and r.json()["code"] == "BUDGET_SPENT"
    assert db.get_run(db.connect(), rid).status == RunStatus.AWAITING_APPROVAL
    assert db.connect().execute("SELECT COUNT(*) FROM jobs WHERE kind='revise'").fetchone()[0] == 0


def test_other_browser_cannot_approve(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    other = TestClient(main.app, base_url="https://testserver")
    assert other.post(f"/api/runs/{rid}/approve", json=body(ctx)).status_code == 404


def test_diff_download_is_owner_only(ready):
    b, rid, _ = ready
    r = b.get(f"/api/runs/{rid}/diff.patch")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"] and "+x = 2" in r.text
    assert TestClient(main.app, base_url="https://testserver").get(f"/api/runs/{rid}/diff.patch").status_code == 404


def test_ownership_answers_are_required_but_never_judged(ready):
    # contracts v0.5 §2.3 (human decision 2026-11-09): three answers, a minimum length only
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    r = b.post(f"/api/runs/{rid}/approve", json=body(ctx, ownership=None))
    assert r.status_code == 422 and r.json()["code"] == "OWNERSHIP_REQUIRED"
    assert b.post(f"/api/runs/{rid}/approve", json=body(ctx, ownership={**OWN, "why_this_fix": "short"})).status_code == 422
    odd = {**OWN, "why_this_fix": "I am honestly not sure, the AI did it."}   # an imperfect answer is still accepted
    v = b.post(f"/api/runs/{rid}/approve", json=body(ctx, ownership=odd)).json()
    assert v["approval"]["ownership"]["why_this_fix"] == odd["why_this_fix"]
    from backend.report import render
    assert "I am honestly not sure" in render(db.get_run(db.connect(), rid))


# #97 Contribution Explainer: every status is the recorded one; what didn't run says so
def explainer(b, rid):
    return b.get(f"/api/runs/{rid}/approval").json()["help"]["explainer"]


def test_explainer_shows_lint_that_never_ran_as_not_run(ready):
    b, rid, _ = ready
    e = explainer(b, rid)
    lint = [r for r in e["verification"] if r["id"] == "repo_check"]
    assert lint == [{"id": "repo_check", "tool": None, "status": "not_run", "reason": "not_run_yet"}]
    assert {"kind": "check", **lint[0]} in e["risks"]


def test_explainer_lists_a_failed_hidden_variant_under_risks(ready):
    from backend.contracts.models import ReproTest, Verification
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.gates = {"G3": CheckStatus.PASSED, "G4": CheckStatus.PASSED, "G5": CheckStatus.PASSED}
    v.repro = ReproTest(test_diff_id=v.patch.test_diff_id, test_ids=["tests/test_a.py::test"], expected_failure="assert 1 == 2",
                        runs_on_base=[CheckStatus.FAILED, CheckStatus.FAILED], uncovered=["negative numbers"])
    v.verify = Verification(new_test_runs=[CheckStatus.PASSED, CheckStatus.PASSED], hidden_variant=CheckStatus.FAILED)
    db.save_run(c, v)
    db.put_kv(c, f"repo_checks:{rid}", '{"checks": [{"tool": "ruff", "status": "PASS", "note": "no new problems"}], "files": [], "reason": null}')
    e = explainer(b, rid)
    status = {r.get("tool") or r["id"]: r["status"] for r in e["verification"]}
    assert status == {"reproduced": "passed", "fixed": "passed", "baseline": "not_run", "hidden_variant": "failed", "ruff": "passed",
                      "only_these_files": "passed", "supplyguard": "passed"}
    assert e["fix"]["only_these_files"] == "passed"
    risky = {r.get("id") or r["kind"] for r in e["risks"]}
    assert risky == {"hidden_variant", "baseline", "uncovered"}   # a passed check is never listed as a risk


def test_explainer_cites_the_pinned_commit_and_explains_needs_attention(ready):
    from backend.contracts.models import Diagnosis, Location, ReviewResult, TestRun
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.diagnosis = Diagnosis(hypothesis="x is set to 1, not 2.", locations=[Location(path="src/a.py", line=1), Location(path="src/b.py")],
                            evidence_ids=["sha256:" + "2" * 64])
    v.review = ReviewResult(concerns=[{"level": "IMPORTANT", "severity": "medium", "text": "No docstring update."},
                                      {"level": "ACCEPTED_TRADEOFF", "severity": "low", "text": "Keeps the old name."}])
    v.baseline = TestRun(pass_set=["t1", "t2"], fail_set=["t3"], partial=True)
    db.save_run(c, v)
    e = explainer(b, rid)
    assert e["root_cause"]["citations"] == [
        {"path": "src/a.py", "line": 1, "url": "https://github.com/o/r/blob/abc/src/a.py#L1"},
        {"path": "src/b.py", "line": None, "url": "https://github.com/o/r/blob/abc/src/b.py"}]
    assert e["root_cause"]["evidence"] == ["sha256:" + "2" * 64]
    assert [r["text"] for r in e["risks"] if r["kind"] == "review"] == ["No docstring update."]
    assert {"kind": "cap", "reason": "baseline_partial"} in e["risks"]
    base = next(r for r in e["verification"] if r["id"] == "baseline")
    assert base["counts"] == {"passed": 2, "failed": 1, "flaky": 0} and base["partial"] is True


def test_explainer_is_owner_only(ready):
    b, rid, _ = ready
    assert TestClient(main.app, base_url="https://testserver").get(f"/api/runs/{rid}/approval").status_code == 404


@pytest.mark.parametrize("bad", ["not json", "[1, 2]", '{"checks": [{"status": "PASS"}]}', '{"checks": "x"}'])
def test_a_malformed_record_never_blocks_the_diff(ready, bad):
    b, rid, _ = ready
    db.put_kv(db.connect(), f"repo_checks:{rid}", bad)
    db.put_kv(db.connect(), f"variant:{rid}", bad)
    r = b.get(f"/api/runs/{rid}/approval")
    assert r.status_code == 200 and "+x = 2" in r.json()["diff"]
    rows = [c for c in r.json()["help"]["explainer"]["verification"] if c["id"] == "repo_check"]
    assert rows == [{"id": "repo_check", "tool": None, "status": "not_run", "reason": "unreadable"}]   # #113: it ran, unreadable


def test_a_failing_explainer_leaves_approval_working(ready, monkeypatch):
    b, rid, _ = ready
    monkeypatch.setattr(approval, "explainer", lambda *a: 1 / 0)
    r = b.get(f"/api/runs/{rid}/approval")
    assert r.status_code == 200 and r.json()["help"]["explainer"] is None and r.json()["diff_hash"]


def test_each_risk_is_listed_once(ready, monkeypatch):
    # the Reviewer's code-written concerns, made by their real producers, restate facts the explainer already lists
    from backend.agents import lint
    from backend.agents.variant import review_concern
    from backend.contracts.models import ReproTest, ReviewResult, TestRun, Verification
    from backend.publisher.publisher import COVERAGE_NOTE
    monkeypatch.setattr(lint, "run_checks", lambda *a: {"checks": [{"tool": "ruff", "status": "FAIL", "new_count": 2, "new": ["E1", "E2"]}]})
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.verify = Verification(new_test_runs=[CheckStatus.PASSED] * 2, hidden_variant=CheckStatus.FAILED)
    v.repro = ReproTest(test_diff_id=v.patch.test_diff_id, test_ids=["t"], expected_failure="e", uncovered=["floats"])
    v.baseline = TestRun(pass_set=["t1"], partial=True)
    v.gates = {**v.gates, "G2": CheckStatus.INCONCLUSIVE, "G3": CheckStatus.PASSED, "G4": CheckStatus.PASSED}
    v.review = ReviewResult(concerns=[review_concern(v.verify), {"source": "coverage", "text": f"{COVERAGE_NOTE} its test checks 1 of the things: floats"},
                                      *lint.review_concerns(rid, "", ""), {"severity": "medium", "text": "Renames a public function."}])
    db.save_run(c, v)
    db.put_kv(c, f"repo_checks:{rid}", '{"checks": [{"tool": "ruff", "status": "FAIL", "note": "2 new problems"}], "files": [], "reason": null}')
    risks = explainer(b, rid)["risks"]
    causes = [r.get("id") or r.get("reason") or r["kind"] for r in risks]
    assert sorted(causes) == ["baseline_partial", "hidden_variant", "repo_check", "review", "uncovered"]
    assert [r["text"] for r in risks if r["kind"] == "review"] == ["Renames a public function."]


def test_a_stale_variant_reason_is_not_shown(ready):
    from backend.contracts.models import Verification
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.verify = Verification(hidden_variant=None)   # a revision cleared it; kv still holds the old attempt's result
    db.save_run(c, v)
    db.put_kv(c, f"variant:{rid}", '{"status": "passed", "reason": "ok"}')
    row = next(r for r in explainer(b, rid)["verification"] if r["id"] == "hidden_variant")
    assert row == {"id": "hidden_variant", "status": "not_run", "reason": None, "evidence": []}
    db.put_kv(c, f"variant:{rid}", '{"status": "not_run", "reason": "no_variant_written"}')
    assert next(r for r in explainer(b, rid)["verification"] if r["id"] == "hidden_variant")["reason"] == "no_variant_written"


def test_citation_paths_are_quoted(ready):
    from backend.contracts.models import Diagnosis, Location
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.diagnosis = Diagnosis(hypothesis="h", locations=[Location(path="src/a b#1?.py", line=3)])
    db.save_run(c, v)
    assert explainer(b, rid)["root_cause"]["citations"][0]["url"] == "https://github.com/o/r/blob/abc/src/a%20b%231%3F.py#L3"


# #98: a visible suggestion per ownership question, from a code template over recorded fields only (no model call)
def suggestions(b, rid):
    return b.get(f"/api/runs/{rid}/approval").json()["help"]["suggestions"]


def test_without_a_diagnosis_the_suggestion_says_the_cause_is_unknown(ready):
    s = suggestions(*ready[:2])
    assert set(s) == set(OWN)   # the same three keys the approval takes
    assert "unknown" in s["why_this_fix"] and "src/a.py" in s["why_this_fix"]
    assert "Nothing was recorded" in s["what_was_broken"]   # the fixture recorded no expected/actual/test
    assert "No regression test was recorded" in s["what_the_test_proves"]


def test_suggestions_use_only_recorded_fields(ready):
    from backend.contracts.models import Diagnosis, IssueSpec, ReproTest, Verification
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.issue = IssueSpec(html_url=URL, repo="o/r", number=1, title="t", expected="x is 2", actual="x is 1")
    v.diagnosis = Diagnosis(hypothesis="x is assigned 1.", locations=[Location(path="src/a.py", line=1)])
    v.repro = ReproTest(test_diff_id=v.patch.test_diff_id, test_ids=["tests/test_a.py::test"], expected_failure="assert 1 == 2",
                        runs_on_base=[CheckStatus.FAILED, CheckStatus.FAILED], uncovered=["negative x"])
    v.verify = Verification(new_test_runs=[])
    v.gates = {"G3": CheckStatus.PASSED, "G5": CheckStatus.NOT_RUN}
    db.save_run(c, v)
    s = suggestions(b, rid)
    assert s["what_was_broken"] == ('The issue expects: x is 2. Instead: x is 1. The new test shows it: on the original code it fails '
                                    'with "assert 1 == 2".')
    assert s["why_this_fix"] == "PatchPilot's diagnosis (a claim, check it in the diff): x is assigned 1. The change edits src/a.py."
    assert s["what_the_test_proves"] == ("The new test tests/test_a.py::test fails on the original code (2 of 2 runs) and was not "
                                         "shown to pass with the fix (verification: not run). The hidden variant wasn't run. "
                                         "It doesn't check: negative x.")


def test_ownership_answers_stay_the_users_own(ready):
    # contracts §2.3: the suggestion is shown, never submitted for the user; the approval keeps the typed answers
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    hints = ctx["help"]["suggestions"]
    assert all(hints[k] for k in OWN)   # suggestions exist, yet empty answers are still refused
    empty = {k: "" for k in OWN}
    assert b.post(f"/api/runs/{rid}/approve", json=body(ctx, ownership=empty)).status_code == 422
    v = b.post(f"/api/runs/{rid}/approve", json=body(ctx)).json()
    assert v["approval"]["ownership"] == OWN and all(v["approval"]["ownership"][k] != hints[k] for k in OWN)


def test_a_lint_concern_stays_when_no_failed_row_shows_it(ready, monkeypatch):
    # no repo_checks record: the only place the user can see the lint failure is the Reviewer's concern
    from backend.agents import lint
    from backend.contracts.models import ReviewResult
    monkeypatch.setattr(lint, "run_checks", lambda *a: {"checks": [{"tool": "ruff", "status": "FAIL", "new_count": 1, "new": ["E1"]}]})
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.review = ReviewResult(concerns=lint.review_concerns(rid, "", ""))
    db.save_run(c, v)
    assert [r["kind"] for r in explainer(b, rid)["risks"] if "ruff" in str(r.get("text"))] == ["review"]


def test_every_check_that_did_not_pass_is_a_risk(ready):
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.gates = {"G2": CheckStatus.PASSED, "G3": CheckStatus.PASSED, "G4": CheckStatus.INCONCLUSIVE, "G5": CheckStatus.PASSED}
    v.supplyguard = None   # no dependency check result
    db.save_run(c, v)
    e = explainer(b, rid)
    status = {r["id"]: r["status"] for r in e["verification"]}
    assert status["only_these_files"] == "inconclusive" and status["supplyguard"] == "not_run"
    assert {"only_these_files", "supplyguard"} <= {r.get("id") for r in e["risks"]}


def test_a_flaky_baseline_is_not_hidden_behind_the_partial_cap(ready):
    from backend.contracts.models import TestRun
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.baseline = TestRun(pass_set=["t1"], flaky_set=["t2"], partial=True)
    v.gates = {**v.gates, "G2": CheckStatus.INCONCLUSIVE}
    db.save_run(c, v)
    ids = [r.get("id") or r.get("reason") for r in explainer(b, rid)["risks"]]
    assert "baseline" in ids and "baseline_partial" in ids



def _run_with(b, rid, **kw):
    from backend.contracts.models import Diagnosis, IssueSpec, ReproTest, Verification
    c = db.connect(); v = db.get_run(c, rid)
    v.issue = IssueSpec(html_url=URL, repo="o/r", number=1, title="t", expected=kw.get("expected"), actual=kw.get("actual"))
    v.repro = ReproTest(test_diff_id=v.patch.test_diff_id, test_ids=kw.get("tests", ["tests/test_a.py::test"]),
                        expected_failure="assert 1 == 2", runs_on_base=[CheckStatus.FAILED] * 2, uncovered=kw.get("uncovered", []))
    v.verify = Verification(new_test_runs=[CheckStatus.PASSED] * 2, hidden_variant=kw.get("variant", CheckStatus.PASSED),
                            regressions=kw.get("regressions", []))
    v.diagnosis = Diagnosis(hypothesis=kw["claim"]) if "claim" in kw else None
    v.gates = {"G3": kw.get("g3", CheckStatus.PASSED), "G5": CheckStatus.PASSED}
    db.save_run(c, v)
    return suggestions(b, rid)


def test_q1_claims_the_failure_only_when_reproduction_passed(ready):
    b, rid, _ = ready
    s = _run_with(b, rid, expected="x is 2", actual="x is 1", g3=CheckStatus.INCONCLUSIVE)
    assert s["what_was_broken"] == ('The issue expects: x is 2. Instead: x is 1. The test was written to fail with "assert 1 == 2", '
                                    "but that wasn't confirmed (reproduction: inconclusive).")
    s = _run_with(b, rid, expected="x is 2.", actual="x is 1.")   # a recorded period isn't doubled
    assert s["what_was_broken"] == ('The issue expects: x is 2. Instead: x is 1. The new test shows it: on the original code it '
                                    'fails with "assert 1 == 2".')


def test_q1_uses_whichever_side_was_recorded(ready):
    b, rid, _ = ready
    assert _run_with(b, rid, expected="x is 2")["what_was_broken"].startswith(
        "The issue expects: x is 2. The issue doesn't say what happens instead.")
    assert _run_with(b, rid, actual="x is 1", g3=CheckStatus.NOT_RUN)["what_was_broken"].startswith(
        "Instead of the right behaviour (the issue doesn't say what that is): x is 1.")


def test_q3_says_the_bug_cant_come_back_only_when_every_check_backs_it(ready):
    b, rid, _ = ready
    strong = "so the bug can't come back without it failing"
    assert strong in _run_with(b, rid)["what_the_test_proves"]
    s = _run_with(b, rid, variant=CheckStatus.FAILED)["what_the_test_proves"]
    assert strong not in s and s.endswith("but the fix fails a hidden variant of the test, so it may only cover the exact tested case.")
    s = _run_with(b, rid, regressions=["tests/test_b.py::t"])["what_the_test_proves"]
    assert strong not in s and "1 existing test broke" in s
    s = _run_with(b, rid, uncovered=None)["what_the_test_proves"]
    assert strong not in s and s.endswith("Coverage of the issue wasn't checked.")


def test_q3_names_every_test_and_q2_needs_a_real_claim(ready):
    b, rid, _ = ready
    s = _run_with(b, rid, tests=["t::a", "t::b"], claim="  ")
    assert s["what_the_test_proves"].startswith("The new tests t::a, t::b fail on the original code (2 of 2 runs)")
    assert s["why_this_fix"].startswith("The cause is unknown")
    assert _run_with(b, rid, claim="x is assigned 1")["why_this_fix"].startswith(
        "PatchPilot's diagnosis (a claim, check it in the diff): x is assigned 1. The change edits src/a.py.")


def test_failing_suggestions_leave_the_explainer(ready, monkeypatch):
    b, rid, _ = ready
    monkeypatch.setattr(approval, "suggestions", lambda *a: 1 / 0)
    h = b.get(f"/api/runs/{rid}/approval").json()["help"]
    assert h["suggestions"] is None and h["explainer"]["verification"]



# #108: code-written concerns carry a source tag; the explainer filters on the tag, never on wording
def test_a_reworded_concern_is_still_listed_once_and_untagged_text_is_never_hidden(ready):
    from backend.contracts.models import ReviewResult, Verification
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.verify = Verification(new_test_runs=[CheckStatus.PASSED] * 2, hidden_variant=CheckStatus.FAILED)
    v.review = ReviewResult(concerns=[
        {"severity": "high", "source": "variant", "text": "Any new wording for the variant failure."},           # tagged: shown as the row
        {"severity": "high", "text": "The fix passes the visible test but fails a hidden variant (model's own words)."}])   # untagged: kept
    db.save_run(c, v)
    assert [r["text"] for r in explainer(b, rid)["risks"] if r["kind"] == "review"] == [
        "The fix passes the visible test but fails a hidden variant (model's own words)."]


def test_revise_clears_the_previous_variant_record(ready):
    b, rid, _ = ready
    db.put_kv(db.connect(), f"variant:{rid}", '{"status": "not_run", "reason": "no_variant_written", "evidence": []}')
    assert b.post(f"/api/runs/{rid}/revise", json={"feedback": "keep the public name"}).status_code == 200
    assert db.get_kv(db.connect(), f"variant:{rid}") is None   # the next attempt can't show this attempt's reason


def test_variant_evidence_is_listed_under_the_variant_not_the_fix(ready):
    from backend.contracts.models import Verification
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    fix_ev, var_ev = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    v.verify = Verification(new_test_runs=[CheckStatus.PASSED] * 2, hidden_variant=CheckStatus.FAILED, evidence_ids=[fix_ev, var_ev])
    db.save_run(c, v)
    db.put_kv(c, f"variant:{rid}", f'{{"status": "failed", "reason": "fix_fails_hidden_variant", "evidence": ["{var_ev}"]}}')
    rows = {r["id"]: r for r in explainer(b, rid)["verification"]}
    assert rows["fixed"]["evidence"] == [fix_ev] and rows["hidden_variant"]["evidence"] == [var_ev]


@pytest.mark.parametrize("bad", ["not json", "[1]", '{"checks": [{"status": "PASS"}]}'])
def test_a_malformed_repo_checks_record_never_500s_the_report_or_the_api(ready, bad):
    b, rid, _ = ready
    db.put_kv(db.connect(), f"repo_checks:{rid}", bad)
    r = b.get(f"/api/runs/{rid}/report.md")
    assert r.status_code == 200 and "Not checked" in r.text
    assert b.get(f"/api/runs/{rid}/repo-checks").json()["checks"] is None   # unknown, never a list of passes


# #113 review round 1
def test_revise_clears_every_per_attempt_record(ready):
    b, rid, _ = ready
    for k in ("variant", "repo_checks", "bisect"):
        db.put_kv(db.connect(), f"{k}:{rid}", '{"status": "passed", "checks": [{"tool": "ruff", "status": "PASS"}]}')
    assert b.post(f"/api/runs/{rid}/revise", json={"feedback": "keep the public name"}).status_code == 200
    assert all(db.get_kv(db.connect(), f"{k}:{rid}") is None for k in ("variant", "repo_checks", "bisect"))
    assert b.get(f"/api/runs/{rid}/repo-checks").json()["reason"] == "not_run_yet"   # never the old diff's PASS


@pytest.mark.parametrize("ev", ["7", '"sha256:abc"', '{"a": 1}', '[1, "x"]'])
def test_a_malformed_variant_evidence_list_counts_as_none(ready, ev):
    from backend.contracts.models import Verification
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid)
    v.verify = Verification(new_test_runs=[CheckStatus.PASSED] * 2, hidden_variant=CheckStatus.FAILED, evidence_ids=["e1"])
    db.save_run(c, v)
    db.put_kv(c, f"variant:{rid}", f'{{"status": "failed", "reason": "fix_fails_hidden_variant", "evidence": {ev}}}')
    rows = {r["id"]: r for r in explainer(b, rid)["verification"]}
    assert rows["hidden_variant"]["evidence"] == [] and rows["fixed"]["evidence"] == ["e1"]


def test_a_corrupt_variant_record_never_500s_bisect(ready):
    b, rid, _ = ready
    db.put_kv(db.connect(), f"variant:{rid}", "not json")
    db.put_kv(db.connect(), f"bisect:{rid}", "also not json")
    r = b.get(f"/api/runs/{rid}/bisect")
    assert r.status_code == 200 and r.json()["variant"] is None and r.json()["status"] == "pending"


def test_an_unreadable_lint_record_says_so_not_not_run_yet(ready):
    b, rid, _ = ready
    db.put_kv(db.connect(), f"repo_checks:{rid}", '{"checks": "x"}')
    assert b.get(f"/api/runs/{rid}/repo-checks").json() == {"checks": None, "files": [], "reason": "unreadable"}
    row = next(r for r in explainer(b, rid)["verification"] if r["id"] == "repo_check")
    assert row["reason"] == "unreadable"
    assert "it ran, but its result couldn't be read" in b.get(f"/api/runs/{rid}/report.md").text


def _plan(c, rid, groups):
    import json
    eid = artifacts.put(json.dumps({"run_id": rid, "pr_url": "https://github.com/o/r/pull/9", "saved_at": "2026-11-11T10:00:00+00:00",
                                    "groups": groups}))
    db.put_kv(c, f"revision_plan:{rid}", eid)
    return eid


def _item(quote, **kw):
    return {"id": "review_comment:1", "source": "review", "author": "maint", "url": None, "quote": quote, "path": None, "line": None,
            "meaning": None, "change": None, **kw}


def test_revise_from_feedback_needs_a_readable_plan(ready):
    b, rid, _ = ready
    r = b.post(f"/api/runs/{rid}/revise-from-feedback")
    assert r.status_code == 409 and r.json()["code"] == "NO_PLAN"
    db.put_kv(db.connect(), f"revision_plan:{rid}", artifacts.put("not json"))
    assert b.post(f"/api/runs/{rid}/revise-from-feedback").json()["code"] == "NO_PLAN"
    assert db.get_run(db.connect(), rid).revision == 0   # nothing started


def test_revise_from_feedback_uses_the_quotes_records_the_plan_and_uses_it_once(ready):
    b, rid, _ = ready
    eid = _plan(db.connect(), rid, [{"category": "code_correctness", "label": "Code correctness",
                                     "items": [_item("Please keep the old name as an alias.", path="src/a.py", line=3,
                                                     meaning="wants backward compatibility", change="add alias")]}])
    v = b.post(f"/api/runs/{rid}/revise-from-feedback").json()
    last = v["revisions"][-1]
    assert v["status"] == "revising" and v["revision"] == 1 and last["revise_target"] == "fix"
    assert last["plan_evidence_id"] == eid and last["plan_saved_at"].startswith("2026-11-11T10:00")
    assert "maint (src/a.py:3): Please keep the old name as an alias." in last["feedback"]
    assert "Hint: wants backward compatibility; add alias" in last["feedback"]
    assert db.get_kv(db.connect(), f"revision_plan:{rid}") is None          # consumed
    assert b.post(f"/api/runs/{rid}/revise-from-feedback").status_code == 409


@pytest.mark.parametrize("cat", ["missing_test", "test_quality"])
def test_a_plan_that_asks_for_tests_starts_at_reproduce(ready, cat):
    b, rid, _ = ready
    _plan(db.connect(), rid, [{"category": "documentation", "label": "", "items": [_item("Add a docstring.")]},
                              {"category": cat, "label": "", "items": [_item("Test the empty input too.")]}])
    assert b.post(f"/api/runs/{rid}/revise-from-feedback").json()["revisions"][-1]["revise_target"] == "test"


def test_revise_from_feedback_keeps_the_revise_rules(ready):
    b, rid, _ = ready
    c = db.connect(); v = db.get_run(c, rid); v.status = RunStatus.RUNNING; db.save_run(c, v)
    _plan(c, rid, [{"category": "code_correctness", "label": "", "items": [_item("Rename it.")]}])
    assert b.post(f"/api/runs/{rid}/revise-from-feedback").json()["code"] == "NOT_REVISABLE"
    assert db.get_kv(db.connect(), f"revision_plan:{rid}")    # not consumed by a refused request


@pytest.mark.parametrize("state", ["merged", "closed"])
def test_no_revise_from_feedback_on_a_done_pr(ready, state):
    b, rid, _ = ready
    c = db.connect()
    _plan(c, rid, [{"category": "code_correctness", "label": "", "items": [_item("Rename it.")]}])
    db.put_kv(c, f"pr_track:{rid}", '{"state": "%s"}' % state)
    assert b.post(f"/api/runs/{rid}/revise-from-feedback").json()["code"] == "PR_DONE"
