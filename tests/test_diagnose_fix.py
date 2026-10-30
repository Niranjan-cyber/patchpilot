"""B07: DIAGNOSE and FIX nodes with a fake sandbox and scripted agent results."""
import importlib

import pytest

from backend import artifacts, db
from backend.contracts.models import CheckStatus, IssueSpec, ReproTest
from backend.sandbox.docker import Result
from backend.worker.nodes import StepContext

D = importlib.import_module("backend.agents.diagnose")
F = importlib.import_module("backend.agents.fix")

SRC = "diff --git a/src/calc.py b/src/calc.py\n--- a/src/calc.py\n+++ b/src/calc.py\n@@ -1 +1 @@\n-    return 0\n+    raise ZeroDivisionError\n"
TEST_EDIT = "diff --git a/tests/test_calc.py b/tests/test_calc.py\n--- a/tests/test_calc.py\n+++ b/tests/test_calc.py\n@@ -1 +1 @@\n-x\n+y\n"


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="divide"), "sha")
    ev = [artifacts.put("transcript"), artifacts.put("test diff"), artifacts.put("FAILED run 1"), artifacts.put("FAILED run 2")]
    v.repro = ReproTest(test_diff_id=ev[1], test_ids=["tests/test_patchpilot_issue_1.py::t"], expected_failure="x",
                        runs_on_base=[CheckStatus.FAILED] * 2, evidence_ids=ev)
    db.save_run(db.connect(), v)
    for m in (D, F):
        monkeypatch.setattr(m.docker, "start", lambda *a: Result(0, "id"))
        monkeypatch.setattr(m.docker, "rm", lambda *a: None)
    monkeypatch.setattr(F, "limits", lambda: {"retries": {"fixer": 3}})
    monkeypatch.setattr("backend.agents.bisect.run_bisect", lambda run, diff: {"status": "not_run", "reason": "test"})  # no network in unit tests
    events = []
    ctx = StepContext(v.run_id, db.get_run(db.connect(), v.run_id), lambda t, s=None, **p: events.append((t, p)))
    return ctx, monkeypatch, ev, events


def lines(n):   # fake sandbox: every file exists with n lines, except missing.py
    return lambda name, cmd, timeout=0: Result(1, "") if "missing.py" in cmd else Result(0, f"{n}\n")


def test_valid_diagnosis_is_saved_with_real_citations(run):
    ctx, mp, ev, events = run
    mp.setattr(D.docker, "exec_", lines(40))
    mp.setattr(D.loop, "run", lambda *a, **k: ({"hypothesis": "divide returns 0 instead of raising.",
                                               "locations": [{"path": "src/calc.py", "line": 12}],
                                               "tour": [{"path": "src/calc.py", "why": "the division"}],
                                               "evidence_ids": [ev[2]]}, []))
    assert D.diagnose(ctx) is None
    d = db.get_run(db.connect(), ctx.run_id).diagnosis
    assert d.locations[0].path == "src/calc.py" and d.locations[0].line == 12 and ev[2] in d.evidence_ids
    assert "end_reason" not in ctx.scratch


def test_cited_id_without_sha256_prefix_is_matched_to_the_menu(run):
    # run a863ee86: gpt-oss cited the right IDs minus "sha256:" twice -> TRIAGE_ONLY on a correct diagnosis
    ctx, mp, ev, events = run
    mp.setattr(D.docker, "exec_", lines(40))
    bare = ev[2].removeprefix("sha256:")
    mp.setattr(D.loop, "run", lambda *a, **k: ({"hypothesis": "divide returns 0.", "locations": [{"path": "src/calc.py", "line": 12}],
                                               "evidence_ids": [bare, "sha256:" + "0" * 64]}, []))
    D.diagnose(ctx)   # a made-up full ID alongside still fails: only bare hashes that ARE on the menu are matched
    assert [p["reason"] for t, p in events if t == "attempt.retry"] == ["unknown_evidence_id"] * 2
    mp.setattr(D.loop, "run", lambda *a, **k: ({"hypothesis": "divide returns 0.", "locations": [{"path": "src/calc.py", "line": 12}],
                                               "evidence_ids": [bare]}, []))
    D.diagnose(ctx)
    assert db.get_run(db.connect(), ctx.run_id).diagnosis.evidence_ids[0] == ev[2]   # stored in the full form


def test_invalid_twice_ends_triage_with_diagnosis_unavailable(run):
    ctx, mp, ev, events = run
    calls = []
    mp.setattr(D.docker, "exec_", lines(40))
    mp.setattr(D.loop, "run", lambda *a, **k: (calls.append(1), ({"hypothesis": "h", "locations": [{"path": "src/calc.py", "line": 1}],
                                                                "evidence_ids": ["made-up-id"]}, []))[1])
    D.diagnose(ctx)
    assert len(calls) == 2                                          # one Investigator retry
    assert ctx.scratch["end_reason"] == "retries_exhausted" and ctx.scratch["status"] == "failed"
    assert db.get_run(db.connect(), ctx.run_id).diagnosis is None
    assert [p["reason"] for t, p in events if t == "attempt.retry"] == ["unknown_evidence_id"] * 2


def test_location_past_end_of_file_is_rejected(run):
    ctx, mp, ev, events = run
    mp.setattr(D.docker, "exec_", lines(5))
    mp.setattr(D.loop, "run", lambda *a, **k: ({"hypothesis": "h", "locations": [{"path": "src/calc.py", "line": 99}],
                                               "evidence_ids": [ev[2]]}, []))
    D.diagnose(ctx)
    assert [p["reason"] for t, p in events if t == "attempt.retry"][0] == "line_out_of_range"


