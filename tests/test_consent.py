"""Maintainer consent (contracts v0.5 §2.2, #70). Silence, an open issue or no PR is never consent; code decides."""
import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.github import consent as K

ASK = "https://github.com/o/r/issues/1#issuecomment-100"
ISSUE = {"state": "open", "html_url": "https://github.com/o/r/issues/1", "labels": [], "comments": 1}


def cm(i, body, assoc="OWNER", login="maint"):
    return {"id": i, "html_url": f"https://github.com/o/r/issues/1#issuecomment-{i}", "body": body,
            "author_association": assoc, "user": {"login": login}}


@pytest.mark.parametrize("body", ["Yes please, go ahead!", "Sure, a PR would be welcome.", "PRs welcome :)",
                                  "We'd happily review a PR. Feel free.", "Please send a PR"])
def test_positive_maintainer_reply_after_the_ask_is_consent(body):
    r = K.read(ISSUE, [cm(101, body)], asked_url=ASK, me="alice")
    assert r["state"] == "granted" and r["evidence"].kind == "maintainer_reply" and r["evidence"].author_association == "OWNER"


@pytest.mark.parametrize("comments, state", [
    ([], "waiting"),                                                           # silence is never consent
    ([cm(101, "Yes please", assoc="NONE", login="bob")], "waiting"),            # not a maintainer
    ([cm(101, "Yes please", assoc="CONTRIBUTOR", login="bob")], "waiting"),
    ([cm(101, "Yes please", login="alice")], "waiting"),                       # the user's own words (they may be a member)
    ([cm(101, "Thanks, I'll have a look at the diff later.")], "replied"),      # unclear: the user may attest it
    ([cm(101, "No thanks, we won't fix this.")], "declined"),
    ([cm(101, "Sure!"), cm(102, "Actually, please don't: I'll fix it myself.")], "declined"),   # the latest word wins
    ([cm(99, "Yes, I can reproduce this.")], "waiting"),                       # before the ask and not about a PR
])
def test_what_is_not_consent(comments, state):
    assert K.read(ISSUE, comments, asked_url=ASK, me="alice")["state"] == state


def test_maintainer_request_before_any_ask_and_quoted_text_does_not_count():
    r = K.read(ISSUE, [cm(50, "A pull request fixing this would be welcome.")], asked_url=None, me="alice")
    assert r["state"] == "granted" and r["evidence"].kind == "maintainer_request"
    assert K.read(ISSUE, [cm(50, "> PRs welcome\nWho said that?")], asked_url=None, me="alice")["state"] == "none"


def test_labels_contributing_and_not_planned():
    lab = {**ISSUE, "labels": [{"name": "help wanted"}]}
    assert K.read(lab, [], asked_url=None, me=None)["evidence"].quote == "label: help wanted"
    ok = ("https://github.com/o/r/blob/main/CONTRIBUTING.md", "Bug fixes are very welcome. Run the tests first.")
    assert K.read(ISSUE, [], asked_url=None, me=None, contributing=ok)["evidence"].kind == "contributing_invites"
    first = (ok[0], "Pull requests are welcome, but please open an issue first to discuss the change.")
    assert K.read(ISSUE, [], asked_url=None, me=None, contributing=first)["state"] == "none"
    closed = {**ISSUE, "state": "closed", "state_reason": "not_planned", "labels": [{"name": "help wanted"}]}
    assert K.read(closed, [], asked_url=ASK, me=None)["state"] == "declined"


