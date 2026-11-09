"""#70 item 8 (trust plan §7): a deterministic test-quality report for the regression test. Code only, no model opinion.
Each row: PASS / FAIL / REVIEW_REQUIRED / NOT_COVERED / NOT_CHECKED, with a one-line note. Read from the run and the
stored test diff, so it needs no storage and never claims a check it couldn't make."""
import ast
import re
import sys
import textwrap

from backend import artifacts
from backend.contracts.models import CheckStatus, RunView

MOCK = re.compile(r"\b(?:mock\.|Mock\(|MagicMock\(|AsyncMock\(|patch\(|patch\.object\(|mocker\.|monkeypatch\.setattr)")
ASSERT_CALL = re.compile(r"^(?:assert\w*|fail\w*)$")    # unittest's self.assertEqual / failUnless, and pytest.fail
RAISES = {"raises", "warns", "assertRaises", "assertRaisesRegex", "assertWarns", "assertLogs"}


def _files(diff: str) -> dict[str, dict]:
    """path -> {added: source lines added, removed: count of removed lines}."""
    out, cur = {}, None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            cur = line.rsplit(" b/", 1)[-1]; out[cur] = {"added": [], "removed": 0}
        elif cur and line.startswith("+") and not line.startswith("+++"):
            out[cur]["added"].append(line[1:])
        elif cur and line.startswith("-") and not line.startswith("---"):
            out[cur]["removed"] += 1
    return out


def _tests(src: str) -> list[ast.FunctionDef] | None:
    """The test functions in the added code; None when it doesn't parse (a hunk inside an existing file)."""
    try:
        tree = ast.parse(textwrap.dedent(src))
    except SyntaxError:
        return None
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")]


def _checks(fn) -> tuple[int, int]:
    """(real checks, vacuous asserts) in one test function. `assert True` / `assert 1` / `assert "x"` check nothing."""
    real = vacuous = 0
    for n in ast.walk(fn):
        if isinstance(n, ast.Assert):
            if (isinstance(n.test, ast.Constant) and n.test.value) or (isinstance(n.test, ast.Tuple) and n.test.elts):
                vacuous += 1   # `assert True`, and `assert (x, "msg")`: a non-empty tuple is always true
            else:
                real += 1
        elif isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if name in RAISES or ASSERT_CALL.match(name) or (isinstance(f, ast.Attribute) and name.startswith("assert_")):
                real += 1   # pytest.raises, self.assertEqual, mock.assert_called_once_with
    return real, vacuous


def _imports(src: str) -> set[str]:
    try:
        tree = ast.parse(textwrap.dedent(src))
    except SyntaxError:
        return {m.group(1) for m in re.finditer(r"(?m)^\s*(?:from|import)\s+([A-Za-z_]\w*)", src)}
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module.split(".")[0])
    return out


def _row(check: str, status: str, note: str) -> dict:
    return {"check": check, "status": status, "note": note}


