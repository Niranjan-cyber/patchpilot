"""G3 reproduction gate: contracts.md 1.1, G3 row.

The recorded outputs below are real `pytest` shapes for the cases the gate has
to tell apart: assertion failure, the issue's own error, a `pytest.raises` that
didn't raise, ImportError, collection error, and a flaky test (fails once,
passes once).
"""

import pytest

from backend.gates.reproduction import classify_run, evaluate_g3, is_test_only_diff

ASSERTION = """\
============================= test session starts ==============================
collected 1 item

tests/test_slugify.py F                                                  [100%]

=================================== FAILURES ===================================
____________________________ test_slugify_unicode ______________________________

    def test_slugify_unicode():
        result = slugify("Creme Brulee")
>       assert result == "creme-brulee"
E       AssertionError: assert 'crme-brle' == 'creme-brulee'

tests/test_slugify.py:12: AssertionError
=========================== short test summary info ============================
FAILED tests/test_slugify.py::test_slugify_unicode - AssertionError: assert ...
============================== 1 failed in 0.04s ===============================
"""

ISSUE_ERROR = """\
============================= test session starts ==============================
collected 1 item

tests/test_merge.py F                                                    [100%]

=================================== FAILURES ===================================
_______________________________ test_merge_none ________________________________

    def test_merge_none():
>       merge({"a": 1}, None)
E       TypeError: argument of type 'NoneType' is not iterable

tests/test_merge.py:9: TypeError
=========================== short test summary info ============================
FAILED tests/test_merge.py::test_merge_none - TypeError: argument of type 'N...
============================== 1 failed in 0.03s ===============================
"""

IMPORT_ERROR = """\
============================= test session starts ==============================
collected 0 items / 1 error

==================================== ERRORS ====================================
______________________ ERROR collecting tests/test_slugify.py __________________
ImportError while importing test module '/repo/tests/test_slugify.py'.
Traceback:
tests/test_slugify.py:3: in <module>
    from slugify.core import slugify_unicode
E   ImportError: cannot import name 'slugify_unicode' from 'slugify.core'
=========================== short test summary info ============================
ERROR tests/test_slugify.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.11s ===============================
"""

COLLECTION_ERROR = """\
============================= test session starts ==============================
collected 0 items / 1 error

==================================== ERRORS ====================================
________________________ ERROR collecting tests/test_api.py ____________________
tests/test_api.py:14: in <module>
    @pytest.mark.parametrize("case", load_cases())
tests/test_api.py:8: in load_cases
    return json.loads(Path("cases.json").read_text())
E   FileNotFoundError: [Errno 2] No such file or directory: 'cases.json'
=========================== short test summary info ============================
ERROR tests/test_api.py - FileNotFoundError: [Errno 2] No such file or direc...
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.08s ===============================
"""

SYNTAX_ERROR = """\
==================================== ERRORS ====================================
______________________ ERROR collecting tests/test_cache.py ____________________
tests/test_cache.py:7: in <module>
    def test_cache(:
E     File "tests/test_cache.py", line 7
E       def test_cache(:
E                      ^
E   SyntaxError: invalid syntax
=============================== 1 error in 0.05s ===============================
"""

PASSED = """\
============================= test session starts ==============================
collected 1 item

tests/test_cache.py .                                                    [100%]
============================== 1 passed in 0.02s ===============================
"""

OTHER_ERROR = """\
=================================== FAILURES ===================================
_______________________________ test_lookup ____________________________________

    def test_lookup():
>       assert table["missing"] == 1
E       KeyError: 'missing'

tests/test_lookup.py:11: KeyError
=========================== short test summary info ============================
FAILED tests/test_lookup.py::test_lookup - KeyError: 'missing'
============================== 1 failed in 0.03s ===============================
"""

DID_NOT_RAISE = """\
=================================== FAILURES ===================================
_________________________ test_divide_by_zero_raises __________________________

    def test_divide_by_zero_raises():
>       with pytest.raises(ZeroDivisionError):
E       Failed: DID NOT RAISE <class 'ZeroDivisionError'>

tests/test_patchpilot_issue_1.py:6: Failed
=========================== short test summary info ============================
FAILED tests/test_patchpilot_issue_1.py::test_divide_by_zero_raises - Failed: ...
============================== 1 failed in 0.02s ===============================
"""

