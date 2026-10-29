from datetime import timedelta

import pytest

from backend import db
from backend.contracts.models import CheckStatus as C, GateResult, IssueSpec, StepId as S
from backend.worker import main as W, nodes
from backend.worker.graph import build

ISSUE = IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("STUB_STEP_SECONDS", "0")
    saved = dict(nodes.NODES)
    nodes.NODES.update({s: nodes._stub(s) for s in nodes.ORDER})   # isolate from real sandbox steps
    yield db.connect(), build(str(tmp_path / "ck.db"))
    nodes.NODES.clear(); nodes.NODES.update(saved)


def passing(calls):
    def mk(step):
        def run(ctx):
            calls.append(step)
            g = nodes.GATE_OF.get(step)
            return GateResult(gate=g, status=C.PASSED, reason="ok") if g else None
        return run
    for s in nodes.ORDER:
        nodes.register(s, mk(s))


def drain(c, graph):
    while (job := W.lease_job(c)):
        W.run_job(graph, job)


def test_create_run_is_atomic(env, monkeypatch):
    c, _ = env
    monkeypatch.setattr(db, "_append", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        db.create_run(c, ISSUE, "sha")
    assert c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_all_gates_pass_awaits_approval(env):
    c, g = env; calls = []; passing(calls)
    v = db.create_run(c, ISSUE, "sha"); drain(c, g)
    r = db.get_run(c, v.run_id)
    assert (r.status.value, r.outcome.value) == ("awaiting_approval", "VERIFIED_FIX")
    types = [e.type for e in db.events_after(c, v.run_id, 0)]
    assert types[0] == "run.queued" and types[-1] == "analysis.finished"


def test_unbuilt_steps_never_fake_a_pass(env):
    c, g = env
    v = db.create_run(c, ISSUE, "sha"); drain(c, g)
    r = db.get_run(c, v.run_id)
    assert r.outcome.value != "VERIFIED_FIX" and all(s.status == C.NOT_RUN for s in r.steps.values())


def test_stop_before_lease(env):
    c, g = env; passing([])
    v = db.create_run(c, ISSUE, "sha"); db.request_stop(c, v.run_id); drain(c, g)
    r = db.get_run(c, v.run_id)
    assert r.outcome.value == "STOPPED" and "run_stopped" in [b.value for b in r.publish_blockers]


def test_g3_failure_ends_early_as_cannot_reproduce(env):
    c, g = env; calls = []; passing(calls)
    nodes.register(S.REPRODUCE, lambda ctx: GateResult(gate="G3", status=C.FAILED, reason="import_error"))
    v = db.create_run(c, ISSUE, "sha"); drain(c, g)
    assert db.get_run(c, v.run_id).outcome.value == "CANNOT_REPRODUCE" and S.FIX not in calls


def expire(c):
    with db.tx(c):
        c.execute("UPDATE jobs SET lease_expires_at=?", ((db.now() - timedelta(seconds=1)).isoformat(),))


def test_crash_resumes_from_last_finished_step(env):
    c, g = env; calls = []; passing(calls)
    crashed = []
    def flaky_diag(ctx):
        if not crashed:
            crashed.append(1); raise RuntimeError("worker died")
        calls.append(S.DIAGNOSE)
    nodes.register(S.DIAGNOSE, flaky_diag)
    v = db.create_run(c, ISSUE, "sha")
    with pytest.raises(RuntimeError):
        W.run_job(g, W.lease_job(c))
    expire(c); drain(c, g)
    r = db.get_run(c, v.run_id)
    assert calls.count(S.SETUP) == 1 and calls.count(S.DIAGNOSE) == 1 and r.outcome.value == "VERIFIED_FIX"
    types = [e.type for e in db.events_after(c, v.run_id, 0)]
    assert "run.interrupted" in types and "run.resumed" in types


def test_two_failed_resumes_end_with_honest_outcome(env):
    c, g = env; passing([])
    def always(ctx): raise RuntimeError("broken step")
    nodes.register(S.DIAGNOSE, always)
    v = db.create_run(c, ISSUE, "sha")
    for _ in range(3):
        with pytest.raises(RuntimeError):
            W.run_job(g, W.lease_job(c))
        expire(c)
    drain(c, g)
    r = db.get_run(c, v.run_id)
    assert r.end_reason.value == "system_error" and r.outcome.value == "TRIAGE_ONLY"   # G3 had passed: best honest outcome
