"""SQLite store (architecture §5): runs, jobs, events. WAL; short transactions; API + worker share it."""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.config import ROOT
from backend.contracts.models import Event, IssueSpec, RunStatus, RunView

DB_PATH = os.getenv("PP_DB", str(ROOT / "data" / "app.db"))
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, owner_session_hash TEXT, owner_account_id INTEGER,
  status TEXT NOT NULL, stop_requested INTEGER NOT NULL DEFAULT 0, state_json TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs, kind TEXT NOT NULL,
  state TEXT NOT NULL, lease_owner TEXT, lease_expires_at TEXT, heartbeat_at TEXT, attempt INTEGER NOT NULL DEFAULT 0,
  available_at TEXT NOT NULL, error_category TEXT);
CREATE TABLE IF NOT EXISTS events(run_id TEXT NOT NULL, seq INTEGER NOT NULL, ts TEXT NOT NULL, type TEXT NOT NULL,
  step TEXT, revision INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL, PRIMARY KEY(run_id, seq));
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id_hash TEXT PRIMARY KEY, ip_hash TEXT, created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL, revoked_at TEXT);
"""


def now() -> datetime:
    return datetime.now(timezone.utc)


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)   # autocommit; explicit BEGIN for transactions
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=5000"); c.execute("PRAGMA foreign_keys=ON")
    c.executescript(SCHEMA)
    return c


@contextmanager
def tx(c: sqlite3.Connection):
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK"); raise


def _append(c, run_id: str, type_: str, step: str | None = None, revision: int = 0, **payload) -> Event:
    seq = c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
    ev = Event(run_id=run_id, seq=seq, ts=now(), type=type_, step=step, revision=revision, payload=payload)
    c.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",
              (run_id, seq, ev.ts.isoformat(), type_, step, revision, json.dumps(payload)))
    return ev


def emit(c, run_id: str, type_: str, step: str | None = None, revision: int = 0, **payload) -> Event:
    with tx(c):
        return _append(c, run_id, type_, step, revision, **payload)


def create_run(c, issue: IssueSpec, base_sha: str, owner_session_hash: str | None = None,
               owner_account_id: int | None = None) -> RunView:
    """Run + job + run.queued in ONE transaction: the worker can't see the job before the run is committed."""
    t = now()
    v = RunView(run_id=str(uuid.uuid4()), status=RunStatus.QUEUED, issue=issue, base_sha=base_sha, created_at=t, updated_at=t)
    with tx(c):
        c.execute("INSERT INTO runs VALUES(?,?,?,?,0,?,?,?)", (v.run_id, owner_session_hash, owner_account_id,
                  v.status.value, v.model_dump_json(), t.isoformat(), t.isoformat()))
        c.execute("INSERT INTO jobs(run_id,kind,state,available_at) VALUES(?,?,?,?)", (v.run_id, "analyze", "queued", t.isoformat()))
        _append(c, v.run_id, "run.queued", position=c.execute("SELECT COUNT(*) FROM jobs WHERE state='queued'").fetchone()[0])
    return v


def get_run(c, run_id: str) -> RunView | None:
    r = c.execute("SELECT state_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
    return RunView.model_validate_json(r[0]) if r else None


def save_run(c, v: RunView) -> None:
    v.updated_at = now()
    with tx(c):
        c.execute("UPDATE runs SET status=?, state_json=?, updated_at=? WHERE run_id=?",
                  (v.status.value, v.model_dump_json(), v.updated_at.isoformat(), v.run_id))


def events_after(c, run_id: str, after: int) -> list[Event]:
    rows = c.execute("SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after)).fetchall()
    return [Event(run_id=r["run_id"], seq=r["seq"], ts=r["ts"], type=r["type"], step=r["step"],
                  revision=r["revision"], payload=json.loads(r["payload"])) for r in rows]


def request_stop(c, run_id: str) -> bool:
    with tx(c):
        return c.execute("UPDATE runs SET stop_requested=1 WHERE run_id=? AND status NOT IN ('finished','published')",
                         (run_id,)).rowcount == 1


def stop_requested(c, run_id: str) -> bool:
    return bool(c.execute("SELECT stop_requested FROM runs WHERE run_id=?", (run_id,)).fetchone()[0])


def put_kv(c, key: str, value: str) -> None:
    c.execute("INSERT INTO kv VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def get_kv(c, key: str) -> str | None:
    r = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


ACTIVE = ("queued", "running", "paused", "interrupted", "revising", "publishing")


def owns(c, run_id: str, session_hash: str | None, account_id: int | None = None) -> bool:
    r = c.execute("SELECT owner_session_hash, owner_account_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
    return bool(r) and ((session_hash is not None and r[0] == session_hash) or (account_id is not None and r[1] == account_id))


def owner_counts(c, session_hash: str | None, account_id: int | None) -> tuple[int, int]:
    """(runs started today UTC, runs still active) for this owner."""
    day = now().date().isoformat()
    w, args = ("owner_account_id=?", (account_id,)) if account_id is not None else ("owner_session_hash=?", (session_hash,))
    today = c.execute(f"SELECT COUNT(*) FROM runs WHERE {w} AND substr(created_at,1,10)=?", (*args, day)).fetchone()[0]
    active = c.execute(f"SELECT COUNT(*) FROM runs WHERE {w} AND status IN ({','.join('?' * len(ACTIVE))})",
                       (*args, *ACTIVE)).fetchone()[0]
    return today, active


def list_runs(c, session_hash: str | None, account_id: int | None) -> list[RunView]:
    rows = c.execute("SELECT state_json FROM runs WHERE (owner_session_hash=? AND ? IS NOT NULL) OR "
                     "(owner_account_id=? AND ? IS NOT NULL) ORDER BY created_at DESC LIMIT 100",
                     (session_hash, session_hash, account_id, account_id)).fetchall()
    return [RunView.model_validate_json(r[0]) for r in rows]


def forget(c, run_id: str, session_hash: str) -> bool:
    with tx(c):
        return c.execute("UPDATE runs SET owner_session_hash=NULL WHERE run_id=? AND owner_session_hash=?",
                         (run_id, session_hash)).rowcount == 1
