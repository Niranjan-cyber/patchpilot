"""G3 Reproduction gate (contracts.md 1.1, G3 row).

`passed` only when the test diff touches test files only *and* the new test
fails in **both** recorded runs with an assertion error or the issue's own
error. One run failing and one passing is `inconclusive` (flaky, and the
caller counts it as a failed attempt). Everything else is `failed`.

shortcut: statuses and reasons are returned as plain strings; swap to
`CheckStatus` from backend/contracts once B02 lands it (the values already
match). Reasons are the gate.result `reason` code (contracts.md:172).
"""

import re

# Failing with one of these is evidence of the bug, not of a broken test.
QUALIFYING = ("assertion", "issue_error")

# A run that reached neither a pass nor a usable failure.
DISQUALIFYING = ("import_error", "syntax_error", "collection_error", "other_error", "no_result")


def is_test_only_diff(paths):
    """True when every changed path is a test file and there is at least one.

    `paths` is what `git diff --name-only` gives for the test diff, slashes
    forward. An empty diff is no reproduction, so it is not test-only.
    """
    return bool(paths) and all(_is_test_path(p) for p in paths)


def _is_test_path(path):
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    in_test_dir = any(p in ("test", "tests") for p in parts[:-1])
    return in_test_dir or name.startswith("test_") or name.endswith("_test.py")


def classify_run(output, issue_error=None):
    """Classify one recorded pytest run of the new test.

    Each reproduction run executes only the new test, so the run's overall
    result is that test's result. Returns one of: assertion, issue_error,
    import_error, syntax_error, collection_error, other_error, passed,
    no_result.
    """
    # Import, syntax and collection errors mean the test never ran the bug,
    # so they outrank whatever the summary line says.
    if _raised(output, "ImportError") or _raised(output, "ModuleNotFoundError"):
        return "import_error"
    if _raised(output, "SyntaxError") or _raised(output, "IndentationError"):
        return "syntax_error"
    if "ERROR collecting" in output or "error during collection" in output:
        return "collection_error"

    if re.search(r"^=+ .*\d+ failed", output, re.M) or re.search(r"^FAILED ", output, re.M):
        if issue_error and _raised(output, issue_error):
            return "issue_error"
        # Older pytest prints a rewritten comparison as a bare `E  assert x == y`.
        if _raised(output, "AssertionError") or _raised(output, "assert"):
            return "assertion"
        return "other_error"

    if re.search(r"^=+ .*\d+ passed", output, re.M):
        return "passed"
    return "no_result"


def _raised(output, error_name):
    # pytest prints the raised error on an `E   <Name>: ...` line; the same
    # name inside a source or prose line is not what the test raised.
    return bool(re.search(rf"^E\s+{re.escape(error_name)}\b", output, re.M))


def evaluate_g3(diff_paths, run_outputs, issue_error=None):
    """Return (status, reason) for G3. Status is passed | failed | inconclusive."""
    if not is_test_only_diff(diff_paths):
        return "failed", "diff_touches_source"
    if len(run_outputs) != 2:
        return "failed", "run_count"

    kinds = [classify_run(o, issue_error) for o in run_outputs]
    for kind in DISQUALIFYING:
        if kind in kinds:
            return "failed", kind

    # Only qualifying failures and passes are left.
    qualifying = [k for k in kinds if k in QUALIFYING]
    if len(qualifying) == 2:
        return "passed", "reproduced"
    if len(qualifying) == 1:
        return "inconclusive", "flaky"
    return "failed", "test_passed"
