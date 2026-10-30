from backend.contracts.models import CheckStatus as C
from backend.sandbox.rules import baseline_sets, evaluate_setup, junit_outcomes, map_supplyguard


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