@pytest.fixture
def api(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from backend.api import main
    from backend.contracts.models import (Approval, IssueSpec, Owner, PublishBlocker, RepoPolicy, RunStatus)
    from backend.github.reader import IssueCheck
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    url = "https://github.com/o/r/issues/1"
    chk = IssueCheck(issue=IssueSpec(html_url=url, repo="o/r", number=1, title="t"), base_sha="abc", default_branch="main",
                     language="Python", policy=RepoPolicy(), fetched_at=db.now())
    monkeypatch.setattr(main, "check_issue", lambda u: chk)
    b = TestClient(main.app, base_url="https://testserver")
    rid = b.post("/api/runs", json={"issue_url": url}).json()["run_id"]
    c = db.connect(); v = db.get_run(c, rid)
    v.status = RunStatus.AWAITING_APPROVAL
    v.publish_blockers = [PublishBlocker.NO_MAINTAINER_CONSENT]
    v.approval = Approval(run_id=rid, revision=0, diff_hash="sha256:" + "1" * 64, evidence_hash="sha256:" + "2" * 64,
                          approved_by=Owner(session_id_hash="s"), approved_at=db.now(), checklist={}, pr_title="t", pr_summary="s")
    db.save_run(c, v)
    db.put_kv(c, f"ask:{rid}", '{"url": "%s"}' % ASK)
    return b, rid, monkeypatch


def test_api_records_consent_attestation_and_override(api):
    b, rid, mp = api
    replies = [cm(101, "Hmm, let me look at the diff first.")]
    mp.setattr(K, "check", lambda repo, n, asked_url, me: K.read(ISSUE, replies, asked_url=asked_url, me=me))
    st = b.get(f"/api/runs/{rid}/consent").json()
    assert st["state"] == "replied" and st["consent"] is None and len(st["replies"]) == 1
    assert b.post(f"/api/runs/{rid}/consent", json={}).json()["consent"] is None             # an unclear reply isn't recorded alone
    bad = b.post(f"/api/runs/{rid}/consent", json={"attest_comment_url": "https://github.com/o/r/issues/1#issuecomment-5"})
    assert bad.status_code == 409 and bad.json()["code"] == "NOT_CONSENT"
    out = b.post(f"/api/runs/{rid}/consent", json={"attest_comment_url": replies[0]["html_url"]}).json()
    assert out["consent"]["kind"] == "maintainer_reply" and out["consent"]["attested_by_user"] is True
    v = db.get_run(db.connect(), rid)
    assert "no_maintainer_consent" not in [x.value for x in v.publish_blockers]


def test_api_override_needs_a_real_reason_and_github_errors_record_nothing(api):
    from backend.github.reader import GitHubError
    b, rid, mp = api
    assert b.post(f"/api/runs/{rid}/consent", json={"override_reason": "because"}).status_code == 422
    def down(*a, **k):
        raise GitHubError("GITHUB_UNAVAILABLE", "GitHub didn't answer.")
    mp.setattr(K, "check", down)
    assert b.post(f"/api/runs/{rid}/consent", json={}).status_code == 503 and db.get_run(db.connect(), rid).consent is None
    out = b.post(f"/api/runs/{rid}/consent", json={"override_reason": "The maintainer asked me to send it in the project chat."}).json()
    assert out["consent"]["kind"] == "user_override"
    from backend.report import render
    assert "Override by the user" in render(db.get_run(db.connect(), rid))


def test_attest_is_refused_after_a_later_decline_and_blank_override_is_refused(api):
    b, rid, mp = api
    replies = [cm(101, "Hmm, let me look at the diff first."), cm(102, "No thanks, we won't fix this.")]
    mp.setattr(K, "check", lambda repo, n, asked_url, me: K.read(ISSUE, replies, asked_url=asked_url, me=me))
    r = b.post(f"/api/runs/{rid}/consent", json={"attest_comment_url": replies[0]["html_url"]})
    assert r.status_code == 409 and r.json()["code"] == "NOT_CONSENT"
    assert b.post(f"/api/runs/{rid}/consent", json={"override_reason": " " * 25}).status_code == 422
    assert db.get_run(db.connect(), rid).consent is None


def test_a_maintainers_earlier_no_beats_an_invite_label():
    # found while fixing #85: a "won't fix" before our ask plus "help wanted" was read as consent granted
    from backend.github import consent as K2
    issue = {"state": "open", "labels": [{"name": "help wanted"}], "html_url": "https://github.com/o/r/issues/1"}
    no = {"user": {"login": "own"}, "author_association": "OWNER", "body": "Won't fix, working as intended.", "id": 5}
    assert K2.read(issue, [no], asked_url=None, me=None)["state"] == "declined"
    later_yes = {**no, "body": "Changed my mind: PRs welcome.", "id": 9}
    assert K2.read(issue, [no, later_yes], asked_url=None, me=None)["state"] == "granted"   # the latest word wins
