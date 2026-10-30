"""G4 diff policy (contracts §1.1) and the DIAGNOSE evidence check. Pure: code decides, never an LLM."""
import re
from pathlib import PurePosixPath

from backend.contracts.models import CheckStatus, GateResult

MAX_FILES, MAX_LINES = 5, 200
DEP_FILES = {"pyproject.toml", "setup.py", "setup.cfg", "pipfile", "pipfile.lock", "poetry.lock", "uv.lock", "pdm.lock"}
_HEADER = re.compile(r"^diff --git (.+)$", re.M)


def diff_paths(diff: str) -> tuple[set[str], bool]:
    """Every path a git diff touches, and whether every header could be parsed.

    git does not quote a space in `diff --git a/X b/Y`, so that line is ambiguous in general.
    The identical-path case (every diff that isn't a rename) is resolved with a backreference;
    a header we can't split is reported so the caller refuses the diff instead of silently
    ignoring the file it names. Paths quoted by git (non-ASCII, specials) also land in the
    unparsed bucket, i.e. they fail closed.
    """
    paths, parsed_all = set(), True
    for body in (b.rstrip() for b in _HEADER.findall(diff)):
        if (m := re.fullmatch(r"a/(.+) b/\1", body)):
            paths.add(m.group(1))
        elif (m := re.fullmatch(r"a/(\S+) b/(\S+)", body)):   # rename or copy
            paths.update(m.groups())
        else:
            parsed_all = False
    return paths, parsed_all


def _header_new_path(line: str) -> str | None:
    """The post-image path of a `diff --git` line, "" when it can't be parsed, None if not a header."""
    if not (m := _HEADER.match(line)):
        return None
    body = m.group(1).rstrip()
    if (x := re.fullmatch(r"a/(.+) b/\1", body)):
        return x.group(1)
    if (x := re.fullmatch(r"a/(\S+) b/(\S+)", body)):
        return x.group(2)
    return ""


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
    paths, parsed_all = diff_paths(diff)
    if not paths and parsed_all:
        return fail("empty_diff")
    if not parsed_all:   # a file we can't name is a file we can't check: refuse the diff
        return fail("unparseable_diff")
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


def _path_in_source(path: str, line_count) -> int | None:
    """Lines in the file, or None when it's absolute, escapes /src, or isn't in the pinned source."""
    if not path or path.startswith("/") or ".." in PurePosixPath(path).parts:
        return None
    return line_count(path)


def keep_tour(tour, line_count) -> tuple[list[dict], list[str]]:
    """Split the model's tour into items whose file really is in the pinned source, and the paths dropped.

    The UI links every tour path into the pinned commit for the user to read along, and `explain`
    counts them as cited files, so an invented path is a wrong fact about the user's code and a 404.
    The hypothesis and locations are validated separately, so a bad tour item is dropped instead of
    failing the whole diagnosis: no outcome changes, and nothing false is shown.
    """
    kept, dropped = [], []
    for t in tour:
        if not isinstance(t, dict):
            continue
        path = str(t.get("path") or "")
        if _path_in_source(path, line_count) is None:
            dropped.append(path)
        else:
            kept.append(t)
    return kept, dropped


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
        n = _path_in_source(str(loc.get("path") or ""), line_count)
        if n is None:
            return "unknown_file"
        line = loc.get("line")
        if line is not None and not (isinstance(line, int) and 1 <= line <= n):
            return "line_out_of_range"
    return None


_EXCEPT = re.compile(r"^(\s*)except\b\s*(.*?)\s*(?:as\s+\w+\s*)?:")
_BROAD = re.compile(r"^\(?\s*(BaseException|Exception)\s*\)?$")
_HANDLED = re.compile(r"\braise\b|\blog(?:ger|ging)?\.\w+\(|\bwarnings\.warn\(|\bprint\(.*file\s*=\s*sys\.stderr")


def swallowed_excepts(diff: str) -> list[dict]:
    """Reviewer concerns, decided by code: an `except` the fix ADDS (source files only) that catches everything, or whose
    handler neither re-raises nor logs (a retry, `pass`, `return <default>`), may hide real errors (run 11's TypeError retry)."""
    out, path, lines = [], None, diff.splitlines()
    for i, line in enumerate(lines):
        if (h := _header_new_path(line)) is not None:
            path = h or None      # unparseable header: attribute its hunks to no file
            continue
        if not path or is_test_path(path) or not path.endswith(".py") or not line.startswith("+") or line.startswith("+++"):
            continue
        m = _EXCEPT.match(line[1:])
        if not m:
            continue
        indent, what = len(m.group(1)), m.group(2) or ""
        body = []
        for nxt in lines[i + 1:]:   # the handler as it reads after the fix: added + context lines, deeper than `except`
            if nxt.startswith(("-", "@@", "diff --git")):
                if nxt.startswith("-"):
                    continue
                break
            code = nxt[1:]
            if code.strip() and not code.lstrip().startswith("#"):
                if len(code) - len(code.lstrip()) <= indent:
                    break
                body.append(code)
        if not what or _BROAD.match(what):
            text = f"The fix adds `except{' ' + what if what else ''}:` in {path}, which catches every error; check it can't hide real bugs."
        elif not any(_HANDLED.search(b) for b in body):
            text = f"The fix adds `except {what}:` in {path} that neither re-raises nor logs, so it may hide real errors; check it."
        else:
            continue
        out.append({"severity": "medium", "text": text})
    return out[:2]   # shortcut: two concerns say enough; upgrade if reviewers want every location listed
