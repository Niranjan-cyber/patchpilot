"""B17: hidden-variant result can only lower readiness; bisect never guesses a commit."""
from backend.agents.bisect import bisect, probe_result
from backend.agents.variant import review_concern, variant_result
from backend.contracts.models import CheckStatus, EndReason, Outcome, Verification, decide_outcome

FAILED = "FAILED tests/test_patchpilot_hidden_1.py::test_v - AssertionError: assert 0 == 1\n1 failed in 0.1s\n"
PASSED = "tests/test_patchpilot_hidden_1.py .\n1 passed in 0.1s\n"
IMPORT = "E   ModuleNotFoundError: No module named 'x'\n1 error in 0.1s\n"


def test_probe_result():
    assert probe_result(FAILED) == "fail"
    assert probe_result(PASSED) == "pass"
    assert probe_result(IMPORT) is None              # can't tell -> never counted as good or bad
    assert probe_result("") is None
    assert probe_result("1 failed, 1 error in 0.2s") is None


def test_variant_result_only_counts_when_it_fails_on_the_original():
    assert variant_result(FAILED, PASSED) == (CheckStatus.PASSED, "ok")
    assert variant_result(FAILED, FAILED) == (CheckStatus.FAILED, "fix_fails_hidden_variant")
    assert variant_result(PASSED, PASSED) == (CheckStatus.NOT_RUN, "variant_not_failing_on_base")
    assert variant_result(FAILED, IMPORT) == (CheckStatus.INCONCLUSIVE, "variant_run_unclear")


def test_hidden_variant_can_only_lower_readiness():
    assert review_concern(Verification(hidden_variant=CheckStatus.FAILED))["severity"] == "high"
    for hv in (CheckStatus.PASSED, CheckStatus.NOT_RUN, CheckStatus.INCONCLUSIVE, None):
        assert review_concern(Verification(hidden_variant=hv)) is None     # never raises readiness, never invents a pass
    assert review_concern(None) is None
    gates = {g: CheckStatus.PASSED for g in ("G1", "G2", "G3", "G4", "G5", "G6")}
    # wired through the Reviewer: a concern turns VERIFIED_FIX into FIX_NEEDS_ATTENTION
    assert decide_outcome(gates, EndReason.COMPLETED, review_concerns=True) == Outcome.FIX_NEEDS_ATTENTION
    assert decide_outcome(gates, EndReason.COMPLETED, review_concerns=False) == Outcome.VERIFIED_FIX


C = [f"c{i}" for i in range(16)]    # newest (base, bad) -> oldest


def oracle(first_bad_index):
    probes = []
    def probe(sha):
        probes.append(sha)
        return "fail" if C.index(sha) <= first_bad_index else "pass"
    return probe, probes


def test_bisect_finds_first_bad_commit():
    probe, probes = oracle(5)
    r = bisect(C, probe, cap=6)
    assert r["status"] == "found" and r["first_bad"] == "c5" and r["last_good"] == "c6"
    assert probes[0] == "c15" and len(probes) <= 6


def test_bisect_over_the_cap_is_not_run_never_a_guess():
    probe, _ = oracle(5)
    r = bisect(C, probe, cap=2)
    assert r["status"] == "not_run" and r["reason"] == "step_cap" and r["first_bad"] is None


def test_bisect_no_passing_commit_in_range():
    r = bisect(C, lambda sha: "fail", cap=6)
    assert r["status"] == "not_run" and r["reason"] == "no_passing_commit_in_range" and r["first_bad"] is None


def test_bisect_unclear_probe_is_inconclusive():
    r = bisect(C, lambda sha: None if sha != "c15" else "pass", cap=6)
    assert r["status"] == "inconclusive" and r["first_bad"] is None and r["probes"][-1]["result"] is None


def test_bisect_without_history():
    assert bisect(["c0"], lambda s: "pass", cap=6)["reason"] == "no_history"


def test_api_bisect_owner_checked(tmp_path, monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from backend import db
    from backend.api import main
    from backend.contracts.models import IssueSpec
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t"), "s")
    c = TestClient(main.app, base_url="https://testserver")
    assert c.get(f"/api/runs/{v.run_id}/bisect").status_code == 404                 # not the owner
    monkeypatch.setattr(main, "_own", lambda request, r: None)
    assert c.get(f"/api/runs/{v.run_id}/bisect").json()["status"] == "pending"
    db.put_kv(db.connect(), f"bisect:{v.run_id}", json.dumps({"status": "not_run", "reason": "step_cap", "first_bad": None}))
    assert c.get(f"/api/runs/{v.run_id}/bisect").json() == {"status": "not_run", "reason": "step_cap", "first_bad": None, "variant": None}


def test_bisect_respects_the_run_time_budget():
    assert bisect(C, lambda s: "pass", cap=6, time_left=lambda: 120)["reason"] == "time_budget"     # < 5 min: skip
    left = iter([900, 900, 100] + [100] * 10)
    probe, probes = oracle(5)
    r = bisect(C, probe, cap=6, time_left=lambda: next(left))
    assert r["status"] == "not_run" and r["reason"] == "time_budget" and r["first_bad"] is None and len(probes) == 2


def test_bisect_requires_parent_child_pair_and_honours_stop():
    probe, _ = oracle(5)
    linear = bisect(C, probe, cap=6, parent_of=lambda sha: [C[C.index(sha) + 1]])
    assert linear["status"] == "found" and linear["first_bad"] == "c5"
    probe, _ = oracle(5)
    merged = bisect(C, probe, cap=6, parent_of=lambda sha: ["some-other-branch"])
    assert merged["status"] == "inconclusive" and merged["reason"] == "non_linear_history" and merged["first_bad"] is None
    assert bisect(C, lambda s: "pass", cap=6, stopped=lambda: True)["reason"] == "stopped"


def test_hidden_variant_error_is_not_run_with_reason(tmp_path, monkeypatch):
    import json
    from backend import db
    from backend.agents import variant as V
    from backend.contracts.models import IssueSpec
    from backend.worker.nodes import StepContext
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t"), "s")
    v.verify = Verification(new_test_runs=[CheckStatus.PASSED] * 2)
    db.save_run(db.connect(), v)
    def boom(rid): raise RuntimeError("docker died")
    monkeypatch.setattr(V, "_hidden_variant", boom)
    events = []
    assert V.hidden_variant(StepContext(v.run_id, v, lambda t, s=None, **p: events.append(p))) == CheckStatus.NOT_RUN
    assert db.get_run(db.connect(), v.run_id).verify.hidden_variant == CheckStatus.NOT_RUN       # never left None
    assert json.loads(db.get_kv(db.connect(), f"variant:{v.run_id}"))["reason"] == "error: RuntimeError"
    assert "not_run" in events[-1]["message"]