def report(v: RunView) -> list[dict]:
    rows = []
    base = v.repro.runs_on_base if v.repro else []
    if not base:
        rows.append(_row("fails_on_base", "NOT_CHECKED", "the test wasn't run on the original code"))
    elif all(s == CheckStatus.FAILED for s in base):
        rows.append(_row("fails_on_base", "PASS" if len(base) >= 2 else "REVIEW_REQUIRED",
                         f"failed {len(base)}/{len(base)} times on the original code" + ("" if len(base) >= 2 else "; one run isn't enough to rule out flakiness")))
    else:
        rows.append(_row("fails_on_base", "FAIL", "didn't fail every time on the original code: " + ", ".join(s.value for s in base)))
    runs = v.verify.new_test_runs if v.verify else []
    if not runs:
        rows.append(_row("passes_with_fix", "NOT_CHECKED", "not run with the fix"))
    else:
        ok = all(s == CheckStatus.PASSED for s in runs)
        rows.append(_row("passes_with_fix", ("PASS" if len(runs) >= 2 else "REVIEW_REQUIRED") if ok else "FAIL",
                         f"passed {sum(s == CheckStatus.PASSED for s in runs)}/{len(runs)} times with the fix in a fresh sandbox"
                         + ("" if not ok or len(runs) >= 2 else "; one run isn't enough to rule out flakiness")))

    raw = artifacts.get(v.repro.test_diff_id) if v.repro else None
    files = _files(raw.decode("utf-8", "replace")) if raw else None
    if not files:   # missing, expired, or not a diff we can read
        rows += [_row(c, "NOT_CHECKED", "the test's diff isn't available or couldn't be read")
                 for c in ("assertions", "mocks", "existing_tests", "test_location", "new_imports")]
    else:
        src = {p: "\n".join(f["added"]) for p, f in files.items()}
        parsed = {p: _tests(s) for p, s in src.items()}
        fns = [fn for t in parsed.values() if t for fn in t]
        if not fns:
            # an edit inside an existing file: count assert lines in what was added instead of reading the functions
            n = sum(len(re.findall(r"(?m)^\s*(?:assert\b|self\.assert|with pytest\.raises)", s)) for s in src.values())
            # zero isn't a FAIL here: new parametrize cases reuse the asserts in the unchanged test body
            rows.append(_row("assertions", "PASS" if n else "REVIEW_REQUIRED",
                             f"{n} assertion line{'s' if n != 1 else ''} in the added code (read line by line: it's a change inside an existing file)"
                             + ("" if n else "; if it adds cases to an existing test, check that test's asserts")))
        else:
            per = {fn.name: _checks(fn) for fn in fns}
            empty = [n for n, (real, _) in per.items() if not real]
            vac = sum(x for _, x in per.values())
            if empty:
                rows.append(_row("assertions", "FAIL", f"no real check in: {', '.join(empty)}" + (f" ({vac} always-true asserts)" if vac else "")))
            elif any(t is None for t in parsed.values()):   # whole functions graded; the rest is a hunk inside an existing file
                rows.append(_row("assertions", "REVIEW_REQUIRED", f"every new test function checks something; "
                                 f"{', '.join(p for p, t in parsed.items() if t is None)} changes an existing file, so check it by eye"))
            else:
                rows.append(_row("assertions", "PASS", f"every new test function checks something ({sum(r for r, _ in per.values())} checks in {len(per)} "
                                 f"function{'s' if len(per) != 1 else ''})" + (f"; {vac} always-true asserts too" if vac else "")))
        mocks = sum(len(MOCK.findall(s)) for s in src.values())
        rows.append(_row("mocks", "REVIEW_REQUIRED" if mocks else "PASS",
                         f"{mocks} mock or patch use{'s' if mocks != 1 else ''}: check the test still runs the real code path" if mocks
                         else "no mocks or patches: the test runs the real code"))
        edited = {p: f["removed"] for p, f in files.items() if f["removed"]}
        rows.append(_row("existing_tests", "REVIEW_REQUIRED" if edited else "PASS",
                         "removes or changes existing lines in " + ", ".join(f"{p} ({n})" for p, n in edited.items()) if edited
                         else "only adds lines; no existing test is changed"))
        dirs = {t.split("::")[0].rsplit("/", 1)[0] for t in (v.baseline.pass_set + v.baseline.fail_set) if "/" in t.split("::")[0]} if v.baseline else set()
        mine = {p.rsplit("/", 1)[0] if "/" in p else "" for p in files}
        if not dirs:
            rows.append(_row("test_location", "NOT_CHECKED", "no existing test locations recorded"))
        elif all(any(m == d or m.startswith(d + "/") for d in dirs) for m in mine):   # a parent (src/) isn't a test folder
            rows.append(_row("test_location", "PASS", f"in the repo's existing test folders ({', '.join(sorted(mine)) or 'root'})"))
        else:
            rows.append(_row("test_location", "REVIEW_REQUIRED", f"{', '.join(sorted(mine)) or 'root'} isn't one of the repo's test folders"))
        own = {p.split("/")[0] for p in files} | {p.split("/")[1] for p in files if p.startswith("src/") and p.count("/") > 1}
        own |= {t.split("/")[0] for t in (v.baseline.pass_set if v.baseline else [])}
        names = set().union(*map(_imports, src.values())) if src else set()
        own |= _first_party(v)
        extra = sorted(n for n in names if n not in sys.stdlib_module_names and n not in {"pytest", "conftest"} and n not in own
                       and not n.startswith("_"))
        rows.append(_row("new_imports", "REVIEW_REQUIRED" if extra else "PASS",
                         f"imports {', '.join(extra)}: make sure the repo already depends on {'them' if len(extra) > 1 else 'it'}" if extra
                         else "only the standard library, pytest and the project's own code"))

    u = v.repro.uncovered if v.repro else None
    # A's review of #86: "covers everything" is the test designer's claim, so it's never a code-decided PASS
    rows.append(_row("covers_issue", "NOT_CHECKED" if u is None else "NOT_COVERED" if u else "REVIEW_REQUIRED",
                     "not checked" if u is None else "leaves out: " + "; ".join(u) if u
                     else "the test designer says it checks every stated condition (its own claim, not checked by code)"))
    hv = v.verify.hidden_variant if v.verify else None
    rows.append(_row("hidden_variant", {CheckStatus.PASSED: "PASS", CheckStatus.FAILED: "FAIL",
                                        CheckStatus.INCONCLUSIVE: "REVIEW_REQUIRED"}.get(hv, "NOT_CHECKED"),
                     ("the fix also passes a variant of the test it never saw" if hv == CheckStatus.PASSED else
                      "the fix fails a variant of the test it never saw" if hv == CheckStatus.FAILED else
                      "it ran, but the result was inconclusive" if hv == CheckStatus.INCONCLUSIVE else "not run")
                     + "; a variant alone doesn't prove the fix is right"))
    return rows


def _first_party(v: RunView) -> set[str]:
    """Top-level names the fix touches: the package under test is never a new dependency."""
    raw = artifacts.get(v.patch.fix_diff_id) if v.patch else None
    paths = _files(raw.decode("utf-8", "replace")) if raw else {}
    return {(p.split("/")[1] if p.startswith("src/") else p.split("/")[0]).removesuffix(".py") for p in paths}   # src/calc.py too


LABEL = {"fails_on_base": "Fails on the original code", "passes_with_fix": "Passes with the fix", "assertions": "Real assertions",
         "mocks": "Mocks", "existing_tests": "Existing tests untouched", "test_location": "Follows the repo's test layout",
         "new_imports": "No new dependencies", "covers_issue": "Covers what the issue expects", "hidden_variant": "Hidden variant"}


def report_lines(v: RunView) -> list[str]:
    if not v.repro:
        return ["## Test quality", "- Not checked: no regression test was written.", ""]
    out = ["## Test quality", "Decided by code from the test and its runs, not by a model.", "", "| Check | Result | Notes |", "|---|---|---|"]
    out += [f"| {LABEL[r['check']]} | {r['status']} | {r['note'].replace('|', chr(92) + '|')} |" for r in report(v)]
    return [*out, ""]
