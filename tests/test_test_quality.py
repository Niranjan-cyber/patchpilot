"""#70 item 8: the regression test's quality, decided by code from the test diff and its runs (trust plan §7)."""
import pytest

from backend import artifacts
from backend.agents.test_quality import report, report_lines
from backend.contracts.models import (CheckStatus as S, IssueSpec, Patch, ReproTest, RunStatus, RunView, TestRun, Verification)

NEW = lambda path, body: f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n" + "".join(f"+{l}\n" for l in body.splitlines())
FIX = "diff --git a/src/calc/core.py b/src/calc/core.py\n--- a/src/calc/core.py\n+++ b/src/calc/core.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
GOOD = """import pytest
from calc.core import div


def test_div_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        div(1, 0)


def test_div():
    assert div(4, 2) == 2
"""


def run(test_diff=None, *, base=(S.FAILED, S.FAILED), runs=(S.PASSED, S.PASSED), uncovered=(), hv=S.PASSED, baseline=("tests/test_old.py::t",)):
    t = __import__("backend.db", fromlist=["now"]).now()
    return RunView(run_id="r" * 32, status=RunStatus.AWAITING_APPROVAL, base_sha="a" * 40, created_at=t, updated_at=t,
                   issue=IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t"),
                   repro=ReproTest(test_diff_id=artifacts.put(test_diff if test_diff is not None else NEW("tests/test_issue_1.py", GOOD)),
                                   test_ids=["tests/test_issue_1.py::test_div"], expected_failure="e", runs_on_base=list(base),
                                   uncovered=list(uncovered) if uncovered is not None else None),
                   patch=Patch(fix_diff_id=artifacts.put(FIX), test_diff_id="x", attempt=1, policy_result=S.PASSED),
                   verify=Verification(new_test_runs=list(runs), hidden_variant=hv), baseline=TestRun(pass_set=list(baseline)))


def rows(v):
    return {r["check"]: (r["status"], r["note"]) for r in report(v)}


def test_a_good_test_passes_every_row():
    r = rows(run())
    assert {k: s for k, (s, _) in r.items()} == {
        "fails_on_base": "PASS", "passes_with_fix": "PASS", "assertions": "PASS", "mocks": "PASS", "existing_tests": "PASS",
        "test_location": "PASS", "new_imports": "PASS", "covers_issue": "PASS", "hidden_variant": "PASS"}
    assert "2 checks in 2 functions" in r["assertions"][1]   # pytest.raises counts as a check
    assert "doesn't prove the fix is right" in r["hidden_variant"][1]


@pytest.mark.parametrize("body, status, words", [
    ("def test_x():\n    run_it()\n", "FAIL", "no real check in: test_x"),
    ("def test_x():\n    run_it()\n    assert True\n", "FAIL", "1 always-true asserts"),
    ("import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.assertEqual(f(), 1)\n", "PASS", "1 checks"),
])
def test_assertions_must_check_something(body, status, words):
    s, note = rows(run(NEW("tests/test_issue_1.py", body)))["assertions"]
    assert s == status and words in note


def test_mocks_edits_layout_and_new_imports_need_review():
    body = "from unittest import mock\nimport requests_mock\n\n\ndef test_x():\n    with mock.patch('calc.core.io'):\n        assert div(1, 1) == 1\n"
    r = rows(run(NEW("scratch/test_issue_1.py", body)))
    assert r["mocks"][0] == "REVIEW_REQUIRED" and r["test_location"][0] == "REVIEW_REQUIRED"
    assert r["new_imports"] == ("REVIEW_REQUIRED", "imports requests_mock: make sure the repo already depends on it")
    edit = ("diff --git a/tests/test_old.py b/tests/test_old.py\n--- a/tests/test_old.py\n+++ b/tests/test_old.py\n@@ -3,2 +3,2 @@\n"
            "-    assert f() == 2\n+    assert f() >= 0\n")
    r = rows(run(edit))
    assert r["existing_tests"] == ("REVIEW_REQUIRED", "removes or changes existing lines in tests/test_old.py (1)")
    assert r["assertions"][0] == "PASS" and "read line by line" in r["assertions"][1]   # a hunk, not a whole file


def test_unknown_is_never_pass():
    r = rows(run(base=(), runs=(), uncovered=None, hv=None, baseline=()))
    for k in ("fails_on_base", "passes_with_fix", "covers_issue", "hidden_variant", "test_location"):
        assert r[k][0] == "NOT_CHECKED", k
    r = rows(run(base=(S.FAILED, S.PASSED), uncovered=["works for uppercase"], hv=S.FAILED))
    assert r["fails_on_base"][0] == "FAIL" and r["covers_issue"] == ("NOT_COVERED", "leaves out: works for uppercase")
    assert r["hidden_variant"][0] == "FAIL"
    v = run(); v.repro.test_diff_id = "sha256:" + "0" * 64   # expired / missing artifact
    assert rows(v)["assertions"][0] == "NOT_CHECKED"
    assert rows(run("seed cap"))["assertions"][0] == "NOT_CHECKED"   # not a diff (seeded sample runs): never FAIL or PASS
    case = ("diff --git a/tests/test_old.py b/tests/test_old.py\n--- a/tests/test_old.py\n+++ b/tests/test_old.py\n@@ -3,0 +4 @@\n"
            "+    (\"Https://x\", \"https://x\"),\n")
    assert rows(run(case))["assertions"][0] == "REVIEW_REQUIRED"   # a new parametrize case reuses the existing asserts


def test_report_table_and_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import db
    from backend.api import main
    text = "\n".join(report_lines(run()))
    assert "| Real assertions | PASS |" in text and "not by a model" in text
    v = run(); v.repro = None
    assert report_lines(v)[1] == "- Not checked: no regression test was written."
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(main, "_own", lambda request, rid: None)
    monkeypatch.setattr(db, "get_run", lambda c, rid: run())
    monkeypatch.setattr(main, "_is_real", lambda rid: True)
    got = TestClient(main.app, base_url="https://testserver").get("/api/runs/" + "r" * 32 + "/test-quality").json()
    assert got["reason"] is None and len(got["checks"]) == 9
