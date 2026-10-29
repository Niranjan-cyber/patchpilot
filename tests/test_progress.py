"""B16: My progress. Counts never conflate outcomes; GitHub PR status is fetched, never guessed."""
from datetime import datetime, timezone

import pytest

from backend.contracts.models import IssueSpec, Outcome, PullRequestRef, RunStatus, RunView
from backend.github import progress as P


def run(n, outcome=None, pr=None, status=RunStatus.FINISHED):
    t = datetime(2026, 10, n, tzinfo=timezone.utc)
    return RunView(run_id=f"r{n}", status=status, outcome=outcome, issue=IssueSpec(html_url=f"https://github.com/o/r/issues/{n}",
                   repo="o/r", number=n, title=f"issue {n}"), base_sha="s", created_at=t, updated_at=t,
                   pr=PullRequestRef(url=f"https://github.com/o/r/pull/{pr}", number=pr, head_branch="b") if pr else None)


RUNS = [run(1, Outcome.VERIFIED_FIX, pr=11), run(2, Outcome.FIX_NEEDS_ATTENTION, pr=12), run(3, Outcome.VERIFIED_FIX),
        run(4, Outcome.TRIAGE_ONLY), run(5, Outcome.CANNOT_REPRODUCE), run(6, None, status=RunStatus.RUNNING), run(7, Outcome.VERIFIED_FIX, pr=13)]


def test_counts_are_separate_and_never_conflated():
    c = P.counts(RUNS, {"o/r#11": "merged", "o/r#12": "open", "o/r#13": None})
    assert c == {"started": 7, "analyzed": 6, "fix_proposed": 4, "pr_opened": 3, "pr_merged": 1, "pr_status_unknown": 1}


def test_unknown_pr_status_is_never_counted_as_merged_or_closed():
    c = P.counts(RUNS, {"o/r#11": None, "o/r#12": None, "o/r#13": None})
    assert c["pr_merged"] == 0 and c["pr_status_unknown"] == 3


def test_github_state_mapping():
    assert P.pr_state({"state": "closed", "merged_at": "2026-10-01T00:00:00Z"}) == "merged"
    assert P.pr_state({"state": "closed", "merged_at": None}) == "closed"
    assert P.pr_state({"state": "open", "draft": True}) == "draft"
    assert P.pr_state({"state": "open"}) == "open"
    assert P.pr_state(None) is None and P.pr_state({"message": "Not Found"}) is None


def test_summary_states():
    assert P.summary([], {})["state"] == "empty"
    assert P.summary(RUNS, {"o/r#11": "merged", "o/r#12": "open", "o/r#13": "open"})["state"] == "success"
    s = P.summary(RUNS, {"o/r#11": "merged", "o/r#12": "open", "o/r#13": None})
    assert s["state"] == "partial"
    row = next(r for r in s["rows"] if r["run_id"] == "r7")
    assert row["github_pr_status"] is None and row["patchpilot"]["pr_url"].endswith("/pull/13")
    assert [r["run_id"] for r in s["rows"]] == ["r7", "r6", "r5", "r4", "r3", "r2", "r1"]   # newest first


def test_fetch_failure_gives_unknown(monkeypatch):
    class Boom:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(P, "_client", lambda: Boom())
    monkeypatch.setattr(P, "_get", lambda h, path, required=True: None)       # GitHub blocked / 5xx
    assert P.fetch_pr_states(RUNS) == {"o/r#11": None, "o/r#12": None, "o/r#13": None}


def test_api_progress_is_owner_scoped_and_reports_unknown(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import db
    from backend.api import main
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(P, "fetch_pr_states", lambda runs: {P.key(v): None for v in runs if v.pr})
    a, b = (TestClient(main.app, base_url="https://testserver") for _ in range(2))
    assert a.get("/api/me/progress").json()["state"] == "empty"            # no cookie yet
    from backend.api import session
    a.cookies.set("pp_sid", "tok-a"); b.cookies.set("pp_sid", "tok-b")
    c = db.connect()
    for tok in ("tok-a", "tok-b"):
        with db.tx(c):
            c.execute("INSERT INTO sessions(id_hash,ip_hash,created_at,last_seen_at) VALUES(?,?,?,?)",
                      (session._h(tok), None, db.now().isoformat(), db.now().isoformat()))
    v = db.create_run(c, RUNS[0].issue, "s", owner_session_hash=session._h("tok-a"))
    v.outcome, v.pr = Outcome.VERIFIED_FIX, PullRequestRef(url="https://github.com/o/r/pull/11", number=11, head_branch="b")
    db.save_run(c, v)
    s = a.get("/api/me/progress").json()
    assert s["state"] == "partial" and s["counts"]["pr_opened"] == 1 and s["rows"][0]["github_pr_status"] is None
    assert b.get("/api/me/progress").json()["state"] == "empty"            # other browser sees nothing


def test_same_pr_number_in_two_repos_does_not_collide():
    a = run(1, Outcome.VERIFIED_FIX, pr=12)
    b = run(2, Outcome.VERIFIED_FIX, pr=12)
    b.issue.repo = "other/repo"
    c = P.counts([a, b], {"o/r#12": "merged", "other/repo#12": None})
    assert c["pr_merged"] == 1 and c["pr_status_unknown"] == 1
    rows = {r["repo"]: r["github_pr_status"] for r in P.summary([a, b], {"o/r#12": "merged", "other/repo#12": None})["rows"]}
    assert rows == {"o/r": "merged", "other/repo": None}