TEST_ONLY = ["tests/test_slugify.py"]


# --- classify_run: the five recorded outputs ------------------------------


@pytest.mark.parametrize(
    "output,issue_error,expected",
    [
        (ASSERTION, None, "assertion"),
        (ISSUE_ERROR, "TypeError", "issue_error"),
        (IMPORT_ERROR, None, "import_error"),
        (COLLECTION_ERROR, None, "collection_error"),
        (SYNTAX_ERROR, None, "syntax_error"),
        (PASSED, None, "passed"),
        (OTHER_ERROR, None, "other_error"),
    ],
)
def test_classify_run(output, issue_error, expected):
    assert classify_run(output, issue_error) == expected


def test_import_error_wins_over_its_collection_banner():
    # IMPORT_ERROR also says "error during collection"; the import is the specific cause.
    assert classify_run(IMPORT_ERROR) == "import_error"


def test_issue_error_must_match_the_issue():
    # The run raises TypeError but the issue reported ValueError: not the issue's error.
    assert classify_run(ISSUE_ERROR, "ValueError") == "other_error"


def test_the_issues_error_is_not_matched_from_prose():
    # The name appears in a source line, not as the error pytest raised.
    output = ASSERTION.replace("assert result ==", "assert ValueError_count ==")
    assert classify_run(output, "ValueError") == "assertion"


def test_bare_rewritten_assert_counts_as_an_assertion():
    # Older pytest omits the "AssertionError:" prefix on a rewritten comparison.
    output = ASSERTION.replace(
        "E       AssertionError: assert 'crme-brle' == 'creme-brulee'",
        "E       assert 'crme-brle' == 'creme-brulee'",
    )
    assert classify_run(output) == "assertion"


def test_an_assert_prefixed_identifier_is_not_an_assertion():
    output = ASSERTION.replace("E       AssertionError: assert", "E       assert_called_once:")
    assert classify_run(output) == "other_error"


def test_pytest_raises_that_did_not_raise_is_a_reproduction():
    # "the bug is that it no longer raises" is a whole class of real issue;
    # reading DID NOT RAISE as other_error would end every one of them as
    # CANNOT_REPRODUCE. Added by A on the B06 takeover; this is its test.
    assert classify_run(DID_NOT_RAISE) == "assertion"
    assert classify_run(DID_NOT_RAISE, "ZeroDivisionError") == "assertion"
    assert evaluate_g3(["tests/test_patchpilot_issue_1.py"], [DID_NOT_RAISE] * 2) == (
        "passed",
        "reproduced",
    )


def test_a_bare_pytest_fail_is_not_a_reproduction():
    # Same "Failed:" prefix, but pytest.fail("todo") is evidence of nothing.
    output = DID_NOT_RAISE.replace(
        "Failed: DID NOT RAISE <class 'ZeroDivisionError'>", "Failed: not implemented yet"
    )
    assert classify_run(output) == "other_error"


@pytest.mark.parametrize("word", ["skipped", "xfailed", "xpassed"])
def test_a_test_that_never_really_ran_is_not_a_reproduction(word):
    # An xfail-marked repro test "fails as expected" and exits 0. None of
    # these may count as evidence, so they land on the failing side.
    output = f"============================== 1 {word} in 0.01s ==============================\n"
    assert classify_run(output) == "no_result"
    assert evaluate_g3(TEST_ONLY, [output, output]) == ("failed", "no_result")


def test_empty_output_is_no_result():
    assert classify_run("") == "no_result"


def test_a_missing_output_is_no_result_not_a_crash():
    # "Unknown is NULL" (AGENTS.md), so a run with no captured output arrives
    # as None. A gate must never raise.
    assert classify_run(None) == "no_result"
    assert evaluate_g3(TEST_ONLY, [ASSERTION, None]) == ("failed", "no_result")


