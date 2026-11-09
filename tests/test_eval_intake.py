"""#70 item 11: the intake eval grades the proceed/stop decision; an error is never counted as right."""
import importlib
import json

E = importlib.import_module("scripts.eval_intake")


def test_grade():
    assert E.grade(["READY"], "READY") == {"exact": True, "direction": True}
    assert E.grade(["ALREADY_ADDRESSED", "HUMAN_DECISION"], "HUMAN_DECISION") == {"exact": True, "direction": True}
    assert E.grade(["ASSESSMENT_ONLY"], "HUMAN_DECISION") == {"exact": False, "direction": True}   # still stopped
    assert E.grade(["UNSUPPORTED"], "READY") == {"exact": False, "direction": False}               # proceeded on a stop
    assert E.grade(["READY"], None) == {"exact": False, "direction": False}                        # lookup failed


def test_main_writes_results_and_counts_errors_as_wrong(tmp_path, monkeypatch):
    from backend.contracts.models import IssueAssessment
    from backend.github.reader import GitHubError
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "intake_cases.json").write_text(json.dumps({"cases": [
        {"id": "a", "url": "u1", "kind": "k", "expected": ["UNSUPPORTED"]}, {"id": "b", "url": "u2", "kind": "k", "expected": ["READY"]}]}))
    a = IssueAssessment(issue_type="unknown", issue_type_source="none", issue_status="open", compatibility_status="unsupported",
                        handling_decision="UNSUPPORTED", decision_reasons=["unsupported:not_python"])
    class Chk:
        assessment, warnings, unsupported, suitability = a, [], "not_python", [{"dimension": "testability", "outcome": "blocker"}]
    def fake(url, extract_model=True):
        if url == "u2":
            raise GitHubError("GITHUB_UNAVAILABLE", "rate limited")
        return Chk()
    monkeypatch.setattr(E, "ROOT", tmp_path); monkeypatch.setattr(E, "check_issue", fake)
    monkeypatch.setattr("sys.argv", ["eval_intake.py", "--no-model"])
    E.main()
    res = json.loads((tmp_path / "eval" / "intake_results.json").read_text())
    assert res["summary"]["exact"] == 1 and res["summary"]["cases"] == 2 and res["summary"]["model"] is False
    assert res["results"][0]["suitability"] == {"testability": "blocker"} and res["results"][1]["error"].startswith("GITHUB_UNAVAILABLE")
