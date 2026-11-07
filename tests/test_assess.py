"""#48 §8 intake tests: the handling decision is decided by code from the issue and G0 checks."""
from backend.contracts.models import CheckStatus as S
from backend.github.assess import assess, classify, decide_handling, missing_information

OK = {"open": S.PASSED, "public": S.PASSED, "python": S.PASSED, "tests_found": S.PASSED, "unassigned": S.PASSED, "no_linked_pr": S.PASSED}
GOOD_BUG = ("divide(x, 0) returns 0 instead of raising\n\n```python\nfrom tinycalc import divide\ndivide(1, 0)\n```\n"
            "Expected: ZeroDivisionError\nActual: returns 0\n")


def run(title="divide(x, 0) returns 0", body=GOOD_BUG, labels=("bug",), names=("pyproject.toml", "tests"), state="open",
        checks=None, unsupported=None, warnings=(), linked=()):
    return assess(title=title, body=body, labels=list(labels), names=list(names), state=state, checks=checks or OK,
                  unsupported=unsupported, warnings=list(warnings), linked=list(linked))


def test_python_bug_with_enough_information_is_ready():
    a = run()
    assert a["handling_decision"] == "READY" and a["issue_type"] == "bug" and a["decision_reasons"] == []
    assert a["compatibility_status"] == "supported" and a["schema_version"] == 1


def test_non_python_repo_is_unsupported():
    a = run(names=("package.json",), checks={**OK, "python": S.FAILED}, unsupported="not_python")
    assert a["handling_decision"] == "UNSUPPORTED" and a["compatibility_status"] == "unsupported"
    assert "unsupported:not_python" in a["decision_reasons"]


def test_no_tests_is_unsupported():
    assert run(unsupported="no_tests")["handling_decision"] == "UNSUPPORTED"


def test_feature_request_is_assessment_only():
    a = run(title="Add support for complex numbers", body="It would be nice to support complex inputs.", labels=("enhancement",))
    assert a["handling_decision"] == "ASSESSMENT_ONLY" and "not_a_bug:enhancement" in a["decision_reasons"]


def test_documentation_issue_is_assessment_only():
    a = run(title="Typo in the README install section", body="The README says pip install tinycalcc.", labels=())
    assert a["issue_type"] == "docs" and a["handling_decision"] == "ASSESSMENT_ONLY"


def test_refactoring_issue_is_assessment_only():
    a = run(title="Refactor the parser module", body="parser.py has grown too big; split it.", labels=("refactor",))
    assert a["handling_decision"] == "ASSESSMENT_ONLY"


def test_bug_with_no_reproduction_information_needs_information():
    a = run(title="Something is off with divide", body="divide is weird sometimes.", labels=("bug",))
    assert a["handling_decision"] == "NEEDS_INFORMATION"
    assert set(a["missing_information"]) == {"no_expected", "no_actual", "no_repro"}
    assert "What should happen instead?" in a["draft_comment"]   # offered, never posted


def test_bug_missing_only_some_information_is_still_ready():
    a = run(body="divide(1, 0) should raise but it doesn't.")   # states expected, no repro snippet
    assert a["handling_decision"] == "READY" and "needs_info" not in a["decision_reasons"]


def test_unknown_type_is_human_decision_never_ready():
    a = run(title="divide", body="See title.", labels=())
    assert a["issue_type"] == "unknown" and a["handling_decision"] == "HUMAN_DECISION"


def test_conflicting_labels_are_human_decision():
    assert run(labels=("bug", "enhancement"))["handling_decision"] == "HUMAN_DECISION"


def test_bug_label_on_a_feature_request_title_is_human_decision():
    a = run(title="Feature request: add a power() function", body="Please add power(x, y).", labels=("bug",))
    assert a["handling_decision"] == "HUMAN_DECISION"


def test_unknown_python_compatibility_is_human_decision():
    assert run(checks={**OK, "python": S.INCONCLUSIVE})["handling_decision"] == "HUMAN_DECISION"


def test_linked_pr_is_already_addressed_and_keeps_the_warning():
    a = run(checks={**OK, "no_linked_pr": S.FAILED}, warnings=("linked_pr",), linked=(12,))
    assert a["handling_decision"] == "ALREADY_ADDRESSED" and a["existing_resolution"] == [12]


def test_closed_issue_keeps_existing_warning_handling():
    a = run(state="closed", checks={**OK, "open": S.FAILED}, warnings=("closed",))
    assert a["handling_decision"] == "ALREADY_ADDRESSED" and a["issue_status"] == "closed"


def test_unsupported_outranks_everything_and_lists_every_reason():
    d, reasons = decide_handling(unsupported="not_python", python=S.FAILED, issue_type="feature", missing=[], warnings=["linked_pr"])
    assert d == "UNSUPPORTED" and reasons == ["unsupported:not_python", "not_a_bug:feature", "linked_pr"]


def test_regression_from_text():
    assert classify("Parsing broke after upgrading to 2.1", "It used to work in 2.0. TypeError: x", []) == ("regression", "text")
    assert classify("Crash", "ValueError: bad", ["bug", "regression"]) == ("regression", "label")


def test_prefixed_labels_and_title_tags():
    assert classify("x", "", ["type: bug"]) == ("bug", "label")
    assert classify("[Docs] fix example", "", []) == ("docs", "text")


def test_missing_information_reads_templates_and_tracebacks():
    assert missing_information("Traceback (most recent call last):\n  ...\nKeyError: 'a'") == ["no_expected"]
    assert missing_information(GOOD_BUG) == []
