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


def test_timeout_without_log_path_stays_empty(monkeypatch):
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: docker.Result(124, "", timed_out=True) if a[0] == "run" else docker.Result(0, ""))
    r = docker.run("img", "script", name="pp-test")
    assert r.timed_out and r.out == ""
