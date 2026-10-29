from backend.agents.verify import evaluate_g5
from backend.contracts.models import CheckStatus as C

BASE = ["tests/test_ops.py::test_add", "tests/test_ops.py::test_sub"]
NEW = ["tests/test_patchpilot_issue_1.py::test_raises"]
ok = {**{t: True for t in BASE}, NEW[0]: True}


def test_passes_when_new_test_green_twice_and_no_regressions():
    assert evaluate_g5(NEW, BASE, ok, {NEW[0]: True})[:2] == (C.PASSED, "verified")


def test_regression_fails():
    st, reason, regs = evaluate_g5(NEW, BASE, {**ok, BASE[1]: False}, {NEW[0]: True})
    assert (st, reason, regs) == (C.FAILED, "regression", [BASE[1]])


def test_baseline_test_missing_counts_as_regression():
    st, _, regs = evaluate_g5(NEW, BASE, {BASE[0]: True, NEW[0]: True}, {NEW[0]: True})
    assert st == C.FAILED and regs == [BASE[1]]          # unknown is not a pass


def test_new_test_still_failing():
    assert evaluate_g5(NEW, BASE, {**ok, NEW[0]: False}, {NEW[0]: False})[:2] == (C.FAILED, "new_test_fails")


def test_flaky_new_test_is_inconclusive():
    assert evaluate_g5(NEW, BASE, ok, {NEW[0]: False})[:2] == (C.INCONCLUSIVE, "flaky_1_of_2")


def test_no_results_is_not_a_pass():
    assert evaluate_g5(NEW, BASE, {}, {})[0] == C.FAILED


import importlib

import pytest

V = importlib.import_module("backend.agents.verify")


@pytest.fixture
def loop(monkeypatch):
    calls = {"fix": 0, "diag": 0}
    D, F = importlib.import_module("backend.agents.diagnose"), importlib.import_module("backend.agents.fix")
    monkeypatch.setattr(F, "fix", lambda ctx: (calls.__setitem__("fix", calls["fix"] + 1), None)[1])
    monkeypatch.setattr(D, "diagnose", lambda ctx: calls.__setitem__("diag", calls["diag"] + 1))
    monkeypatch.setattr(V, "limits", lambda: {"retries": {"fixer": 3, "rediagnose": 1}})
    monkeypatch.setattr(V.db, "get_run", lambda c, rid: type("R", (), {"verify": type("V", (), {"regressions": []})()})())
    from backend.worker.nodes import StepContext
    ctx = StepContext("r", None, lambda *a, **k: None)
    return ctx, calls, monkeypatch


def results(*sts):
    it = iter(sts)
    return lambda ctx: V.GateResult(gate="G5", status=next(it), reason="new_test_fails")


def test_first_verify_passes(loop):
    ctx, calls, mp = loop
    mp.setattr(V, "_verify_once", results(C.PASSED))
    assert V.verify(ctx).status == C.PASSED and calls == {"fix": 0, "diag": 0}


def test_fixer_retry_then_pass_passes_feedback(loop):
    ctx, calls, mp = loop
    mp.setattr(V, "_verify_once", results(C.FAILED, C.PASSED))
    assert V.verify(ctx).status == C.PASSED and calls["fix"] == 1 and "still fails" in ctx.scratch["verify_feedback"]


def test_three_fixes_then_one_rediagnosis_then_triage(loop):
    ctx, calls, mp = loop
    mp.setattr(V, "_verify_once", results(*[C.FAILED] * 6))
    assert V.verify(ctx).status == C.FAILED and calls == {"fix": 4, "diag": 1}
