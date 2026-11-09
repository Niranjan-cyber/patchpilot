"""#70 item 11: the intake eval grades the proceed/stop decision. Unknown (a failed lookup, no model answer) is graded null
and counted apart: never right, never wrong (A's review of #89)."""
import importlib
import json

import pytest

E = importlib.import_module("scripts.eval_intake")


def test_grade():
    assert E.grade(["READY"], "READY") == {"exact": True, "direction": True}
    assert E.grade(["ALREADY_ADDRESSED", "HUMAN_DECISION"], "HUMAN_DECISION") == {"exact": True, "direction": True}
    assert E.grade(["ASSESSMENT_ONLY"], "HUMAN_DECISION") == {"exact": False, "direction": True}   # still stopped
    assert E.grade(["UNSUPPORTED"], "READY") == {"exact": False, "direction": False}               # proceeded on a stop
    assert E.grade(["READY"], None) == {"exact": None, "direction": None}                          # unknown, not wrong


def test_a_correct_stop_case_never_accepts_ready():
    cases = json.loads((E.ROOT / "eval" / "intake_cases.json").read_text(encoding="utf-8"))["cases"]
    for c in cases:
        if "correct to stop" in c["kind"]:
            assert "READY" not in c["expected"], c["id"]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from backend.contracts.models import IssueAssessment
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "intake_cases.json").write_text(json.dumps({"cases": [
        {"id": "a", "url": "u1", "kind": "k", "expected": ["UNSUPPORTED"]}, {"id": "b", "url": "u2", "kind": "k", "expected": ["READY"]},
        {"id": "c", "url": "u3", "kind": "k", "expected": ["HUMAN_DECISION"]}]}))
    mk = lambda d, r: IssueAssessment(issue_type="unknown", issue_type_source="none", issue_status="open",
                                      compatibility_status="unsupported", handling_decision=d, decision_reasons=r)
    class Chk:
        warnings, unsupported, suitability = [], "not_python", [{"dimension": "testability", "outcome": "blocker"}]
        def __init__(self, a): self.assessment = a
    monkeypatch.setattr(E, "ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_READ_TOKEN", "x")
    return tmp_path, mk, Chk


def test_errors_and_missing_model_answers_are_unknown_not_scored(setup, monkeypatch):
    from backend.github.reader import GitHubError
    tmp_path, mk, Chk = setup
    def fake(url, extract_model=True):
        if url == "u2":
            raise GitHubError("GITHUB_UNAVAILABLE", "GitHub didn't answer.")
        if url == "u3":   # the model didn't answer, so HUMAN_DECISION is a fallback, not the intake's verdict
            return Chk(mk("HUMAN_DECISION", ["model_unavailable"]))
        return Chk(mk("UNSUPPORTED", ["unsupported:not_python"]))
    monkeypatch.setattr(E, "check_issue", fake)
    monkeypatch.setattr("sys.argv", ["eval_intake.py"])
    E.main()
    s = json.loads((tmp_path / "eval" / "intake_results.json").read_text())["summary"]
    assert (s["cases"], s["graded"], s["exact"], s["errors"], s["model_unanswered"]) == (3, 1, 1, 1, 1)
    assert "READY" in s["limitation"]


def test_a_rate_limit_stops_the_run_and_no_model_runs_get_their_own_file(setup, monkeypatch):
    from backend.github.reader import GitHubError
    tmp_path, mk, Chk = setup
    calls = []
    def fake(url, extract_model=True):
        calls.append(url)
        raise GitHubError("GITHUB_UNAVAILABLE", "GitHub is rate-limiting us. Try again in 5 min.", 300)
    monkeypatch.setattr(E, "check_issue", fake)
    monkeypatch.setattr("sys.argv", ["eval_intake.py", "--no-model"])
    E.main()
    assert calls == ["u1"]   # stopped after the first rate limit
    res = json.loads((tmp_path / "eval" / "intake_results_no_model.json").read_text())
    assert res["summary"]["graded"] == 0 and res["results"][1]["error"].startswith("not run")
    assert not (tmp_path / "eval" / "intake_results.json").exists()   # a keyword-only run never replaces a model run


def test_no_token_fails_fast(setup, monkeypatch):
    monkeypatch.delenv("GITHUB_READ_TOKEN")
    with pytest.raises(SystemExit):
        E.main()
