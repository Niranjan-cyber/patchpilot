"""#120: G2 partial collection wiring: setup records the files that never loaded, later full-suite runs skip them,
and the baseline counts as partial (readiness capped)."""
import pytest

from backend import db
from backend.contracts.models import CheckStatus, IssueSpec
from backend.report import render
from backend.sandbox import steps
from backend.sandbox.docker import Result
from backend.worker.nodes import StepContext

OUT = ("INSTALL_EXIT=0\nCOLLECT_EXIT=2\nCOLLECTED=2298\nUNCOLLECTABLE=test_autoarray/inversion/test_sibson.py\n"
       "TEST_FILES=180\nE   ModuleNotFoundError: No module named 'numba'\n")
XML = '<testsuites><testsuite><testcase classname="test_autoarray.test_a" name="test_ok"/></testsuite></testsuites>'


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t"), "sha")
    calls = []
    monkeypatch.setattr(steps.docker, "ensure_infra", lambda: None)
    monkeypatch.setattr(steps.docker, "commit", lambda *a: None)
    monkeypatch.setattr(steps.docker, "rm", lambda *a: None)
    def run(img, cmd, **k):
        calls.append(cmd)
        return Result(0, OUT) if "collect-only" in cmd else Result(0, "EXIT=0\n<<<JUNIT>>>" + XML)
    monkeypatch.setattr(steps.docker, "run", run)
    return StepContext(v.run_id, db.get_run(db.connect(), v.run_id), lambda *a, **p: None), calls


def test_a_few_unloadable_files_pass_setup_and_are_skipped_in_the_baseline(ctx):
    c, calls = ctx
    g = steps.setup(c)
    assert (g.status, g.reason) == (CheckStatus.PASSED, "partial_collection")
    assert "1 test file couldn't load" in c.scratch["headline"]
    steps.baseline(c)
    assert "--ignore=test_autoarray/inversion/test_sibson.py" in calls[-1]
    v = db.get_run(db.connect(), c.run_id)
    assert v.baseline.partial is True                       # caps readiness at "Needs attention" (contracts §1.3)
    assert "`test_autoarray/inversion/test_sibson.py`" in render(v, skipped=steps.skipped_files(c.run_id))


def test_a_name_we_cannot_pass_to_pytest_fails_closed(ctx, monkeypatch):
    c, calls = ctx
    bad = OUT.replace("UNCOLLECTABLE=test_autoarray/inversion/test_sibson.py", "UNCOLLECTABLE=--rootdir=/etc/x.py")
    monkeypatch.setattr(steps.docker, "run", lambda img, cmd, **k: Result(0, bad))
    assert steps.setup(c).reason == "collection_error" and steps.skipped_files(c.run_id) == []
