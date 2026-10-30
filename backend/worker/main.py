"""Worker process: leases jobs from SQLite, runs the graph, heartbeats, resumes after a crash (contracts §7).
Run: uv run python -m backend.worker.main"""
import os
import re
import socket
import threading
import time
from datetime import timedelta

from backend import db
from backend.contracts.models import RunStatus
import backend.sandbox.steps  # noqa: F401  registers PREFLIGHT/SETUP/BASELINE
from backend.worker.graph import build

try:
    import backend.agents  # noqa: F401  role B registers REPRODUCE..REVIEW
except ImportError:
    pass

LEASE, BEAT, MAX_LEASES = 60, 10, 3      # 3 leases = first run + 2 resumes
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def lease_job(c):
    t = db.now()
    with db.tx(c):
        row = c.execute("""SELECT * FROM jobs WHERE kind IN ('analyze','revise','publish','resume') AND ((state='queued' AND available_at<=?)
                           OR (state='running' AND lease_expires_at<?)) ORDER BY id LIMIT 1""",
                        (t.isoformat(), t.isoformat())).fetchone()
        if not row:
            return None
        c.execute("UPDATE jobs SET state='running', lease_owner=?, lease_expires_at=?, heartbeat_at=?, attempt=attempt+1 WHERE id=?",
                  (WORKER_ID, (t + timedelta(seconds=LEASE)).isoformat(), t.isoformat(), row["id"]))
    return dict(row) | {"resumed": row["state"] == "running", "attempt": row["attempt"] + 1}


def heartbeat(job_id: int, stop: threading.Event):
    c = db.connect()
    while not stop.wait(BEAT):
        t = db.now()
        db.put_kv(c, "worker_heartbeat", t.isoformat())
        with db.tx(c):
            c.execute("UPDATE jobs SET heartbeat_at=?, lease_expires_at=? WHERE id=? AND lease_owner=?",
                      (t.isoformat(), (t + timedelta(seconds=LEASE)).isoformat(), job_id, WORKER_ID))


def run_job(graph, job: dict) -> None:
    if job["kind"] == "publish":
        from backend.publisher.job import run_publish
        return run_publish(job)
    c, rid = db.connect(), job["run_id"]
    cfg = {"configurable": {"thread_id": rid}}
    run = db.get_run(c, rid)
    if job["kind"] == "resume":   # B15: Continue after a guided pause (the graph resumes at the paused node)
        db.emit(c, rid, "run.resumed", None, run.revision, from_step=(graph.get_state(cfg).next or ["?"])[0])
        run.status, run.pause = RunStatus.RUNNING, None; db.save_run(c, run)
        return _finish_job(c, job, graph, cfg)
    if job["kind"] == "revise" and not job["resumed"]:
        db.emit(c, rid, "run.resumed", None, run.revision, from_step="fix")
        graph.update_state(cfg, {"end_reason": None, "gates": {"G4": "not_run", "G5": "not_run", "G6": "not_run"}}, as_node="diagnose")
        return _finish_job(c, job, graph, cfg)
    if job["resumed"]:
        snap = graph.get_state(cfg)
        db.emit(c, rid, "run.interrupted", None, run.revision, last_completed_step=(snap.values or {}).get("last") or None)
        if job["attempt"] > MAX_LEASES:   # 2 failed resumes -> end honestly with the report so far
            graph.update_state(cfg, {"end_reason": "system_error"}, as_node="review")
            return _finish_job(c, job, graph, cfg)
        db.emit(c, rid, "run.resumed", None, run.revision, from_step=(snap.next or ["?"])[0])
    else:
        db.emit(c, rid, "run.started", None, run.revision, from_step="preflight")
    run = db.get_run(c, rid); run.status = RunStatus.RUNNING; db.save_run(c, run)
    _finish_job(c, job, graph, cfg)


def _finish_job(c, job, graph, cfg):
    stop = threading.Event()
    threading.Thread(target=heartbeat, args=(job["id"], stop), daemon=True).start()
    try:
        has_ckpt = bool(graph.get_state(cfg).next)
        graph.invoke(None if has_ckpt else {"run_id": job["run_id"], "gates": {}}, cfg)
        with db.tx(c):
            c.execute("UPDATE jobs SET state='succeeded', lease_owner=NULL WHERE id=?", (job["id"],))
    finally:
        stop.set()


def reap(c) -> None:
    """contracts §7/§9: drop per-run images + snapshot volumes 48 h after a run stops changing."""
    from backend.sandbox import docker
    from backend.sandbox.steps import image, snap
    cutoff = (db.now() - timedelta(hours=48)).isoformat()
    for (rid,) in c.execute("SELECT run_id FROM runs WHERE status IN ('finished','published','awaiting_approval') "
                            "AND updated_at < ? AND 'reaped:' || run_id NOT IN (SELECT key FROM kv)", (cutoff,)):
        docker.rm_image(image(rid)); docker.rm_volume(snap(rid))
        db.put_kv(c, f"reaped:{rid}", db.now().isoformat())
    # a sandbox outlives its step only if the worker died mid-step: keep containers of runs with a live lease, drop the rest
    live = {r[0][:8] for r in c.execute("SELECT run_id FROM jobs WHERE state='running' AND lease_expires_at>?", (db.now().isoformat(),))}
    names = docker._docker("ps", "-a", "--format", "{{.Names}}").out.split()
    docker.rm(*[n for n in names if (m := re.match(r"pp-([0-9a-f]{8})-", n)) and m[1] not in live])


def main():
    from backend.sandbox import docker
    ok, why = docker.runtime_ok()
    if not ok:
        raise SystemExit(f"refusing to start: sandbox runtime {why}")
    graph = build()
    print(f"worker {WORKER_ID} ready", flush=True)
    c = db.connect()
    last_reap = 0.0
    while True:
        if time.time() - last_reap > 600:
            reap(c); last_reap = time.time()
        db.put_kv(c, "worker_heartbeat", db.now().isoformat())
        job = lease_job(c)
        if job:
            try:
                run_job(graph, job)
            except Exception as e:   # leave the lease to expire: the next lease resumes from the checkpoint
                print(f"job {job['id']} failed: {e!r}", flush=True)
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
