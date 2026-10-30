from fastapi.testclient import TestClient

from backend.api.main import app

c = TestClient(app)


def test_healthz_never_claims_unknown_parts_are_ok(tmp_path, monkeypatch):
    from backend import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))   # no worker has ever run here
    from backend.api import main as m
    monkeypatch.setattr(m, "llm_budget_set", lambda: False)        # independent of the live config
    h = c.get("/healthz").json()
    assert h["worker"] is False and h["llm_budget"] == "unset"


def test_run_and_events_after():
    assert c.get("/api/runs/verified_fix").json()["outcome"] == "VERIFIED_FIX"
    all_ev = c.get("/api/runs/verified_fix/events").json()
    later = c.get(f"/api/runs/verified_fix/events?after={all_ev['events'][2]['seq']}").json()
    assert [e["seq"] for e in later["events"]] == [e["seq"] for e in all_ev["events"][3:]]
    assert later["next_after"] == all_ev["next_after"]


def test_unknown_run_is_404_with_error_shape():
    r = c.get("/api/runs/..%2F..%2Fetc")
    assert r.status_code == 404
    r = c.get("/api/runs/nope")
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    assert r.headers["X-Robots-Tag"] == "noindex"
