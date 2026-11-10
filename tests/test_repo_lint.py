"""The repo's own checks on the change (#70 item 3; mcstatus #1238: basedpyright's reportUnusedCallResult failed CI on our test).
One row per tool: PASS / FAIL / NOT_RUN / UNSUPPORTED / BLOCKED, with the command and exit code. Never a silent pass."""
import json
import shutil
import subprocess
import sys

import pytest

from backend import db
from backend.agents import lint as L
from backend.sandbox import docker
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


def test_a_later_attempt_that_raises_never_shows_the_earlier_rows(sandbox):
    # A #74 review, item 2: attempt 1 stored PASS rows; attempt 2's sandbox raises (review.py swallows it)
    key = "repo_checks:" + "r" * 32
    db.put_kv(db.connect(), key, json.dumps({"checks": [{"tool": "ruff check", "status": "PASS"}], "files": ["a.py"], "reason": None}))
    def boom(*a, **k):
        raise RuntimeError("docker died")
    sandbox.setattr(L.docker, "run", boom)
    with pytest.raises(RuntimeError):
        L.review_concerns("r" * 32, "", DIFF("a.py"))
    assert json.loads(db.get_kv(db.connect(), key)) == {"checks": [], "files": ["a.py"], "reason": "sandbox_failed"}


def test_a_timeout_marks_every_tool_that_never_started():
    # A #74 review, item 3: the plan lists ruff + mypy; the run stopped inside ruff check, so mypy never started
    after = ("@@PP_PLAN ruff check\n@@PP_PLAN ruff format\n@@PP_PLAN mypy\n@@PP_MISSING black\n@@PP_TOOL ruff check|python -m ruff check\n"
             "[stopped: hit the time limit (300 s) before this finished]\n")
    got = {r["tool"]: (r["status"], r["note"]) for r in L.rows("", after)}
    assert got["ruff check"][0] == "BLOCKED" and got["black"][0] == "NOT_RUN"
    assert got["ruff format"] == got["mypy"] == ("BLOCKED", "timed out before it ran")


def test_the_concern_counts_every_new_problem_not_the_stored_twenty(sandbox):
    after = "@@PP_TOOL mypy|m\n" + "".join(f"a.py:{i}: error: e{i}\n" for i in range(25)) + "@@PP_EXIT 1\n"
    sandbox.setattr(L.docker, "run", lambda *a, **k: Result(0, "@@PP_AFTER\n" + after))
    [c] = L.review_concerns("r" * 32, "", DIFF("a.py"))
    assert "reports 25 new problems" in c["text"]


@pytest.mark.skipif(not shutil.which("sh"), reason="needs sh")
def test_contributing_counts_commands_not_prose(tmp_path):
    # A #74 review, item 5: "black-box tests" / "we dropped flake8" must not run a linter; a command line in a code block does
    (tmp_path / "CONTRIBUTING.md").write_text("We write black-box tests. We dropped flake8 last year.\n"
                                             "```\n$ python -m mypy src\n```\nOr run `ruff check .` before pushing.\n")
    probe = "".join(f"said '{t}' && echo {t[-7:] if 'pyright' in t else t}\n" for t in ("black", "flake8", "mypy", "ruff", "(based)?pyright"))
    out = subprocess.run([shutil.which("sh"), "-c", L.TOOLS + "\n" + probe], cwd=tmp_path, capture_output=True, text=True).stdout
    assert out.split() == ["mypy", "ruff"]
    plan = subprocess.run([shutil.which("sh"), "-c", L.TOOLS + "\nPLAN=1; lint a.py"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert L.SEP not in plan and L.MISSING not in plan   # the plan pass only lists; it runs and reports nothing


@pytest.mark.skipif(not shutil.which("sh") or subprocess.run([sys.executable, "-m", "ruff", "--version"], capture_output=True).returncode != 0,
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


# #99 (wheelgap#133: our test file would have failed `ruff format`, but the row only said "not run" because the repo's env had no
# ruff). Real pp-base container, no network, the repo installs no ruff: PatchPilot's own pinned ruff must run the format check.
def _in_pp_base(files: dict[str, str], *paths: str) -> dict[str, dict]:
    import shlex
    import uuid
    write = "".join(f"printf %s {shlex.quote(body)} > {shlex.quote(p)}\n" for p, body in files.items())
    r = docker.run("pp-base:3.12", write + L.TOOLS + f"\nlint {' '.join(shlex.quote(p) for p in paths)}\n",
                   name=f"pp-test-lint-{uuid.uuid4().hex[:6]}", timeout=120)
    return {row["tool"]: row for row in L.rows("", r.out)}


needs_pp_base = pytest.mark.skipif(not shutil.which("docker") or docker._docker("image", "inspect", "pp-base:3.12").code,
                                   reason="needs Docker and pp-base:3.12")


@needs_pp_base
def test_ruff_format_fails_a_badly_formatted_file_even_when_the_repo_installs_no_ruff():
    rows = _in_pp_base({"pyproject.toml": "[tool.ruff]\nline-length = 100\n", "a.py": "x=[1,2 ,3]\n"}, "a.py")
    assert rows["ruff format"]["status"] == "FAIL" and rows["ruff format"]["new"] == ["a.py: would reformat"]
    assert "/opt/pp-tools/bin/ruff format --check" in rows["ruff format"]["command"]


@needs_pp_base
def test_ruff_format_passes_a_clean_file():
    rows = _in_pp_base({"ruff.toml": "line-length = 100\n", "a.py": "x = [1, 2, 3]\n"}, "a.py")
    assert rows["ruff format"]["status"] == "PASS"


@needs_pp_base
def test_no_ruff_config_means_no_format_row():
    assert "ruff format" not in _in_pp_base({"a.py": "x=[1,2 ,3]\n"}, "a.py")   # not detected: never shown as a pass
