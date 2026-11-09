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
    assert {"not_approved", "no_maintainer_consent"} <= {b.value for b in r.publish_blockers}   # contracts v0.5 §2.2
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


def test_revise_resumes_at_fix_only(env):
    c, g = env; calls = []; passing(calls)
    v = db.create_run(c, ISSUE, "sha"); drain(c, g)
    assert db.get_run(c, v.run_id).status.value == "awaiting_approval"
    calls.clear()
    r = db.get_run(c, v.run_id); r.revision = 1; r.status = r.status.__class__("revising"); db.save_run(c, r)
    with db.tx(c):
        c.execute("INSERT INTO jobs(run_id,kind,state,available_at) VALUES(?,?,?,?)", (v.run_id, "revise", "queued", db.now().isoformat()))
    drain(c, g)
    assert calls == [S.FIX, S.VERIFY, S.REVIEW]
    assert db.get_run(c, v.run_id).status.value == "awaiting_approval"


def ask(r, target):
    from backend.contracts.models import RevisionSummary
    r.revisions.append(RevisionSummary(revision=r.revision, outcome=r.outcome, end_reason=r.end_reason,
                                       revise_target=target, feedback="the test checks the wrong thing"))
    r.revision += 1; r.status = r.status.__class__("revising")


def test_revise_the_test_reruns_reproduce_and_drops_the_old_test(env):
    # smart_open-833: the test asserted an unrelated zstd read-back, and Revise could only retry the fix against it
    from backend.contracts.models import ReproTest
    c, g = env; calls = []; passing(calls)
    v = db.create_run(c, ISSUE, "sha"); drain(c, g)
    calls.clear()
    r = db.get_run(c, v.run_id)
    r.repro = ReproTest(test_diff_id="sha256:" + "a" * 64, test_ids=["tests/t.py::old"], expected_failure="x",
                        runs_on_base=[C.FAILED, C.FAILED], evidence_ids=[])
    ask(r, "test"); db.save_run(c, r)
    with db.tx(c):
        c.execute("INSERT INTO jobs(run_id,kind,state,available_at) VALUES(?,?,?,?)", (v.run_id, "revise", "queued", db.now().isoformat()))
    drain(c, g)
    assert calls == [S.REPRODUCE, S.DIAGNOSE, S.FIX, S.VERIFY, S.REVIEW]
    assert db.get_run(c, v.run_id).repro is None   # the stub step writes no test, so the old one must not survive


@pytest.mark.parametrize("target,step,gate,outcome", [("test", S.REPRODUCE, "G3", "CANNOT_REPRODUCE"),
                                                      ("fix", S.FIX, "G4", "TRIAGE_ONLY")])
def test_a_failed_revision_never_inherits_the_old_passing_gates(env, target, step, gate, outcome):
    # the old revision's G5=passed stayed in run.gates, so a revision that failed earlier would still claim a fix
    c, g = env; calls = []; passing(calls)
    v = db.create_run(c, ISSUE, "sha"); drain(c, g)
    nodes.register(step, lambda ctx: GateResult(gate=gate, status=C.FAILED, reason="no"))
    r = db.get_run(c, v.run_id); ask(r, target); db.save_run(c, r)
    with db.tx(c):
        c.execute("INSERT INTO jobs(run_id,kind,state,available_at) VALUES(?,?,?,?)", (v.run_id, "revise", "queued", db.now().isoformat()))
    drain(c, g)
    r = db.get_run(c, v.run_id)
    assert r.outcome.value == outcome and r.gates["G5"] == C.NOT_RUN and r.status.value == "finished"
    assert r.patch is None and r.verify is None and r.review is None   # nothing from the old revision speaks for this one
    assert S.VERIFY not in r.steps and S.REVIEW not in r.steps          # their old "passed" rows are gone, never shown


def test_a_crash_during_revise_setup_resumes_the_revision_not_the_whole_run(env):
    c, g = env; calls = []; passing(calls)
    v = db.create_run(c, ISSUE, "sha"); drain(c, g)
    r = db.get_run(c, v.run_id); ask(r, "test"); db.save_run(c, r)
    with db.tx(c):   # a leased revise job whose worker died before the graph was moved
        c.execute("INSERT INTO jobs(run_id,kind,state,available_at,lease_expires_at,attempt) VALUES(?,?,?,?,?,1)",
                  (v.run_id, "revise", "running", db.now().isoformat(), (db.now() - timedelta(seconds=1)).isoformat()))
    calls.clear(); drain(c, g)
    assert calls == [S.REPRODUCE, S.DIAGNOSE, S.FIX, S.VERIFY, S.REVIEW]


def test_reap_removes_sandboxes_whose_run_has_no_live_lease(env, monkeypatch):
    # a worker restart mid-step left agent containers running for an hour (runs 8, 9), eating the host's memory
    from backend.sandbox import docker
    c, _ = env
    live = db.create_run(c, IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t"), "sha")
    dead = db.create_run(c, IssueSpec(html_url="https://github.com/o/r/issues/2", repo="o/r", number=2, title="t"), "sha")
    W.lease_job(c)                                                          # leases live's job (lowest id)
    names = [f"pp-{live.run_id[:8]}-td-1-aaaa", f"pp-{dead.run_id[:8]}-td-1-bbbb", "pp-proxpi"]
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: docker.Result(0, "\n".join(names)))
    removed = []
    monkeypatch.setattr(docker, "rm", lambda *n: removed.extend(n))
    monkeypatch.setattr(docker, "rm_image", lambda *a: None)
    monkeypatch.setattr(docker, "rm_volume", lambda *a: None)
    W.reap(c)
    assert removed == [f"pp-{dead.run_id[:8]}-td-1-bbbb"]
