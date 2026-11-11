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
    assert "Not re-checked" in "\n".join(existing_work_section("missing-run"))   # G0 did check at the start


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


def test_unreadable_comments_at_the_start_are_not_comparable_and_logins_ignore_case():
    # A's review of #77: comments unreadable at the start must not turn last year's claims into "new" ones
    out = A.new_existing_work(W(claimants=None), W(claimants=["bob"]), me="alice", started_at=T0, claims_known_at_start=True)
    assert out and "can't tell" in out[0] and "since the run started" not in out[0]
    assert A.new_existing_work(W(claimants=["Bob"]), W(claimants=["bob"]), me="alice", started_at=T0, claims_known_at_start=True) == []


def test_a_merged_pr_counts_only_when_it_really_references_the_issue(monkeypatch):
    # A's review of #77: "Refactor divide zero tests" shares two title words with the issue but doesn't mention it
    import backend.github.reader as R
    canned = {"/repos/o/r/issues/1": {"state": "open", "title": "divide by zero returns None", "body": "b", "assignees": [], "labels": [], "comments": 0},
              "/repos/o/r": {"language": "Python", "default_branch": "main"},
              "/repos/o/r/pulls?state=closed&sort=updated&direction=desc&per_page=50": [
                  {"number": 7, "title": "Refactor divide zero tests", "body": "", "merged_at": "2026-11-09T07:00:00Z"},
                  {"number": 8, "title": "Raise on zero", "body": "Closes #1", "merged_at": "2026-11-09T07:00:00Z"}]}
    monkeypatch.setattr(R, "_get", lambda h, path, required=True: canned.get(path))
    monkeypatch.setattr("backend.github.assess.extract", lambda **k: None)
    assert [p["number"] for p in R.check_issue("https://github.com/o/r/issues/1").existing_work["closed_prs"]] == [8]


def _run_with_owner(tmp_path, monkeypatch, start):
    from backend.contracts.models import CheckStatus, IssueSpec, RepoPolicy
    from backend.github.reader import IssueCheck
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    c = db.connect()
    c.execute("INSERT INTO accounts(id, github_id, login, created_at) VALUES(7, 77, 'alice', '2026-11-09')")
    v = db.create_run(c, IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t",
                                   checks={"unassigned": CheckStatus.PASSED}), "sha", owner_account_id=7)
    db.put_kv(c, f"existing_work:{v.run_id}", json.dumps(start))
    monkeypatch.setattr(A.reader, "_get", lambda h, path, required=True: {"files": []})
    mk = lambda now: IssueCheck(issue=v.issue, base_sha="sha", default_branch="main", language="Python", policy=RepoPolicy(),
                                fetched_at=db.now(), existing_work=now)
    return v, mk


def test_the_users_own_claim_never_blocks_approve_before_they_publish(tmp_path, monkeypatch):
    # A's review of #77: at approve there's no publish_account yet, so "me" must come from the run's signed-in owner
    v, mk = _run_with_owner(tmp_path, monkeypatch, W())
    monkeypatch.setattr(A.reader, "check_issue", lambda url, extract_model=True: mk(W(claimants=["Alice"])))
    assert A.stale_checks(v, "") == []


def test_a_change_accepted_at_approve_is_not_blocked_again_at_publish(tmp_path, monkeypatch):
    # A's review of #77: the publisher compared against the start snapshot again, so an accepted change could never publish
    v, mk = _run_with_owner(tmp_path, monkeypatch, W())
    monkeypatch.setattr(A.reader, "check_issue", lambda url, extract_model=True: mk(W(claimants=["bob"])))
    assert A.stale_checks(v, "") == [A.PublishBlocker.ISSUE_CHANGED]
    A.accept_issue_change(v.run_id)
    assert A.stale_checks(v, "") == []
    monkeypatch.setattr(A.reader, "check_issue", lambda url, extract_model=True: mk(W(claimants=["bob", "carol"])))
    assert A.stale_checks(v, "") == [A.PublishBlocker.ISSUE_CHANGED]   # something newer than what was accepted still blocks


def test_a_blocked_approval_names_only_what_blocks_in_words():
    msg = A.blocked_message([A.PublishBlocker.NOT_APPROVED, A.PublishBlocker.NO_MAINTAINER_CONSENT, A.PublishBlocker.ISSUE_CHANGED])
    assert "not_approved" not in msg and "no_maintainer_consent" not in msg and "issue_changed" not in msg
    assert "pull request" in msg and "Approve anyway" in msg
