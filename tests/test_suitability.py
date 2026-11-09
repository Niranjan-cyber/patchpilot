"""#70 item 7: suitability one dimension at a time, with whose words each piece of evidence is. No single score."""
import json

from backend import db
from backend.contracts.models import CheckStatus as S
from backend.github.assess import assess
from backend.github.suitability import ORDER, dimensions, report_lines

OK = {"open": S.PASSED, "public": S.PASSED, "python": S.PASSED, "tests_found": S.PASSED, "unassigned": S.PASSED, "no_linked_pr": S.PASSED}
BODY = "Calling `f(0)` raises:\n```\nZeroDivisionError: division by zero\n```\nIt should return None instead."
X = {"issue_type": "bug", "problem_summary": "f(0) crashes", "acceptance_conditions": ["f(0) returns None"]}


def run(*, title="f(0) crashes", body=BODY, labels=(), comments=(), issue=None, checks=None, unsupported=None, ai="unknown", linked=(), x=X):
    checks = checks or OK
    a = assess(title=title, body=body, labels=list(labels), names=["pyproject.toml", "tests"], state="open", checks=checks,
               unsupported=unsupported, warnings=[], linked=list(linked) if linked is not None else None, extracted=x)
    iss = {"user": {"login": "rep"}, "labels": [{"name": l} for l in labels], "assignees": [], **(issue or {})}
    d = dimensions(a=a, issue=iss, comments=list(comments) if comments is not None else None, checks=checks,
                   expected="return None" if "should" in body else None, actual="ZeroDivisionError" if "Error" in body else None,
                   unsupported=unsupported, ai_policy=ai)
    return {x["dimension"]: x for x in d}, [x["dimension"] for x in d]


def test_a_clear_bug_with_an_invite_label():
    d, order = run(labels=["bug", "help wanted"])
    assert order == ORDER
    assert {k: v["outcome"] for k, v in d.items()} == {
        "problem_clarity": "ok", "expected_behavior": "ok", "reproducibility": "ok", "technical_scope": "unknown",
        "repo_compatibility": "ok", "testability": "ok", "maintainer_intent": "ok", "existing_work": "ok", "system_support": "ok"}
    # the reporter's words and our extraction are labelled apart; the AI summary is never a maintainer statement
    assert d["expected_behavior"]["evidence"][0] == {"source": "reporter", "text": "return None"}
    assert any(e["source"] == "patchpilot" and "f(0) returns None" in e["text"] for e in d["expected_behavior"]["evidence"])
    assert all(e["source"] != "maintainer" for v in d.values() for e in v["evidence"])


def test_silence_is_unknown_and_only_maintainers_count_as_maintainers():
    cs = [{"user": {"login": "rep"}, "author_association": "NONE", "body": "Please fix, maintainers want this!"},
          {"user": {"login": "own"}, "author_association": "OWNER", "body": "Hmm, not sure this is a bug.",
           "html_url": "https://github.com/o/r/issues/1#issuecomment-5"},
          {"user": {"login": "carol"}, "author_association": "NONE", "body": "I'll send a PR for this tomorrow"}]
    d, _ = run(comments=cs)
    m = d["maintainer_intent"]
    assert m["outcome"] == "unknown" and m["missing"] == ["Whether the maintainers want a pull request"]
    assert [e["source"] for e in m["evidence"]] == ["maintainer"] and m["evidence"][0]["url"].endswith("issuecomment-5")
    assert "rep:" not in json.dumps(m)   # the reporter saying "maintainers want this" is not the maintainers
    w = d["existing_work"]
    assert w["outcome"] == "concern" and w["evidence"] == [{"source": "contributor", "text": "carol said they'll work on it"}]
    assert run()[0]["maintainer_intent"]["outcome"] == "unknown"   # nobody said anything: unknown, never consent


def test_gaps_blockers_and_unreadable_sources():
    d, _ = run(body="It is broken.", x={"issue_type": "bug"}, comments=None, linked=None)
    assert d["expected_behavior"]["outcome"] == "concern" and d["expected_behavior"]["missing"] == ["What should happen instead"]
    assert d["reproducibility"]["outcome"] == "concern" and len(d["reproducibility"]["missing"]) == 2
    assert d["existing_work"]["outcome"] == "unknown"   # comments and linked PRs unreadable
    d, _ = run(ai="forbidden", issue={"state_reason": None})
    assert d["maintainer_intent"]["outcome"] == "blocker"
    d, _ = run(checks={**OK, "python": S.FAILED}, unsupported="not_python")
    assert d["repo_compatibility"]["outcome"] == d["system_support"]["outcome"] == "blocker"
    d, _ = run(title="Add support for X", x={"issue_type": "feature"}, body="It would be nice to add support for X.", labels=["enhancement"])
    assert d["problem_clarity"]["outcome"] == "blocker" and d["expected_behavior"]["outcome"] == "unknown"


def test_report_says_not_checked_without_data_and_lists_sources():
    assert report_lines(None) == ["## Suitability by dimension", "- Not checked for this run.", ""]
    d, _ = run(labels=["help wanted"])
    text = "\n".join(report_lines(list(d.values())))
    assert "- **Maintainer intent: ok.**" in text and "  - repository: label: help wanted" in text and "there is no overall score" in text


def test_run_creation_stores_it_for_the_report(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api import main
    from backend.contracts.models import IssueSpec, RepoPolicy
    from backend.github.reader import IssueCheck
    from backend.report import suitability_section
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    url = "https://github.com/o/r/issues/1"
    d, _ = run()
    chk = IssueCheck(issue=IssueSpec(html_url=url, repo="o/r", number=1, title="t"), base_sha="abc", default_branch="main",
                     language="Python", policy=RepoPolicy(), fetched_at=db.now(), suitability=list(d.values()))
    monkeypatch.setattr(main, "check_issue", lambda u: chk)
    rid = TestClient(main.app, base_url="https://testserver").post("/api/runs", json={"issue_url": url}).json()["run_id"]
    assert "- **Is it a bug" not in "\n".join(suitability_section(rid))   # report wording, not the UI's
    assert "- **Problem clarity: ok.**" in "\n".join(suitability_section(rid))
    assert "Not checked" in "\n".join(suitability_section("other-run"))
