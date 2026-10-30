import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.api import main
from backend.contracts.models import CheckStatus, IssueSpec, RepoPolicy
from backend.github.reader import IssueCheck

URL = "https://github.com/o/r/issues/1"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    chk = IssueCheck(issue=IssueSpec(html_url=URL, repo="o/r", number=1, title="t", checks={"open": CheckStatus.PASSED}),
                     base_sha="abc", default_branch="main", language="Python", policy=RepoPolicy(), fetched_at=db.now())
    monkeypatch.setattr(main, "check_issue", lambda url: chk)


def browser():
    return TestClient(main.app, base_url="https://testserver")   # Secure cookie needs https


def test_runs_are_private_to_their_browser():
    a, b = browser(), browser()
    rid = a.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    assert a.get(f"/api/runs/{rid}").status_code == 200
    for path in (f"/api/runs/{rid}", f"/api/runs/{rid}/events"):
        r = b.get(path)
        assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    assert b.post(f"/api/runs/{rid}/stop").status_code == 404
    assert b.get("/api/me/runs").json() == [] and len(a.get("/api/me/runs").json()) == 1
    assert TestClient(main.app).get(f"/api/runs/{rid}").status_code == 404   # no cookie at all


def test_cookie_flags_and_token_never_stored():
    a = browser()
    r = a.post("/api/runs", json={"issue_url": URL})
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "secure" in sc and "samesite=lax" in sc
    tok = a.cookies.get("pp_sid")
    assert tok and not db.connect().execute("SELECT 1 FROM sessions WHERE id_hash=?", (tok,)).fetchone()


def test_limits_active_then_daily():
    a = browser()
    rid = a.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    r = a.post("/api/runs", json={"issue_url": URL})
    assert r.status_code == 429 and r.json()["code"] == "LIMIT_ACTIVE_RUN"
    a.post(f"/api/runs/{rid}/stop")                                   # queued → finished
    assert a.post("/api/runs", json={"issue_url": URL}).status_code == 201
    c = db.connect()
    with db.tx(c):
        c.execute("UPDATE runs SET status='finished'")
    r = a.post("/api/runs", json={"issue_url": URL})
    assert r.status_code == 429 and r.json()["code"] == "LIMIT_SESSION_DAILY"


def test_forget_run():
    a = browser()
    rid = a.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    assert a.delete(f"/api/runs/{rid}/access").status_code == 204
    assert a.get(f"/api/runs/{rid}").status_code == 404 and a.get("/api/me/runs").json() == []


def test_artifacts_are_owner_checked(tmp_path, monkeypatch):
    from backend import artifacts
    monkeypatch.setattr(artifacts, "STORE", tmp_path / "artifacts")
    a, b = browser(), browser()
    rid = a.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    ev, loose = artifacts.put("FAILED tests/x.py::t"), artifacts.put("not referenced by any run")
    db.emit(db.connect(), rid, "attempt.retry", "fix", evidence_ids=[ev])
    r = a.get(f"/api/artifacts/{ev}")
    assert r.status_code == 200 and "FAILED" in r.text and r.headers["x-content-type-options"] == "nosniff"
    assert a.get(f"/api/artifacts/{ev}?download=true").headers["content-disposition"].startswith("attachment")
    for client, eid in ((b, ev), (a, loose), (a, "sha256:" + "0" * 64), (a, "sha256:not-hex"), (a, "..%2F..%2Fetc%2Fpasswd")):
        assert client.get(f"/api/artifacts/{eid}").status_code == 404     # not yours / unreferenced / missing / bad id

def test_new_run_records_g0_and_its_gate_event():   # run 11 report said "Issue eligibility: not run"
    a = browser()
    rid = a.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    assert a.get(f"/api/runs/{rid}").json()["gates"]["G0"] == "passed"
    ev = [e for e in a.get(f"/api/runs/{rid}/events").json()["events"] if e["type"] == "gate.result"]
    assert [(e["step"], e["payload"]["gate"], e["payload"]["status"]) for e in ev] == [("intake", "G0", "passed")]
