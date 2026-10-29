"""G4 diff policy (contracts §1.1) and the DIAGNOSE evidence check. Pure: code decides, never an LLM."""
import re
from pathlib import PurePosixPath

from backend.contracts.models import CheckStatus, GateResult

MAX_FILES, MAX_LINES = 5, 200
DEP_FILES = {"pyproject.toml", "setup.py", "setup.cfg", "pipfile", "pipfile.lock", "poetry.lock", "uv.lock", "pdm.lock"}
_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.M)


def is_test_path(p: str) -> bool:
    pp = PurePosixPath(p)
    name = pp.name
    return (any(part in ("tests", "test", "testing") for part in pp.parts[:-1]) or name == "conftest.py"
            or (name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))))


def is_dep_path(p: str) -> bool:
    name = PurePosixPath(p).name.lower()
    return name in DEP_FILES or (name.startswith("requirements") and name.endswith(".txt")) or \
        (name.endswith(".txt") and "requirements" in PurePosixPath(p).parts)


def g4_result(diff: str, *, evidence_ids: list[str]) -> GateResult:
    fail = lambda r: GateResult(gate="G4", status=CheckStatus.FAILED, reason=r, evidence_ids=evidence_ids)
    paths = {p for pair in _HEADER.findall(diff) for p in pair}
    if not paths:
        return fail("empty_diff")
    if "GIT binary patch" in diff or re.search(r"^Binary files .* differ$", diff, re.M):
        return fail("binary_change")
    if any(is_test_path(p) for p in paths):
        return fail("edits_tests")      # covers edited, deleted and renamed-into-tests files
    if any(is_dep_path(p) for p in paths):
        return fail("dependency_change")
    if any(PurePosixPath(p).parts[0] == ".github" for p in paths):
        return fail("ci_change")
    if len(_HEADER.findall(diff)) > MAX_FILES:
        return fail("too_many_files")
    changed = sum(1 for line in diff.splitlines()
                  if line[:1] in "+-" and not line.startswith(("+++ ", "--- ")))
    if changed > MAX_LINES:
        return fail("too_many_lines")
    return GateResult(gate="G4", status=CheckStatus.PASSED, reason="ok", evidence_ids=evidence_ids)


def check_diagnosis(res: dict | None, known_ids: set[str], line_count) -> str | None:
    """None = valid. line_count(path) -> number of lines, or None if the file doesn't exist in the pinned source."""
    if not isinstance(res, dict):
        return "no_result"
    if not str(res.get("hypothesis") or "").strip():
        return "no_hypothesis"
    ids = res.get("evidence_ids") or []
    if not isinstance(ids, list) or not isinstance(res.get("locations") or [], list):
        return "no_result"
    if not ids:
        return "no_evidence"
    if any(i not in known_ids for i in ids):
        return "unknown_evidence_id"
    locs = res.get("locations") or []
    if not locs:
        return "no_location"
    for loc in locs:
        if not isinstance(loc, dict):
            return "no_location"
        path = str(loc.get("path") or "")
        if not path or path.startswith("/") or ".." in PurePosixPath(path).parts:
            return "unknown_file"
        n = line_count(path)
        if n is None:
            return "unknown_file"
        line = loc.get("line")
        if line is not None and not (isinstance(line, int) and 1 <= line <= n):
            return "line_out_of_range"
    return None
