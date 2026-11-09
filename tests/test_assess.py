"""#48 §8 intake tests. The model extracts (classifier); code decides; unknown is never READY (DECISION 2026-11-07)."""
import time

import pytest

from backend import db
from backend.contracts.models import CheckStatus as S
from backend.github import assess as A
from backend.github.assess import assess, classify, decide_handling, keyword_type, missing_information, new_warnings

OK = {"open": S.PASSED, "public": S.PASSED, "python": S.PASSED, "tests_found": S.PASSED, "unassigned": S.PASSED, "no_linked_pr": S.PASSED}
GOOD_BUG = ("divide(x, 0) returns 0 instead of raising\n\n```python\nfrom tinycalc import divide\ndivide(1, 0)\n```\n"
            "Expected: ZeroDivisionError\nActual: returns 0\n")
NO_MODEL = object()


def run(title="divide(x, 0) returns 0", body=GOOD_BUG, labels=("bug",), names=("pyproject.toml", "tests"), state="open",
        checks=None, unsupported=None, warnings=(), linked=(), model="bug", base_sha="abc123", forbids_ai=False):
    return assess(title=title, body=body, labels=list(labels), names=list(names), state=state, checks=checks or OK,
                  unsupported=unsupported, warnings=list(warnings), linked=None if linked is None else list(linked),
                  extracted=None if model is NO_MODEL else {"issue_type": model}, base_sha=base_sha, forbids_ai=forbids_ai)


# ---- the #48 §8 intake cases ----
def test_python_bug_with_enough_information_is_ready():
    a = run()
    assert a.handling_decision == "READY" and a.issue_type == "bug" and a.issue_type_source == "model"
    assert a.decision_reasons == [] and a.compatibility_status == "supported" and a.test_framework == "pytest"


def test_non_python_repo_is_unsupported():
    a = run(names=("package.json",), checks={**OK, "python": S.FAILED}, unsupported="not_python", model=NO_MODEL)
    assert a.handling_decision == "UNSUPPORTED" and a.compatibility_status == "unsupported"
    assert "unsupported:not_python" in a.decision_reasons and "model_unavailable" not in a.decision_reasons   # no call made


def test_no_tests_is_unsupported():
    assert run(unsupported="no_tests").handling_decision == "UNSUPPORTED"


def test_feature_request_is_assessment_only():
    a = run(title="Add support for complex numbers", body="It would be nice to support complex inputs.", labels=("enhancement",),
            model="enhancement")
    assert a.handling_decision == "ASSESSMENT_ONLY" and "not_a_bug:enhancement" in a.decision_reasons


def test_documentation_issue_is_assessment_only():
    a = run(title="Typo in the README install section", body="The README says pip install tinycalcc.", labels=(), model="docs")
    assert a.issue_type == "docs" and a.handling_decision == "ASSESSMENT_ONLY"


def test_refactoring_issue_is_assessment_only():
    a = run(title="Refactor the parser module", body="parser.py has grown too big; split it.", labels=("refactor",), model="refactor")
    assert a.handling_decision == "ASSESSMENT_ONLY"


def test_bug_with_no_reproduction_information_needs_information():
    a = run(title="Something is off with divide", body="divide is weird sometimes.")
    assert a.handling_decision == "NEEDS_INFORMATION"
    assert set(a.missing_information) == {"no_expected", "no_actual", "no_repro"}
    assert "What should happen instead?" in a.draft_comment   # offered, never posted


def test_unknown_type_is_human_decision_never_ready():
    a = run(title="divide", body="See title.", labels=(), model="unknown")
    assert a.issue_type == "unknown" and a.handling_decision == "HUMAN_DECISION" and "unclear_type" in a.decision_reasons


def test_linked_pr_is_already_addressed_and_keeps_the_warning():
    a = run(checks={**OK, "no_linked_pr": S.FAILED}, warnings=("linked_pr",), linked=(12,))
    assert a.handling_decision == "ALREADY_ADDRESSED" and a.existing_resolution == [12]
    assert "Lookups can be wrong" in A.DECISION_TEXT["ALREADY_ADDRESSED"]   # a warning, not a verdict


def test_closed_issue_keeps_existing_warning_handling():
    a = run(state="closed", checks={**OK, "open": S.FAILED}, warnings=("closed",))
    assert a.handling_decision == "ALREADY_ADDRESSED" and a.issue_status == "closed"


def test_repo_forbids_ai_is_listed_as_a_reason_without_changing_the_decision():
    a = run(forbids_ai=True)
    assert a.handling_decision == "READY" and "repo_forbids_ai" in a.decision_reasons   # the publish blocker stays permanent


# ---- the model is the classifier; keywords only cross-check ----
def test_model_unavailable_never_makes_a_bug_ready():
    a = run(model=NO_MODEL)
    assert a.handling_decision == "HUMAN_DECISION" and {"model_unavailable", "unclear_type"} <= set(a.decision_reasons)
    assert new_warnings(a) == ["unclear_type"]


