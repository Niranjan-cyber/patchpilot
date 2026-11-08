"""G2's test count must not depend on the repo's pytest verbosity (tabulate #494 run 2f36f258: `addopts = "-v"`
cancelled our `-q`, pytest printed a <Module>/<Function> tree with no `::` lines, and 383 tests counted as 0)."""
import re
import shutil
import subprocess

import pytest

from backend.sandbox.steps import INSTALL

TREE = """<Dir tabulate>
  <Module test/test_api.py>
    <Function test_tabulate_formats>
  <Module test/test_output.py>
    <Function test_ragged_rows>
    <Function test_github_escape_pipe_character>

========================= 3 tests collected in 0.28s =========================
"""
QUIET = "test/test_api.py::test_tabulate_formats\ntest/test_output.py::test_ragged_rows\n\n2 tests collected in 0.01s\n"
ONE = "test_x.py::test_only\n\n1 test collected in 0.01s\n"
NO_SUMMARY = "test_x.py::test_a\ntest_x.py::test_b\n"   # truncated log: fall back to counting node ids
NONE = "\nno tests collected in 0.01s\n"
# repo addopts "-q" + our -q = -qq (msoffcrypto-tool, run d20ce608): per-file counts, no ids, no summary
QQ = "msoffcrypto/__init__.py: 1\nmsoffcrypto/format/ppt97.py: 2\ntests/test_cli.py: 1\ntests/test_xls_padding.py: 5\n"


DESELECTED = "test_x.py::test_b\ntest_x.py::test_c\n\n2/3 tests collected (1 deselected) in 0.07s\n"   # real pytest 8 output
ALL_DESELECTED = "\n0/3 tests collected (3 deselected) in 0.01s\n"   # nothing runnable: must be 0, not 3


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
@pytest.mark.parametrize("log, want", [(TREE, 3), (QUIET, 2), (ONE, 1), (NO_SUMMARY, 2), (NONE, 0), (QQ, 9),
                                       (DESELECTED, 2), (ALL_DESELECTED, 0)])
def test_collected_count_reads_pytest_summary(tmp_path, log, want):
    line = re.search(r'^(?:(?:n=|\[ -n).*\n)*echo "COLLECTED=.*$', INSTALL, re.M).group(0).split("; tail")[0]
    f = tmp_path / "collect.log"
    f.write_text(log, encoding="utf-8")
    bash = shutil.which("bash")   # full path: a bare "bash" on Windows starts WSL
    out = subprocess.run([bash, "-c", line.replace("/tmp/collect.log", f"'{f.as_posix()}'")],
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == f"COLLECTED={want}"