def _fix_exec(diffs):
    it = iter(diffs)
    return lambda name, cmd, timeout=0: Result(0, next(it)) if "git diff --cached" in cmd else Result(0, "")


def test_fix_rejects_test_edit_then_accepts_source_fix(run):
    ctx, mp, ev, events = run
    mp.setattr(F.docker, "exec_", _fix_exec([SRC + TEST_EDIT, SRC]))
    mp.setattr(F.loop, "run", lambda *a, **k: ({"summary": "raise instead of returning 0"}, []))
    r = F.fix(ctx)
    assert r.gate == "G4" and r.status == CheckStatus.PASSED
    p = db.get_run(db.connect(), ctx.run_id).patch
    assert p.attempt == 2 and artifacts.get(p.fix_diff_id).decode() == SRC and p.test_diff_id == ev[1]
    assert [p["reason"] for t, p in events if t == "attempt.retry"] == ["edits_tests"]


def test_fix_gives_up_after_all_attempts_with_g4_failed(run):
    ctx, mp, ev, events = run
    mp.setattr(F.docker, "exec_", _fix_exec([TEST_EDIT] * 4))
    mp.setattr(F.loop, "run", lambda *a, **k: ({"summary": "s"}, []))
    r = F.fix(ctx)
    assert r.status == CheckStatus.FAILED and r.reason == "edits_tests"
    assert len([1 for t, _ in events if t == "attempt.retry"]) == 4          # 1 + 3 retries, each counted
    assert db.get_run(db.connect(), ctx.run_id).patch is None


def test_fix_without_reproduction_is_not_run(run):
    ctx, mp, ev, events = run
    ctx.run.repro = None
    assert F.fix(ctx).status == CheckStatus.NOT_RUN


def test_graph_never_shows_failed_diagnose_as_passed(tmp_path, monkeypatch):
    from backend.contracts.models import StepId
    from backend.worker import graph, nodes
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t"), "sha")
    monkeypatch.setitem(nodes.NODES, StepId.DIAGNOSE, lambda ctx: ctx.scratch.update(status="failed", end_reason="retries_exhausted"))
    out = graph._step_node(StepId.DIAGNOSE)({"run_id": v.run_id})
    assert out["end_reason"] == "retries_exhausted"
    assert db.get_run(db.connect(), v.run_id).steps[StepId.DIAGNOSE].status == CheckStatus.FAILED


def test_g4_exhausted_stops_the_run_as_triage_only():
    from backend.contracts.models import EndReason, Outcome, decide_outcome
    from backend.worker.graph import STOP_EARLY
    assert CheckStatus.FAILED in STOP_EARLY["G4"]
    gates = {"G1": CheckStatus.PASSED, "G2": CheckStatus.PASSED, "G3": CheckStatus.PASSED, "G4": CheckStatus.FAILED}
    assert decide_outcome(gates, EndReason.RETRIES_EXHAUSTED, diagnosis_valid=True) == Outcome.TRIAGE_ONLY


# --- the codebase tour is shown as links into the pinned source (bug:P1) ---

SOURCE = {"src/tinycalc/ops.py": 40, "tests/test_ops.py": 12}


def _lines(path):
    return SOURCE.get(path)


def _res(tour):
    return {"hypothesis": "divide() does not guard a zero denominator",
            "locations": [{"path": "src/tinycalc/ops.py", "line": 12}],
            "evidence_ids": ["ev1"], "tour": tour}


def test_a_tour_file_that_is_not_in_the_source_is_dropped():
    from backend.gates.diff_policy import keep_tour
    tour = [{"path": "src/tinycalc/ops.py", "why": "divide lives here"},
            {"path": "tests/test_invented.py", "why": "expects a ZeroDivisionError"}]
    kept, dropped = keep_tour(tour, _lines)
    assert [t["path"] for t in kept] == ["src/tinycalc/ops.py"]
    assert dropped == ["tests/test_invented.py"]


@pytest.mark.parametrize("path", ["/etc/shadow", "../../etc/passwd", "src/../../x.py", "", "   "])
def test_an_absolute_or_escaping_tour_path_is_dropped(path):
    from backend.gates.diff_policy import keep_tour
    kept, dropped = keep_tour([{"path": path, "why": "nope"}], _lines)
    assert kept == [] and dropped == [path]


def test_a_bad_tour_item_does_not_fail_the_whole_diagnosis():
    # The hypothesis and locations are validated separately: dropping a tour
    # item must not turn a good diagnosis into TRIAGE_ONLY.
    from backend.gates.diff_policy import check_diagnosis, keep_tour
    res = _res([{"path": "tests/test_invented.py", "why": "x"}])
    assert check_diagnosis(res, {"ev1"}, _lines) is None
    assert keep_tour(res["tour"], _lines)[0] == []


def test_a_malformed_tour_entry_is_ignored():
    from backend.gates.diff_policy import keep_tour
    kept, dropped = keep_tour(["tests/test_ops.py", None, 7], _lines)
    assert kept == [] and dropped == []


def test_locations_are_still_validated_against_the_source():
    from backend.gates.diff_policy import check_diagnosis
    bad = _res([])
    bad["locations"] = [{"path": "src/invented.py", "line": 1}]
    assert check_diagnosis(bad, {"ev1"}, _lines) == "unknown_file"
    deep = _res([])
    deep["locations"] = [{"path": "../../etc/passwd", "line": 1}]
    assert check_diagnosis(deep, {"ev1"}, _lines) == "unknown_file"
