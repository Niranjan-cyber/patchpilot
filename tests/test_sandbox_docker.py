"""docker.run's timeout handling (issue #43): a script that redirects its own log to a file and tails it only
at the end leaves the host's capture empty on timeout, unless we grab the file off the (still-alive) container first."""
from backend.sandbox import docker


def test_timeout_recovers_the_log_file_before_killing(monkeypatch):
    calls = []

    def fake_docker(*args, **kw):
        calls.append(args)
        if args[0] == "exec":
            return docker.Result(0, "+ pip install -r requirements.txt\n~ trying pip install -e .[test]\n")
        if args[0] == "kill":
            return docker.Result(0, "")
        return docker.Result(124, "", timed_out=True)   # the `run` itself

    monkeypatch.setattr(docker, "_docker", fake_docker)
    r = docker.run("img", "script", name="pp-test", log_path="/tmp/install.log")

    assert r.timed_out
    assert "pip install -r requirements.txt" in r.out    # not empty (was: sha256 of "")
    assert "hit the time limit" in r.out
    assert calls[-1][0] == "kill"                        # log fetched before the kill, not after


def test_timeout_with_no_output_anywhere_says_so(monkeypatch):
    # #48 §6.3: nothing on stdout and no log file must not become an empty evidence artifact
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: docker.Result(124, "", timed_out=True) if a[0] == "run" else docker.Result(0, ""))
    r = docker.run("img", "script", name="pp-test", timeout=90)
    assert r.timed_out and r.code == 124
    assert r.out == "[stopped: hit the time limit (90 s); the command printed nothing before it was stopped]"


def test_timeout_keeps_host_captured_partial_output(monkeypatch):
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: docker.Result(124, "collected 3 items\n", timed_out=True) if a[0] == "run" else docker.Result(0, ""))
    r = docker.run("img", "script", name="pp-test", timeout=60)
    assert r.out.startswith("collected 3 items") and "hit the time limit (60 s) before this finished" in r.out


def test_subprocess_timeout_bytes_are_decoded(monkeypatch):
    # TimeoutExpired.stdout is bytes even with text=True; it used to be dropped as "not a str"
    import subprocess
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(a[0], 5, output=b"partial out\n", stderr=b"partial err\n")
    monkeypatch.setattr(docker.subprocess, "run", boom)
    r = docker._docker("run", "x", timeout=5)
    assert r.timed_out and r.out == "partial out\npartial err\n"


def test_exec_timeout_is_never_empty(monkeypatch):
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: docker.Result(124, "", timed_out=True) if "-w" in a else docker.Result(0, ""))
    r = docker.exec_("pp-agent", "sleep 999", timeout=30)
    assert r.timed_out and "(30 s)" in r.out and "printed nothing" in r.out
