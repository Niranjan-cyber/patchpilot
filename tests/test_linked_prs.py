"""A's P1 (messages.md 2026-11-08 01:35): open PRs that fix an issue without a timeline cross-reference must still raise
the overridable linked_pr warning. Titles and bodies below are from the real PRs (python-dotenv #715, jmespath #381)."""
from backend.github.reader import mentioning_open_prs

DOTENV = "An empty value ignores ${name:-default}"
PULLS = [
    {"number": 720, "title": "Fix ${name:-default} ignoring default for empty values", "body": "Fixes #715.\n\n**Problem:** ..."},
    {"number": 716, "title": "fix: use the default when an interpolated variable is empty", "body": "## Purpose ..."},
    {"number": 684, "title": "Substitute ${name:-default} when the variable is set but empty (POSIX)", "body": "The README says ..."},
    {"number": 700, "title": "Add a CLI flag for quiet output", "body": "Closes #699"},
    {"number": 701, "title": "Bump version", "body": "see #7155 and #71"},            # other numbers that contain 715
    {"number": 702, "title": "docs: link https://github.com/theskumar/python-dotenv/issues/715", "body": None},
]


def test_number_or_url_mention_counts():
    got = mentioning_open_prs(PULLS, "theskumar/python-dotenv", 715, DOTENV)
    assert 720 in got and 702 in got and 701 not in got and 700 not in got


def test_title_overlap_catches_prs_that_never_name_the_issue():
    got = mentioning_open_prs(PULLS, "theskumar/python-dotenv", 715, DOTENV)
    assert {716, 684} <= set(got)


def test_jmespath_floor_ceil():
    pulls = [{"number": 391, "title": "Raise JMESPathTypeError for non-finite floor()/ceil() args", "body": "## Summary ..."},
             {"number": 383, "title": "Fix floor and ceil for non-finite Python floats", "body": "Fixes #381."},
             {"number": 300, "title": "Add a sort_by helper", "body": ""}]
    got = mentioning_open_prs(pulls, "jmespath/jmespath.py", 381,
                              "floor() and ceil() raise OverflowError / ValueError on Infinity and NaN")
    assert got == [383, 391]


def test_one_shared_word_is_not_enough():
    pulls = [{"number": 9, "title": "Speed up the default parser", "body": ""}]
    assert mentioning_open_prs(pulls, "o/r", 1, "An empty value ignores the default") == []


def test_bad_input_is_empty_not_a_crash():
    assert mentioning_open_prs([{"number": 1}, "junk", {"title": "x"}], "o/r", 5, "t") == []


def test_two_generic_repo_words_in_a_long_title_are_not_a_match():
    # cattrs#836 vs open #783: only "converter" and "hooks" in common, words most cattrs PRs use
    pulls = [{"number": 783, "title": "Honor converter hooks in make_dict_unstructure_fn", "body": ""}]
    assert mentioning_open_prs(pulls, "python-attrs/cattrs", 836,
                               "bson converter structures TypedDicts (and Counters) as plain dicts, skipping their hooks") == []


def test_a_pr_that_says_it_fixes_another_issue_is_not_a_title_match():
    # tinycalc#7 vs draft #5 "Fix #3: parse_number(...)": same function, but #5 is for #3
    pulls = [{"number": 5, "title": 'Fix #3: parse_number("1,000") crashes with ValueError', "body": "Fixes #3"}]
    assert mentioning_open_prs(pulls, "o/r", 7, 'parse_number("1e3") crashes with ValueError') == []
    assert mentioning_open_prs(pulls, "o/r", 3, 'parse_number("1,000") crashes with ValueError') == [5]
