import importlib


def test_runsc_is_added_to_every_sandbox_when_configured(monkeypatch):
    monkeypatch.setenv("PP_DOCKER_RUNTIME", "runsc")
    d = importlib.reload(importlib.import_module("backend.sandbox.docker"))
    assert d.HARDEN[:2] == ["--runtime", "runsc"]
    monkeypatch.setattr(d, "_docker", lambda *a, **k: d.Result(0, '{"runc":{}}'))
    assert d.runtime_ok()[0] is False                       # configured but missing → refuse
    monkeypatch.delenv("PP_DOCKER_RUNTIME")
    importlib.reload(d)


def test_prototype_default_has_no_runtime_flag():
    d = importlib.import_module("backend.sandbox.docker")
    assert "--runtime" not in d.HARDEN and d.runtime_ok()[0] is True
