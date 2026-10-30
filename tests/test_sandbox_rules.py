from backend.contracts.models import CheckStatus as C
from backend.sandbox.rules import baseline_sets, evaluate_setup, junit_outcomes, map_supplyguard, release_tag_before


def proj(**kw):
    base = {"summary": {"incomplete": False}, "suspicious": [], "vulnerabilities": []}
    base.update(kw); return {"projects": [base]}


def test_g1_malicious_blocks_without_override():
    r = proj(suspicious=[{"packageId": "reqeusts@1.0", "risk": "high", "signals": [{"kind": "malicious-advisory"}]}])
    assert map_supplyguard(1, r)[:2] == (C.BLOCKED, "malicious_package")


def test_g1_high_confidence_typosquat_blocks():
    # real SupplyGuard output for its pypi-vulnerable fixture (reqeusts@1.0.0)
    r = proj(suspicious=[{"packageId": "pypi:reqeusts@1.0.0", "risk": "medium",
                          "signals": [{"kind": "lookalike", "confidence": "high"}]}])
    assert map_supplyguard(1, r)[0] == C.BLOCKED


def test_g1_low_confidence_lookalike_is_a_finding():
    r = proj(suspicious=[{"packageId": "flaskk@1", "risk": "low", "signals": [{"kind": "lookalike", "confidence": "medium"}]}])
    st, _, f = map_supplyguard(1, r)
    assert st == C.PASSED and f[0]["kinds"] == ["lookalike"]


def test_g1_cves_dont_block():
    assert map_supplyguard(1, proj(vulnerabilities=[{"id": "GHSA-x", "severity": "high"}]))[0] == C.PASSED


def test_g1_unknown_is_never_clean():
    assert map_supplyguard(None, None)[0] == C.INCONCLUSIVE
    assert map_supplyguard(3, {"projects": []})[1] == "no_supported_dependency_files"
    assert map_supplyguard(2, proj())[0] == C.INCONCLUSIVE
    assert map_supplyguard(0, proj(summary={"incomplete": True}))[0] == C.INCONCLUSIVE
    assert map_supplyguard(0, {"projects": []})[0] == C.INCONCLUSIVE


def test_g2():
    assert evaluate_setup(0, False, 0, 12) == (C.PASSED, "installed_and_collected")
    assert evaluate_setup(1, False, 0, 0)[1] == "install_failed"
    assert evaluate_setup(0, True, 0, 0)[1] == "install_timeout"
    assert evaluate_setup(0, False, 5, 0)[1] == "no_tests_collected"
    assert evaluate_setup(0, False, 2, 0)[1] == "collection_error"


XML = """<testsuites><testsuite>
<testcase classname="tests.test_ops" name="test_add"/>
<testcase classname="tests.test_ops" name="test_pow"><failure message="x"/></testcase>
<testcase classname="tests.test_ops" name="test_flaky"><failure message="x"/></testcase>
<testcase classname="tests.test_ops" name="test_skip"><skipped/></testcase>
</testsuite></testsuites>"""


def test_baseline_sets_with_rerun():
    first = junit_outcomes(XML)
    assert "tests/test_ops.py::test_skip" not in first
    p, f, fl = baseline_sets(first, {"tests/test_ops.py::test_pow": False, "tests/test_ops.py::test_flaky": True})
    assert p == ["tests/test_ops.py::test_add"] and f == ["tests/test_ops.py::test_pow"] and fl == ["tests/test_ops.py::test_flaky"]


def test_junit_garbage_is_empty_not_crash():
    assert junit_outcomes("not xml") == {}


def test_junit_followed_by_stderr_still_parses():
    # run 11: `git apply` warned "new blank line at EOF" on stderr, which lands after the XML in docker output → a verified
    # fix (298 passed) read as no_results
    out = junit_outcomes(XML + "/tmp/d0.diff:59: new blank line at EOF.\n+\nwarning: 1 line adds whitespace errors.\n")
    assert out == junit_outcomes(XML) and out


def test_supplyguard_runs_with_an_absolute_executable(tmp_path, monkeypatch):
    # Windows: `which` returns tsx.CMD as a relative forward-slash path; cmd.exe read "data/..." as a command "data" with a
    # "/tools" switch, so SupplyGuard never ran and G1 was inconclusive on every run
    import os
    from backend import db
    from backend.sandbox import steps
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(steps, "WORK", tmp_path)
    (tmp_path / "r" / "src").mkdir(parents=True)
    monkeypatch.setenv("SUPPLYGUARD_CMD", "data/tools/sg/.bin/tsx data/tools/sg/cli/index.ts")
    monkeypatch.setattr(steps.shutil, "which", lambda x: "data/tools/sg/.bin\tsx.CMD")
    seen = []
    class P: returncode, stdout, stderr = 0, "{}", ""
    monkeypatch.setattr(steps.subprocess, "run", lambda argv, **k: (seen.append(argv), P)[1])
    steps.run_supplyguard("r")
    assert os.path.isabs(seen[0][0])


def test_release_tag_is_newest_release_before_the_base_commit():   # #26: setuptools_scm needs a real tag
    rel = [{"tag_name": "8.1.0", "published_at": "2024-03-01T00:00:00Z"},
           {"tag_name": "8.0.2", "published_at": "2024-01-10T00:00:00Z"},
           {"tag_name": "8.0.3", "published_at": "2024-02-01T00:00:00Z", "draft": True},
           {"tag_name": "8.0.0", "published_at": "2023-12-31T00:00:00Z"},
           {"tag_name": "next", "published_at": None}]
    assert release_tag_before(rel, "2024-02-15T12:00:00Z") == "8.0.2"   # not the later 8.1.0, not the draft
    assert release_tag_before(rel, "2020-01-01T00:00:00Z") is None        # no release yet: no hint, never a guess
    assert release_tag_before([], "2024-02-15T12:00:00Z") is None
