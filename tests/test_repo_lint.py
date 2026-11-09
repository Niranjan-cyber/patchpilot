"""The repo's own checks on the change (#70 item 3; mcstatus #1238: basedpyright's reportUnusedCallResult failed CI on our test).
One row per tool: PASS / FAIL / NOT_RUN / UNSUPPORTED / BLOCKED, with the command and exit code. Never a silent pass."""
import json
import shutil
import subprocess

import pytest

from backend import db
from backend.agents import lint as L
from backend.sandbox.docker import Result

BEFORE = """@@PP_TOOL ruff check|python -m ruff check --no-cache --output-format concise -- mcstatus/bedrock.py
mcstatus/bedrock.py:40:5: F401 [*] `os` imported but unused
Found 1 error.
@@PP_EXIT 1
@@PP_TOOL ruff format|python -m ruff format --check --no-cache -- mcstatus/bedrock.py
1 file already formatted
@@PP_EXIT 0
@@PP_TOOL basedpyright|basedpyright ./mcstatus/bedrock.py
/src/mcstatus/bedrock.py:12:9 - error: Type of "x" is unknown (reportUnknownVariableType)
1 error, 0 warnings, 0 notes
@@PP_EXIT 1
"""
AFTER = """@@PP_TOOL ruff check|python -m ruff check --no-cache --output-format concise -- mcstatus/bedrock.py tests/protocol/test_patchpilot_issue_1237.py
mcstatus/bedrock.py:44:5: F401 [*] `os` imported but unused
Found 1 error.
@@PP_EXIT 1
@@PP_TOOL ruff format|python -m ruff format --check --no-cache -- mcstatus/bedrock.py tests/protocol/test_patchpilot_issue_1237.py
Would reformat: tests/protocol/test_patchpilot_issue_1237.py
1 file would be reformatted
@@PP_EXIT 1
@@PP_TOOL basedpyright|basedpyright ./mcstatus/bedrock.py ./tests/protocol/test_patchpilot_issue_1237.py
/src/mcstatus/bedrock.py:14:9 - error: Type of "x" is unknown (reportUnknownVariableType)
/src/tests/protocol/test_patchpilot_issue_1237.py:22:5 - error: Result of call expression is of type "dict" and is not used (reportUnusedCallResult)
2 errors, 0 warnings, 0 notes
@@PP_EXIT 1
@@PP_TOOL mypy|python -m mypy --no-incremental --no-error-summary -- mcstatus/bedrock.py
mypy.ini: [mypy]: Unrecognized option: plugins = pydantic.mypy
@@PP_EXIT 2
@@PP_MISSING flake8
@@PP_HOOKS ruff codespell check-yaml
"""
DIFF = lambda p: f"diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n@@ -1 +1 @@\n-a\n+b\n"


def test_only_problems_the_change_adds_count():
    # a problem that only moved lines (F401 40 -> 44, pyright 12 -> 14) is not new; summary lines are ignored
    new = L.new_problems(BEFORE, AFTER)
    assert set(new) == {"ruff format", "basedpyright"}
    assert new["ruff format"] == ["tests/protocol/test_patchpilot_issue_1237.py: would reformat"]
    assert "reportUnusedCallResult" in new["basedpyright"][0] and len(new["basedpyright"]) == 1


def test_one_row_per_tool_with_command_and_exit_code():
    rows = {r["tool"]: r for r in L.rows(BEFORE, AFTER)}
    assert rows["ruff check"]["status"] == "PASS" and "1 were already there" in rows["ruff check"]["note"]
    assert rows["ruff check"]["exit_code"] == 1 and rows["ruff check"]["command"].startswith("python -m ruff check")
    assert " -- " in rows["ruff check"]["command"]                      # file arguments after --
    assert rows["ruff format"]["status"] == "FAIL" and rows["basedpyright"]["status"] == "FAIL"
    assert rows["mypy"]["status"] == "BLOCKED" and "Unrecognized option" in rows["mypy"]["note"]   # a config error isn't a pass
    assert rows["flake8"]["status"] == "NOT_RUN" and rows["flake8"]["exit_code"] is None
    assert rows["pre-commit: codespell"]["status"] == "UNSUPPORTED" and rows["pre-commit: check-yaml"]["status"] == "UNSUPPORTED"
    assert "pre-commit: ruff" not in rows                                 # a hook we do run isn't listed twice


