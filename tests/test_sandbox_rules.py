from datetime import date

import pytest
from backend.contracts.models import CheckStatus as C
from backend.sandbox.rules import (baseline_sets, evaluate_setup, junit_outcomes, map_supplyguard, release_tag_before,
                                   uncollectable_files)


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


def test_g1_popular_lookalike_is_a_finding_not_a_block():
    # #118: real SupplyGuard signal from aws-powertools#8796 (Indian digit grouping), 473k downloads/week
    sig = {"kind": "lookalike", "confidence": "high", "weight": 45,
           "evidence": 'Name resembles popular package "retry" (one character different); 4,73,064 downloads last week; '
                       "first published 2021-07-26"}
    st, reason, f = map_supplyguard(1, proj(suspicious=[{"packageId": "pypi:retry2@0.9.5", "risk": "medium", "signals": [sig]}]))
    assert (st, reason) == (C.PASSED, "no_malicious_packages") and f[0]["package"] == "pypi:retry2@0.9.5"


@pytest.mark.parametrize("evidence", [
    'resembles "requests"; 312 downloads last week; first published 2019-01-01',     # unpopular
    'resembles "requests"; 90,000 downloads last week; first published 2026-10-20',  # popular but new: inflated downloads
    'resembles "requests"; 90,000 downloads last week',                              # age unknown
    'resembles "requests"; , downloads last week; first published 2019-01-01',       # no digits: must not crash
    'resembles "requests"; 1.2M downloads last week; first published 2019-01-01',    # a wording we don't parse
    'resembles "requests"', ""])
def test_g1_unpopular_new_or_unknown_lookalike_still_blocks(evidence):
    sig = {"kind": "lookalike", "confidence": "high", "evidence": evidence}
    r = proj(suspicious=[{"packageId": "pypi:reqeusts@1", "signals": [sig]}])
    assert map_supplyguard(1, r, today=date(2026, 11, 11))[0] == C.BLOCKED


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


def test_g2_a_few_uncollectable_files_pass_as_partial_collection():
    # #120: PyAutoArray#687 (2,298 tests, 1 file needs the optional numba) and corgidrp#1087 (the e2e data files)
    assert evaluate_setup(0, False, 2, 2298, uncollectable=1, test_files=180) == (C.PASSED, "partial_collection")
    assert evaluate_setup(0, False, 2, 348, uncollectable=10, test_files=60) == (C.PASSED, "partial_collection")
    assert evaluate_setup(0, False, 2, 348, uncollectable=11, test_files=200)[1] == "collection_error"   # more than 10 files
    assert evaluate_setup(0, False, 2, 40, uncollectable=3, test_files=5)[1] == "collection_error"      # more than 20%
    assert evaluate_setup(0, False, 2, 0, uncollectable=1, test_files=9)[1] == "collection_error"       # nothing collected
    assert evaluate_setup(0, False, 2, 50)[1] == "collection_error"     # errors we couldn't name: fail closed
    assert evaluate_setup(0, False, 4, 50, uncollectable=1, test_files=9)[1] == "collection_error"      # usage error, not 2


def test_uncollectable_files_are_read_from_the_collect_summary():
    out = ("COLLECT_EXIT=2\nUNCOLLECTABLE=tests/e2e_tests/astrom_e2e.py\nUNCOLLECTABLE=tests/e2e_tests/kgain_e2e.py\n"
           "UNCOLLECTABLE=-rf\nUNCOLLECTABLE=../etc/x.py\nUNCOLLECTABLE=tests/a b.py\nTEST_FILES=60\n")
    assert uncollectable_files(out) == ["tests/e2e_tests/astrom_e2e.py", "tests/e2e_tests/kgain_e2e.py"]   # odd paths dropped


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


