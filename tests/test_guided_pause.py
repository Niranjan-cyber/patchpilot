"""B15: optional guided pauses via LangGraph interrupt(). Pause after a step, Continue resumes, no step runs twice."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.api import main
from backend.contracts.models import CheckStatus, GateResult, IssueSpec, RunStatus, StepId
from backend.worker import graph as G
from backend.worker import nodes


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    calls = []
    def make(step):
        def run(ctx):
            calls.append(step.value)
            g = nodes.GATE_OF.get(step)
            return GateResult(gate=g, status=CheckStatus.PASSED, reason="ok") if g else None
        return run
    for s in nodes.ORDER:
        monkeypatch.setitem(nodes.NODES, s, make(s))
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t"), "sha")
    g = G.build(str(tmp_path / "ck.db"))
    return v.run_id, g, {"configurable": {"thread_id": v.run_id}}, calls


def test_pause_after_reproduce_then_continue_runs_each_step_once(env):
    rid, g, cfg, calls = env
    db.put_kv(db.connect(), f"pauses:{rid}", json.dumps(["reproduce"]))
    g.invoke({"run_id": rid, "gates": {}}, cfg)
    v = db.get_run(db.connect(), rid)
    assert v.status == RunStatus.PAUSED and v.pause.reason == "guided_pause" and v.outcome is None
    assert calls == ["preflight", "setup", "baseline", "reproduce"]
    assert g.get_state(cfg).next == ("diagnose",)
    ev = [e for e in db.events_after(db.connect(), rid, 0) if e.type == "run.paused"]
    assert ev and ev[-1].payload["reason"] == "guided_pause" and ev[-1].payload["after"] == "reproduce"

    v.status, v.pause = RunStatus.RUNNING, None; db.save_run(db.connect(), v)     # what the worker's resume job does
    g.invoke(None, cfg)
    assert calls == ["preflight", "setup", "baseline", "reproduce", "diagnose", "fix", "verify", "review"]
    assert db.get_run(db.connect(), rid).outcome is not None


def test_no_pauses_by_default(env):
    rid, g, cfg, calls = env
    g.invoke({"run_id": rid, "gates": {}}, cfg)
    assert len(calls) == 8 and db.get_run(db.connect(), rid).status != RunStatus.PAUSED


def test_stop_while_paused_ends_stopped(env):
    rid, g, cfg, calls = env
    db.put_kv(db.connect(), f"pauses:{rid}", json.dumps(["reproduce"]))
    g.invoke({"run_id": rid, "gates": {}}, cfg)
    db.request_stop(db.connect(), rid)
    g.invoke(None, cfg)
    v = db.get_run(db.connect(), rid)
    assert v.outcome.value == "TRIAGE_ONLY" or v.outcome.value == "STOPPED"
    assert "diagnose" not in calls and v.end_reason.value == "user_stopped"


def test_api_pauses_continue_and_validation(env, monkeypatch):
    rid, g, cfg, calls = env
    monkeypatch.setattr(main, "_own", lambda request, r: None)
    c = TestClient(main.app, base_url="https://testserver")
    assert c.put(f"/api/runs/{rid}/pauses", json={"after": ["setup"]}).status_code == 422
    assert c.put(f"/api/runs/{rid}/pauses", json={"after": ["reproduce", "reproduce"]}).json()["after"] == ["reproduce"]
    assert c.get(f"/api/runs/{rid}/pauses").json()["after"] == ["reproduce"]
    assert c.post(f"/api/runs/{rid}/continue").status_code == 409            # not paused yet
    g.invoke({"run_id": rid, "gates": {}}, cfg)
    assert c.post(f"/api/runs/{rid}/continue").status_code == 200
    c.post(f"/api/runs/{rid}/continue")                                      # double click
    jobs = db.connect().execute("SELECT COUNT(*) FROM jobs WHERE run_id=? AND kind='resume'", (rid,)).fetchone()[0]
    assert jobs == 1
