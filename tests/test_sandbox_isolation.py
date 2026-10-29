"""Integration: needs Docker + pp-base:3.12 (infra/Dockerfile.base). Skipped when Docker isn't available."""
import os
import shutil
import uuid

import pytest

from backend.sandbox import docker

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