def test_release_tags_that_look_like_git_options_are_ignored():
    # the tag name is untrusted (repo-controlled) and is passed to `git tag` on the HOST
    rel = lambda t, d: {"tag_name": t, "published_at": d, "draft": False}
    assert release_tag_before([rel("--file=/etc/passwd", "2026-01-02T00:00:00Z")], "2026-02-01T00:00:00Z") is None
    assert release_tag_before([rel("v1.2.0", "2026-01-01T00:00:00Z"), rel("-d", "2026-01-02T00:00:00Z")],
                              "2026-02-01T00:00:00Z") == "v1.2.0"


def test_baseline_ignores_a_test_that_prints_the_junit_separator(monkeypatch):
    # B's review of #42: _pytest split on the FIRST '<<<JUNIT>>>', so a test echoing it shadowed the real one
    from backend.sandbox import docker, steps
    out = "EXIT=0\nsome test printed <<<JUNIT>>> here\n1 passed\n<<<JUNIT>>>\n" + XML
    monkeypatch.setattr(steps.docker, "run", lambda *a, **k: docker.Result(0, out))
    assert steps._pytest("r", "")[0] == junit_outcomes(XML) != {}


# G1 for pyproject-only repos (requests #7642, rich #4249, networkx #8997 had no lock file, so G1 was always inconclusive):
# the requirements G2 will install, read without running anything. None = unknown -> G1 stays inconclusive.
from backend.sandbox.rules import pyproject_requirements as preqs

RICH = '''[project]
name = "rich"
dependencies = ["markdown-it-py>=2.2.0", "pygments>=2.13.0,<3.0.0"]
[project.optional-dependencies]
jupyter = ["ipywidgets>=7.5.1,<9"]
[dependency-groups]
dev = ["mypy", {include-group = "test"}]
test = ["pytest>=8", "attrs"]
docs = ["sphinx"]
'''


def test_pyproject_deps_plus_what_g2_installs():
    # dependencies + the test groups G2 installs (includes followed); not unrelated extras or groups; pytest always
    assert preqs(RICH) == ["markdown-it-py>=2.2.0", "pygments>=2.13.0,<3.0.0", "pytest>=8", "attrs", "mypy", "pytest"]


def test_pyproject_first_test_extra_only_like_g2():
    t = '[project]\ndependencies = []\n[project.optional-dependencies]\ntests = ["hypothesis"]\ndev = ["black"]\n'
    assert preqs(t) == ["hypothesis", "pytest"]


@pytest.mark.parametrize("text", [
    '[project]\nname = "x"\ndynamic = ["version", "dependencies"]\n',    # declared elsewhere (setup.py): unknown
    '[tool.poetry.dependencies]\npython = "^3.10"\n',                     # no [project] table
    '[project\nbroken',                                                     # not TOML
    '[project]\ndependencies = "requests"\n',                               # not a list
])
def test_pyproject_unknown_is_none(text):
    assert preqs(text) is None


def test_no_supported_files_is_named_even_without_a_json_report():   # smart_open-833: exit 3 + plain text was "unavailable"
    assert map_supplyguard(3, None)[1] == "no_supported_dependency_files"


SMART_OPEN_SETUP = """
import os
def _get_version(): return '1'
base_deps = ['wrapt']
aws_deps = ['boto3']
zst_deps = ['zstandard']
all_deps = aws_deps + zst_deps
tests_require = all_deps + ['pytest', 'moto[server]']
setup(name='smart_open', install_requires=base_deps, extras_require={'test': tests_require, 'aws': aws_deps})
"""


def test_setup_py_requirements_are_read_without_running_it():   # smart_open-833: deps only in setup.py → G1 inconclusive
    from backend.sandbox.rules import setup_requirements
    assert setup_requirements(SMART_OPEN_SETUP, None) == ["wrapt", "boto3", "zstandard", "pytest", "moto[server]"]
    cfg = "[options]\ninstall_requires =\n    requests>=2\n    click\n[options.extras_require]\ntest =\n    pytest\n"
    assert setup_requirements(None, cfg) == ["requests>=2", "click", "pytest"]
    assert setup_requirements("setup(install_requires=get_deps())", None) is None          # not static: unknown, never empty
    assert setup_requirements("x = 1", None) is None
    assert setup_requirements("setup(install_requires=open('r').read().split())", None) is None
