"""Integration: needs Docker + pp-base:3.12 (infra/Dockerfile.base). Skipped when Docker isn't available."""
import os
import shutil
import subprocess
import uuid

import pytest

from backend.sandbox import docker
from backend.sandbox.steps import INSTALL

pytestmark = pytest.mark.skipif(not shutil.which("docker") or docker._docker("image", "inspect", "pp-base:3.12").code,
                                reason="needs Docker and pp-base:3.12")


def run(script, **kw):
    return docker.run("pp-base:3.12", script, name=f"pp-test-{uuid.uuid4().hex[:6]}", timeout=60, **kw)


def test_step_container_has_no_network():
    r = run("python -c \"import urllib.request; urllib.request.urlopen('https://pypi.org', timeout=5)\"")
    assert r.code != 0


def test_no_host_secrets_and_not_root(monkeypatch):
    monkeypatch.setenv("GITHUB_READ_TOKEN", "should-never-leak")
    r = run("env; id -u")
    assert "should-never-leak" not in r.out and "GITHUB" not in r.out and r.out.strip().endswith("1000")


def test_root_filesystem_is_read_only():
    assert run("touch /opt/venv/x").code != 0


# #26: a stub pip (shell function) stands in for PyPI, so these run offline in seconds
STUB_PIP = ("pip() { echo \"pip $*\" >> /tmp/calls; case \"$*\" in *'.[test]'*) echo \"WARNING: demo does not provide the extra 'test'\";; esac;"
            " case \"$*\" in *'-e .['*) echo made-at-install > /src/gen_version.py;; esac; return 0; }; ")


def project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / ".gitignore").write_text("gen_version.py\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(tmp_path)]
    for a in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(git + a, check=True, capture_output=True)
    vol = f"pp-snap-test-{uuid.uuid4().hex[:6]}"
    docker.make_snapshot(vol, str(tmp_path))
    return vol


def test_install_moves_past_an_extra_pip_only_warns_about(tmp_path):
    vol = project(tmp_path)
    try:
        r = run(STUB_PIP + INSTALL + "\ncat /tmp/calls", snapshot_volume=vol, read_only=False)
        assert "pip install -q -e .[test]" in r.out and "pip install -q -e .[tests]" in r.out   # [test] only warned: went on
        assert "-e .[testing]" not in r.out                                                     # stopped at the first real extra
        cmds = [line for line in r.out.splitlines() if line.startswith("+ ")]   # what EnvProfile.install_cmds records
        assert cmds == ["+ pip install -e .[tests]"]
    finally:
        docker.rm_volume(vol)


def test_files_generated_at_setup_reach_later_steps_but_never_the_diff(tmp_path):
    vol, name, img = project(tmp_path), f"pp-test-{uuid.uuid4().hex[:6]}", f"pp-test-img-{uuid.uuid4().hex[:6]}"
    try:
        docker.run("pp-base:3.12", STUB_PIP + INSTALL, name=name, timeout=60, snapshot_volume=vol, read_only=False, keep=True)
        docker.commit(name, img)
        r = docker.run(img, "cat gen_version.py; git add -A; git status --porcelain", name=f"pp-test-{uuid.uuid4().hex[:6]}",
                       timeout=60, snapshot_volume=vol)
        assert "made-at-install" in r.out                                  # was lost before #26
        assert "gen_version.py" not in r.out.replace("made-at-install", "")   # ignored file: not part of any diff
    finally:
        docker.rm(name); docker.rm_image(img); docker.rm_volume(vol)