def test_model_unavailable_with_a_clear_non_bug_label_is_human_decision_not_a_hard_block():
    # A's review, bug 3: keywords alone may not set G0 blocked; the user decides (overridable, with the report caveat)
    a = run(title="Docs: fix the install example", body="typo", labels=("documentation",), model=NO_MODEL)
    assert a.handling_decision == "HUMAN_DECISION" and {"model_unavailable", "unclear_type"} <= set(a.decision_reasons)


def test_model_and_labels_disagree_is_human_decision():
    assert run(labels=("enhancement",), model="bug").handling_decision == "HUMAN_DECISION"
    a = run(title="Feature request: add a power() function", body="Please add power(x, y).", labels=("bug",), model="feature")
    assert a.handling_decision == "HUMAN_DECISION" and a.issue_type_source == "model"


def test_conflicting_labels_are_human_decision():
    assert run(labels=("bug", "enhancement")).handling_decision == "HUMAN_DECISION"


def test_model_bug_with_no_keyword_signal_is_ready():
    # no label, no traceback: keywords say nothing, so they don't contradict the model
    assert run(labels=(), body="divide(1, 0) should raise ZeroDivisionError but returns 0.").handling_decision == "READY"


# ---- unknown required fields -> HUMAN_DECISION with its reason (A's review) ----
@pytest.mark.parametrize("kw,reason,warning", [
    (dict(checks={**OK, "python": S.INCONCLUSIVE}), "compatibility_unknown", "lookup_failed"),
    (dict(linked=None), "linked_pr_unknown", "lookup_failed"),
    (dict(checks={**OK, "tests_found": S.INCONCLUSIVE}, names=("pyproject.toml",)), "test_framework_unknown", "lookup_failed"),
    (dict(base_sha=None), "base_sha_unknown", "base_unknown"),
    (dict(base_sha="pending"), "base_sha_unknown", "base_unknown"),
])
def test_unknown_required_field_is_human_decision(kw, reason, warning):
    a = run(**kw)
    assert a.handling_decision == "HUMAN_DECISION" and reason in a.decision_reasons and warning in new_warnings(a)


def test_windows_only_bug_is_a_human_decision_with_a_warning():
    a = run(title="`click.edit` on Windows throws WinError 14001", body="Traceback ...\nOSError: [WinError 14001]")
    assert a.handling_decision == "HUMAN_DECISION" and "other_os" in a.decision_reasons and new_warnings(a) == ["other_os"]


def test_unsupported_outranks_everything_and_lists_every_reason():
    d, reasons = decide_handling(unsupported="not_python", python=S.FAILED, issue_type="feature", missing=[], warnings=["linked_pr"])
    assert d == "UNSUPPORTED" and reasons == ["unsupported:not_python", "not_a_bug:feature", "linked_pr"]


def test_keyword_cross_check():
    assert keyword_type("Parsing broke after upgrading to 2.1", "It used to work in 2.0. TypeError: x", []) == ("regression", "text")
    assert keyword_type("Crash", "ValueError: bad", ["bug", "regression"]) == ("regression", "label")
    assert keyword_type("x", "", ["type: bug"]) == ("bug", "label")
    assert keyword_type("[Docs] fix example", "", []) == ("docs", "text")
    assert classify("x", "", [], None) == ("unknown", "none")


def test_missing_information_reads_templates_and_tracebacks():
    assert missing_information("Traceback (most recent call last):\n  ...\nKeyError: 'a'") == ["no_expected"]
    assert missing_information(GOOD_BUG) == []


# ---- extract(): bounded, counted, cached; never raises ----
class Resp:
    def __init__(self, text, p=900, k=200):
        self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]
        self.usage = type("U", (), {"prompt_tokens": p, "completion_tokens": k})()


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    import backend.config
    import backend.llm_gateway as G
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(backend.config, "limits", lambda: {"assess_llm_tokens_per_day": 5000})
    monkeypatch.setattr(G, "_limits", lambda: {"run_llm_tokens": 400_000, "global_llm_tokens_per_day": 100_000})
    monkeypatch.setattr(G, "chain", lambda kind: ["groq/test"])


def x(text="", calls=None, **kw):
    def comp(**k):
        if calls is not None:
            calls.append(k)
        return Resp(text, **kw)
    return dict(url="https://github.com/o/r/issues/1", updated_at="2026-11-07T00:00:00Z", title="t", body="b", labels=[],
                _completion=comp)


def test_extract_parses_counts_and_caches(tmpdb):
    calls = []
    good = '{"issue_type": "bug", "problem_summary": "divide is wrong", "acceptance_conditions": ["raises"]}'
    out = A.extract(**x(good, calls))
    assert out["issue_type"] == "bug" and out["acceptance_conditions"] == ["raises"] and len(calls) == 1
    assert A.assess_tokens_today() == 1100                         # logged under role "assessor"
    assert A.extract(**x(good, calls)) == out and len(calls) == 1  # same issue version: cached, no second call


