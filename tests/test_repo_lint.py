"""The repo's own linters on the change (mcstatus #1238: basedpyright's reportUnusedCallResult failed CI on our test)."""
from backend.agents import lint as L
from backend.sandbox.docker import Result

BEFORE = """@@PP_TOOL ruff check
mcstatus/bedrock.py:40:5: F401 [*] `os` imported but unused
Found 1 error.
@@PP_TOOL ruff format
1 file already formatted
@@PP_TOOL basedpyright
/src/mcstatus/bedrock.py:12:9 - error: Type of "x" is unknown (reportUnknownVariableType)
1 error, 0 warnings, 0 notes
"""
AFTER = """@@PP_TOOL ruff check
mcstatus/bedrock.py:44:5: F401 [*] `os` imported but unused
Found 1 error.
@@PP_TOOL ruff format
Would reformat: tests/protocol/test_patchpilot_issue_1237.py
1 file would be reformatted
@@PP_TOOL basedpyright
/src/mcstatus/bedrock.py:14:9 - error: Type of "x" is unknown (reportUnknownVariableType)
/src/tests/protocol/test_patchpilot_issue_1237.py:22:5 - error: Result of call expression is of type "dict" and is not used (reportUnusedCallResult)
2 errors, 0 warnings, 0 notes
"""
DIFF = lambda p: f"diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n@@ -1 +1 @@\n-a\n+b\n"


def test_only_problems_the_change_adds_count():
    # a problem that only moved lines (F401 40 -> 44, pyright 12 -> 14) is not new; summary lines are ignored
    new = L.new_problems(BEFORE, AFTER)
    assert set(new) == {"ruff format", "basedpyright"}
    assert new["ruff format"] == ["tests/protocol/test_patchpilot_issue_1237.py: would reformat"]
    assert "reportUnusedCallResult" in new["basedpyright"][0] and len(new["basedpyright"]) == 1


def test_mypy_lines_parse():
    out = "@@PP_TOOL mypy\npkg/a.py:3: error: Incompatible return value type  [return-value]\n"
    assert L.problems(out)["mypy"] == {("pkg/a.py", "error: Incompatible return value type  [return-value]"): 1}


def test_concerns_from_a_sandbox_run(monkeypatch):
    seen = {}
    monkeypatch.setattr(L, "image", lambda rid: "img"); monkeypatch.setattr(L, "snap", lambda rid: "vol")
    monkeypatch.setattr(L.docker, "run", lambda img, script, **k: (seen.setdefault("s", script), Result(0, BEFORE + "@@PP_AFTER\n" + AFTER))[1])
    cs = L.review_concerns("r" * 32, DIFF("tests/protocol/test_patchpilot_issue_1237.py"), DIFF("mcstatus/bedrock.py"))
    assert [c["severity"] for c in cs] == ["medium", "medium"] and "basedpyright reports 1 new problem" in cs[1]["text"]
    assert "'mcstatus/bedrock.py'" in seen["s"] or "mcstatus/bedrock.py" in seen["s"]


def test_nothing_claimed_when_not_run(monkeypatch):
    monkeypatch.setattr(L, "image", lambda rid: "img"); monkeypatch.setattr(L, "snap", lambda rid: "vol")
    monkeypatch.setattr(L.docker, "run", lambda *a, **k: Result(3, "APPLY_FAILED"))
    assert L.review_concerns("r" * 32, "", DIFF("a.py")) == []
    assert L.review_concerns("r" * 32, "", DIFF("README.md")) == []   # no Python file changed: no sandbox run at all