def test_a_fully_qualified_exception_matches_the_issues_bare_class_name():
    # The issue says "ValidationError"; pytest prints the dotted path.
    output = ISSUE_ERROR.replace(
        "E       TypeError:", "E       django.core.exceptions.ValidationError:"
    )
    assert classify_run(output, "ValidationError") == "issue_error"


def test_a_dotted_prefix_does_not_make_a_different_class_match():
    output = ISSUE_ERROR.replace("E       TypeError:", "E       MyValueError:")
    assert classify_run(output, "ValueError") == "other_error"


# --- is_test_only_diff ----------------------------------------------------


@pytest.mark.parametrize(
    "paths,expected",
    [
        (["tests/test_slugify.py"], True),
        (["tests/unit/test_a.py", "tests/conftest.py"], True),
        (["src/slugify/core_test.py"], True),
        (["src/slugify/core.py"], False),
        (["tests/test_a.py", "src/slugify/core.py"], False),
        (["requirements.txt"], False),
        ([], False),
        # A test diff may only add Python test modules: anything else would
        # ride into the published PR.
        ([".github/workflows/test_ci.yml"], False),
        ([".github/workflows/test_ci.py"], False),
        (["tests/install.sh"], False),
        (["tests/Dockerfile"], False),
        # git quotes a non-ASCII path unless core.quotepath=false.
        (['"tests/t\\303\\251st.py"'], True),
    ],
)
def test_is_test_only_diff(paths, expected):
    assert is_test_only_diff(paths) == expected


# --- evaluate_g3 ----------------------------------------------------------


def test_passes_when_an_assertion_fails_in_both_runs():
    assert evaluate_g3(TEST_ONLY, [ASSERTION, ASSERTION]) == ("passed", "reproduced")


def test_passes_on_the_issues_own_error_in_both_runs():
    assert evaluate_g3(["tests/test_merge.py"], [ISSUE_ERROR, ISSUE_ERROR], "TypeError") == (
        "passed",
        "reproduced",
    )


def test_flaky_one_of_two_is_inconclusive():
    assert evaluate_g3(TEST_ONLY, [ASSERTION, PASSED]) == ("inconclusive", "flaky")
    assert evaluate_g3(TEST_ONLY, [PASSED, ASSERTION]) == ("inconclusive", "flaky")


def test_import_error_fails_even_if_the_other_run_asserts():
    assert evaluate_g3(TEST_ONLY, [ASSERTION, IMPORT_ERROR]) == ("failed", "import_error")


def test_collection_and_syntax_errors_fail():
    assert evaluate_g3(TEST_ONLY, [COLLECTION_ERROR, COLLECTION_ERROR])[0] == "failed"
    assert evaluate_g3(TEST_ONLY, [SYNTAX_ERROR, SYNTAX_ERROR]) == ("failed", "syntax_error")


def test_a_test_that_passes_twice_fails_the_gate():
    assert evaluate_g3(TEST_ONLY, [PASSED, PASSED]) == ("failed", "test_passed")


def test_a_diff_touching_source_fails_before_any_output_is_read():
    assert evaluate_g3(["src/slugify/core.py"], [ASSERTION, ASSERTION]) == (
        "failed",
        "diff_touches_source",
    )


def test_wrong_number_of_runs_fails():
    # The gate is defined on exactly 2 runs; one run is never evidence of reproduction.
    assert evaluate_g3(TEST_ONLY, [ASSERTION]) == ("failed", "run_count")
    assert evaluate_g3(TEST_ONLY, []) == ("failed", "run_count")


def test_an_unreadable_run_is_not_a_reproduction():
    assert evaluate_g3(TEST_ONLY, [ASSERTION, ""]) == ("failed", "no_result")


def test_g3_result_contract_shape():
    from backend.contracts.models import CheckStatus
    from backend.gates.reproduction import g3_result
    r = g3_result(["src/a.py"], ["", ""])
    assert r.gate == "G3" and r.status == CheckStatus.FAILED and r.reason == "diff_touches_source"


def test_did_not_raise_counts_as_assertion():
    from tests.test_agents import FAIL_OUT
    assert classify_run(FAIL_OUT) == "assertion"