def test_a_new_extraction_prompt_is_not_answered_from_the_old_cache(tmpdb, monkeypatch):
    # gitingest-115: cached conditions from the old prompt would survive the prompt fix until the issue is edited
    calls = []
    good = '{"issue_type": "bug", "acceptance_conditions": ["raises"]}'
    A.extract(**x(good, calls))
    monkeypatch.setattr(A, "EXTRACT_PROMPT", A.EXTRACT_PROMPT + " ")
    A.extract(**x(good, calls))
    assert len(calls) == 2


def test_conditions_state_the_behaviour_not_only_the_reporters_example():   # gitingest-115
    p = A.EXTRACT_PROMPT
    assert "not only the reporter's example" in p and "title" in p and "Never invent" in p


def test_extract_bad_json_or_type_is_unavailable(tmpdb):
    assert A.extract(**x("not json")) is None
    assert A.extract(**{**x('{"issue_type": "bugfix"}'), "updated_at": "v2"}) is None


def test_extract_respects_its_own_daily_cap(tmpdb):
    A.extract(**x('{"issue_type": "bug"}', p=4000, k=1000))       # 5,000 tokens used = the cap
    calls = []
    assert A.extract(**{**x('{"issue_type": "bug"}', calls), "updated_at": "v2"}) is None and calls == []


def test_extract_times_out_as_unavailable(tmpdb, monkeypatch):
    monkeypatch.setattr(A, "EXTRACT_SECONDS", 0.2)

    def slow(**k):
        time.sleep(1)
        return Resp('{"issue_type": "bug"}')
    assert A.extract(**{**x(), "_completion": slow}) is None


# ---- carried over from #41 (unclear_bug), so no warning behaviour is lost ----
def test_reporter_unsure_it_is_a_bug_is_human_decision_even_if_the_model_says_bug():
    a = run(body="divide(1, 0) returns 0. Is this expected? Not sure if intentional.\n" + GOOD_BUG)
    assert a.handling_decision == "HUMAN_DECISION" and "unclear_type" in a.decision_reasons


def test_report_carries_the_unclear_caveat_on_every_outcome_after_consent():
    from backend.github.assess import UNCLEAR_CAVEAT, report_lines
    assert report_lines(run(model="unknown"))[0] == UNCLEAR_CAVEAT
    assert UNCLEAR_CAVEAT not in report_lines(run())          # a clear READY bug: no caveat


# ---- A's review of #50: bugs 2+3, ASSESSMENT_ONLY only when model AND labels/text agree it's a non-bug ----
def test_bug2_model_alone_never_hard_blocks():
    a = run(title="Something about CI", body="The workflow is red on main.", labels=(), model="build_ci")
    assert a.handling_decision == "HUMAN_DECISION" and "unclear_type" in a.decision_reasons   # overridable, not G0 blocked


def test_bug3_keywords_alone_never_hard_block_when_the_model_is_unavailable():
    for title, labels in (("The docs say parse() should accept bytes", ()), ("How do I avoid this crash", ()), ("x fails", ("tests",))):
        a = run(title=title, body="parse(b'x') raises TypeError", labels=labels, model=NO_MODEL)
        assert a.handling_decision == "HUMAN_DECISION", title


def test_model_and_keywords_agreeing_on_a_non_bug_is_assessment_only():
    a = run(title="Docs: fix the install example", body="typo", labels=("documentation",), model="docs")
    assert a.handling_decision == "ASSESSMENT_ONLY" and a.issue_type == "docs"


# ---- A's "plausible" items on #50 ----
def test_parse_extraction_survives_braces_around_the_json():
    from backend.github.assess import parse_extraction
    out = parse_extraction('Thinking about {sets}... answer: {"issue_type": "bug", "problem_summary": "x"} (done {ok})')
    assert out and out["issue_type"] == "bug" and out["problem_summary"] == "x"
    assert parse_extraction('{"issue_type": "nope"} {broken') is None


def test_repo_fact_checks_skip_the_assessor_call(monkeypatch):
    import backend.github.reader as R
    canned = {"/repos/o/r/issues/1": {"state": "open", "title": "t", "body": "b", "assignees": [], "labels": []},
              "/repos/o/r": {"language": "Python", "default_branch": "main"}}
    monkeypatch.setattr(R, "_get", lambda h, path, required=True: canned.get(path))
    called = []
    monkeypatch.setattr("backend.github.assess.extract", lambda **k: called.append(k))
    R.check_issue("https://github.com/o/r/issues/1", extract_model=False)   # approval stale check, publisher
    assert called == []
    R.check_issue("https://github.com/o/r/issues/1")
    assert len(called) == 1
