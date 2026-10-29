import pytest
from fastapi.testclient import TestClient

from backend import artifacts, db
from backend.api import approval, main
from backend.contracts.models import (CheckStatus, IssueSpec, Outcome, Patch, PublishBlocker, RepoPolicy, RunStatus,
                                      SGReport)
from backend.github.reader import IssueCheck

URL = "https://github.com/o/r/issues/1"
FIX = "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
TEST = "diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -0,0 +1 @@\n+def test(): pass\n"
OK = {"read_diff": True, "understands_change": True, "ai_note_ok": True}


@pytest.fixture
def ready(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    chk = IssueCheck(issue=IssueSpec(html_url=URL, repo="o/r", number=1, title="t"), base_sha="abc", default_branch="main",
                     language="Python", policy=RepoPolicy(), fetched_at=db.now())
    monkeypatch.setattr(main, "check_issue", lambda url: chk)
    stale = []
    monkeypatch.setattr(approval, "stale_checks", lambda v, d: list(stale))
    b = TestClient(main.app, base_url="https://testserver")
    rid = b.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    c = db.connect(); v = db.get_run(c, rid)
    v.status, v.outcome = RunStatus.AWAITING_APPROVAL, Outcome.VERIFIED_FIX
    v.gates = {"G5": CheckStatus.PASSED}; v.publish_blockers = [PublishBlocker.NOT_APPROVED]
    v.patch = Patch(fix_diff_id=artifacts.put(FIX), test_diff_id=artifacts.put(TEST), attempt=1, policy_result=CheckStatus.PASSED)
    v.supplyguard = SGReport(report_id="sha256:" + "1" * 64, status=CheckStatus.PASSED)
    db.save_run(c, v)
    return b, rid, stale


def body(ctx, **kw):
    return {"revision": ctx["revision"], "diff_hash": ctx["diff_hash"], "evidence_hash": ctx["evidence_hash"],
            "checklist": OK, "explanation": "it raises now", "pr_title": "t", "pr_summary": "s", **kw}


def test_approve_records_exact_hashes(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    assert ctx["files"] == ["src/a.py", "tests/test_a.py"]
    r = b.post(f"/api/runs/{rid}/approve", json=body(ctx))
    assert r.status_code == 200
    v = r.json()
    assert v["approval"]["diff_hash"] == ctx["diff_hash"] and v["approval"]["explanation"] == "it raises now"
    assert "not_approved" not in v["publish_blockers"]


def test_checklist_required(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    r = b.post(f"/api/runs/{rid}/approve", json=body(ctx, checklist={**OK, "ai_note_ok": False}))
    assert r.status_code == 422 and r.json()["code"] == "CHECKLIST_INCOMPLETE"


def test_stale_hash_refused(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    r = b.post(f"/api/runs/{rid}/approve", json=body(ctx, diff_hash="sha256:" + "0" * 64))
    assert r.status_code == 409 and r.json()["code"] == "APPROVAL_STALE"


def test_upstream_change_is_permanent(ready):
    b, rid, stale = ready
    stale.append(PublishBlocker.UPSTREAM_CHANGED)
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    r = b.post(f"/api/runs/{rid}/approve", json=body(ctx))
    assert r.status_code == 409 and r.json()["code"] == "UPSTREAM_CHANGED"
    assert b.get(f"/api/runs/{rid}").json()["status"] == "finished"


def test_recheck_deps_voids_approval(ready, monkeypatch):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    b.post(f"/api/runs/{rid}/approve", json=body(ctx))
    from backend.sandbox import steps
    monkeypatch.setattr(steps, "run_supplyguard", lambda r: SGReport(report_id="sha256:" + "2" * 64, status=CheckStatus.PASSED))
    v = b.post(f"/api/runs/{rid}/recheck-deps").json()
    assert v["approval"] is None and "not_approved" in v["publish_blockers"]
    assert b.get(f"/api/runs/{rid}/approval").json()["evidence_hash"] != ctx["evidence_hash"]


def test_revise_voids_and_queues(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    b.post(f"/api/runs/{rid}/approve", json=body(ctx))
    v = b.post(f"/api/runs/{rid}/revise", json={"feedback": "keep the public name"}).json()
    assert v["revision"] == 1 and v["status"] == "revising" and v["approval"] is None and len(v["revisions"]) == 1
    assert db.connect().execute("SELECT COUNT(*) FROM jobs WHERE kind='revise' AND state='queued'").fetchone()[0] == 1


def test_other_browser_cannot_approve(ready):
    b, rid, _ = ready
    ctx = b.get(f"/api/runs/{rid}/approval").json()
    other = TestClient(main.app, base_url="https://testserver")
    assert other.post(f"/api/runs/{rid}/approve", json=body(ctx)).status_code == 404