def test_cut_off_output_with_new_problems_is_still_a_fail():
    out = "@@PP_TOOL mypy|python -m mypy -- a.py\na.py:3: error: Incompatible return value type  [return-value]\n"
    assert L.rows("", out)[0]["status"] == "FAIL"
    assert L.rows("", "@@PP_TOOL mypy|python -m mypy -- a.py\n")[0]["status"] == "BLOCKED"   # no exit code, nothing read


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(L, "image", lambda rid: "img"); monkeypatch.setattr(L, "snap", lambda rid: "vol")
    return monkeypatch


def test_concerns_and_stored_rows_from_a_sandbox_run(sandbox):
    seen = {}
    sandbox.setattr(L.docker, "run", lambda img, script, **k: (seen.setdefault("s", script), Result(0, BEFORE + "@@PP_AFTER\n" + AFTER))[1])
    cs = L.review_concerns("r" * 32, DIFF("tests/protocol/test_patchpilot_issue_1237.py"), DIFF("mcstatus/bedrock.py"))
    assert [c["severity"] for c in cs] == ["medium", "medium"] and any("basedpyright reports 1 new problem" in c["text"] for c in cs)
    stored = json.loads(db.get_kv(db.connect(), "repo_checks:" + "r" * 32))
    assert stored["reason"] is None and {r["status"] for r in stored["checks"]} == {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "UNSUPPORTED"}
    assert 'set -- "$@" "$f"' in seen["s"]   # the before-run keeps paths with spaces whole


def test_nothing_claimed_when_not_run(sandbox):
    sandbox.setattr(L.docker, "run", lambda *a, **k: Result(3, "APPLY_FAILED"))
    assert L.review_concerns("r" * 32, "", DIFF("a.py")) == []
    assert json.loads(db.get_kv(db.connect(), "repo_checks:" + "r" * 32))["reason"] == "diff_did_not_apply"
    assert L.review_concerns("r" * 32, "", DIFF("README.md")) == []   # no Python file changed: no sandbox run at all
    assert json.loads(db.get_kv(db.connect(), "repo_checks:" + "r" * 32))["reason"] == "no_python_files"


@pytest.mark.skipif(not shutil.which("sh") or subprocess.run(["python", "-m", "ruff", "--version"], capture_output=True).returncode != 0,
                    reason="needs sh and ruff")
def test_the_real_shell_finds_ruff_through_ci_and_runs_it_with_dashdash(tmp_path):
    # ruff is configured nowhere but the CI workflow: discovery must still find it; "-x.py" must stay a file, not an option
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("steps:\n  - run: ruff check .\n")
    (tmp_path / "-x.py").write_text("import os\n")
    (tmp_path / ".pre-commit-config.yaml").write_text("repos:\n  - hooks:\n      - id: codespell\n      - id: ruff\n")
    out = subprocess.run([shutil.which("sh"), "-c", L.TOOLS + '\nlint "-x.py"\nhooks'], cwd=tmp_path, capture_output=True, text=True).stdout
    rows = {r["tool"]: r for r in L.rows("", out)}
    assert rows["ruff check"]["status"] == "FAIL" and "-x.py: F401" in rows["ruff check"]["new"][0]
    assert rows["pre-commit: codespell"]["status"] == "UNSUPPORTED"


def test_report_and_api_show_rows_and_never_call_a_missing_check_passed(sandbox):
    from fastapi.testclient import TestClient
    from backend.api import main
    from backend.contracts.models import IssueSpec, RepoPolicy
    from backend.github.reader import IssueCheck
    from backend.report import repo_checks_section
    url = "https://github.com/o/r/issues/1"
    chk = IssueCheck(issue=IssueSpec(html_url=url, repo="o/r", number=1, title="t"), base_sha="abc", default_branch="main",
                     language="Python", policy=RepoPolicy(), fetched_at=db.now())
    sandbox.setattr(main, "check_issue", lambda u: chk)
    b = TestClient(main.app, base_url="https://testserver")
    rid = b.post("/api/runs", json={"issue_url": url}).json()["run_id"]
    assert b.get(f"/api/runs/{rid}/repo-checks").json() == {"checks": None, "files": [], "reason": "not_run_yet"}
    assert "Not checked" in "\n".join(repo_checks_section(rid))
    db.put_kv(db.connect(), f"repo_checks:{rid}", json.dumps({"checks": L.rows(BEFORE, AFTER), "files": [], "reason": None}))
    text = "\n".join(repo_checks_section(rid))
    assert "| ruff format | FAIL | 1 |" in text and "| flake8 | NOT_RUN | - |" in text and "| mypy | BLOCKED | 2 |" in text
    assert TestClient(main.app, base_url="https://testserver").get(f"/api/runs/{rid}/repo-checks").status_code == 404   # owner only
