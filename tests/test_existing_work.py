"""#70 item 4: re-check existing work at publish. New claims, assignees or merged PRs since the run started block
publishing (ISSUE_CHANGED); the user's own comments never do; an unreadable source is unknown, so it fails closed."""
import json

import pytest

from backend import db
from backend.api import approval as A

T0 = "2026-11-09T06:00:00+00:00"
W = lambda **k: {"checked_at": T0, "sources": {"timeline": "checked", "open_prs": "checked", "comments": "checked", "closed_prs": "checked"},
                 "linked_prs": [], "assignees": [], "claimants": [], "closed_prs": [], **k}


@pytest.mark.parametrize("start, now, me, known, blocked", [
    (W(), W(), "alice", True, False),                                                     # nothing changed
    (W(), W(claimants=["bob"]), "alice", True, True),                                     # bob claimed it meanwhile
    (W(), W(assignees=["carol"]), "alice", True, True),                                   # carol was assigned
    (W(), W(claimants=["Alice"]), "alice", True, False),                                  # the user's own "happy to send a PR"
    (W(claimants=["bob"]), W(claimants=["bob"]), "alice", True, False),                   # accepted at the start, not new
    (W(), W(claimants=None), "alice", True, True),                                        # comments unreadable: fail closed
    (W(), W(closed_prs=[{"number": 9, "merged_at": "2026-11-09T07:00:00Z", "closed_at": None}]), "alice", True, True),
    (W(), W(closed_prs=[{"number": 9, "merged_at": "2026-11-09T05:00:00Z", "closed_at": None}]), "alice", True, False),  # merged before
    (W(), W(closed_prs=[{"number": 9, "merged_at": None, "closed_at": "2026-11-09T07:00:00Z"}]), "alice", True, False),  # closed unmerged
    (None, W(claimants=["bob"]), "alice", False, False),   # old run without a snapshot that accepted a claim at the start
    (None, W(claimants=["bob"]), "alice", True, True),     # old run that started with no claim
])
def test_new_existing_work(start, now, me, known, blocked):
    assert bool(A.new_existing_work(start, now, me=me, started_at=T0, claims_known_at_start=known)) is blocked


def test_reader_records_sources_and_recent_closed_prs(monkeypatch):
    import backend.github.reader as R
    canned = {"/repos/o/r/issues/1": {"state": "open", "title": "divide by zero returns None", "body": "b", "assignees": [], "labels": [], "comments": 1},
              "/repos/o/r": {"language": "Python", "default_branch": "main"},
              "/repos/o/r/issues/1/comments?per_page=100": [{"body": "I'll take this", "user": {"login": "bob"}}],
              "/repos/o/r/pulls?state=closed&sort=updated&direction=desc&per_page=50": [
                  {"number": 5, "title": "Fix #1: raise on zero", "body": "", "merged_at": "2026-11-09T07:00:00Z", "closed_at": "2026-11-09T07:00:00Z"},
                  {"number": 6, "title": "Unrelated docs", "body": "", "merged_at": None, "closed_at": "2026-11-09T07:00:00Z"}]}
    monkeypatch.setattr(R, "_get", lambda h, path, required=True: canned.get(path))
    monkeypatch.setattr("backend.github.assess.extract", lambda **k: None)
    w = R.check_issue("https://github.com/o/r/issues/1").existing_work
    assert w["sources"] == {"timeline": "failed", "open_prs": "failed", "comments": "checked", "closed_prs": "checked"}
    assert w["claimants"] == ["bob"] and [p["number"] for p in w["closed_prs"]] == [5]


def test_publish_recheck_blocks_on_a_new_claim_and_the_report_says_where_we_looked(tmp_path, monkeypatch):
    from backend.contracts.models import CheckStatus, IssueSpec, Outcome, RunStatus, RunView
    from backend.github.reader import IssueCheck
    from backend.contracts.models import RepoPolicy
    from backend.report import existing_work_section
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t",
                                              checks={"unassigned": CheckStatus.PASSED}), "sha")
    db.put_kv(db.connect(), f"existing_work:{v.run_id}", json.dumps(W()))
    now = W(claimants=["bob"], checked_at="2026-11-09T09:00:00+00:00")
    chk = IssueCheck(issue=v.issue, base_sha="sha", default_branch="main", language="Python", policy=RepoPolicy(),
                     fetched_at=db.now(), existing_work=now)
    monkeypatch.setattr(A.reader, "check_issue", lambda url, extract_model=True: chk)
    monkeypatch.setattr(A.reader, "_get", lambda h, path, required=True: {"files": []})
    assert A.stale_checks(v, "") == [A.PublishBlocker.ISSUE_CHANGED]
    text = "\n".join(existing_work_section(v.run_id))
    assert "When the run started" in text and "Re-checked before publishing" in text and "bob claimed the issue" in text
    assert "issue comments (read)" in text
    assert "Not checked" in "\n".join(existing_work_section("missing-run"))


def test_creating_a_run_stores_the_start_snapshot(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api import main
    from backend.contracts.models import IssueSpec, RepoPolicy
    from backend.github.reader import IssueCheck
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    url = "https://github.com/o/r/issues/1"
    chk = IssueCheck(issue=IssueSpec(html_url=url, repo="o/r", number=1, title="t"), base_sha="abc", default_branch="main",
                     language="Python", policy=RepoPolicy(), fetched_at=db.now(), existing_work=W(linked_prs=[]))
    monkeypatch.setattr(main, "check_issue", lambda u: chk)
    rid = TestClient(main.app, base_url="https://testserver").post("/api/runs", json={"issue_url": url}).json()["run_id"]
    assert json.loads(db.get_kv(db.connect(), f"existing_work:{rid}"))["sources"]["comments"] == "checked"
