"""#101: real GitHub PR state (reviews, CI) and the in-app feedback badge. Fixture: wheelgap/wheelgap#133, recorded 2026-11-10."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.contracts.models import IssueSpec, Outcome, PullRequestRef
from backend.github import progress as P

FX = Path(__file__).parent.parent / "fixtures/github/wheelgap-pr-133"
REPO, N = "wheelgap/wheelgap", 133


def load(name):
    return json.loads((FX / f"{name}.json").read_text(encoding="utf-8"))


def github(routes, calls=None):
    """A fake GitHub answering from recorded JSON; paths not in routes get 404."""
    def handle(req: httpx.Request):
        path = req.url.raw_path.decode()
        if calls is not None:
            calls.append((path, req.headers.get("if-none-match")))
        r = routes.get(path)
        if callable(r):
            return r(req)
        if r is None:
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json=r, headers={"etag": f'"{len(path)}"'})
    return lambda: httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handle))


def recorded(**over):
    pr, base = load("pull"), f"/repos/{REPO}"
    routes = {f"{base}/pulls/{N}": pr, f"{base}/pulls/{N}/reviews?per_page=100": load("reviews"),
              f"{base}/pulls/{N}/comments?per_page=100": load("review_comments"),
              f"{base}/issues/{N}/comments?per_page=100": load("issue_comments"),
              f"{base}/commits/{pr['head']['sha']}/check-runs?per_page=100": load("check_runs")}
    return {**routes, **{f"{base}/{k}": v for k, v in over.items()}}


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    return db.connect()


def new_run(c, sess="h-a"):
    v = db.create_run(c, IssueSpec(html_url=f"https://github.com/{REPO}/issues/114", repo=REPO, number=114, title="t"), "s",
                      owner_session_hash=sess)
    v.outcome, v.pr = Outcome.VERIFIED_FIX, PullRequestRef(url=f"https://github.com/{REPO}/pull/{N}", number=N, head_branch="b")
    db.save_run(c, v)
    return v


def test_recorded_wheelgap_pr_maps_to_merged_with_maintainer_comments(c, monkeypatch):
    monkeypatch.setattr(P, "_client", github(recorded()))
    s = P.snapshot(c, P._client(), REPO, N)
    assert s["state"] == "merged" and s["ci"] == "passing"
    assert [f["author"] for f in s["feedback"]] == ["patrickballard"] * 3          # the contributor's own activity is skipped
    assert all(f["kind"] == "comment" and f["url"] for f in s["feedback"])
    assert s["last_activity_at"] == "2026-11-09T19:59:11Z"


def test_open_pr_review_states_follow_latest_review_per_reviewer():
    def r(who, state, t): return {"user": {"login": who}, "state": state, "submitted_at": t}
    open_pr = {"state": "open", "draft": False, "user": {"login": "me"}}
    assert P.pr_state(open_pr, []) == "open"
    assert P.pr_state(open_pr, [r("m", "APPROVED", "1")]) == "approved"
    assert P.pr_state(open_pr, [r("m", "APPROVED", "1"), r("k", "CHANGES_REQUESTED", "2")]) == "changes_requested"
    assert P.pr_state(open_pr, [r("m", "CHANGES_REQUESTED", "1"), r("m", "APPROVED", "2")]) == "approved"   # m changed their mind
    assert P.pr_state(open_pr, [r("m", "CHANGES_REQUESTED", "1"), r("m", "DISMISSED", "2")]) == "open"
    assert P.pr_state(open_pr, [r("m", "COMMENTED", "1")]) == "open"                # a comment isn't a decision
    assert P.pr_state(open_pr, [r("me", "APPROVED", "1")]) == "open"                # your own review doesn't count
    assert P.pr_state({**open_pr, "draft": True}, [r("m", "APPROVED", "1")]) == "draft"


def test_failed_ci_is_failing_and_becomes_feedback(c, monkeypatch):
    ck = load("check_runs")
    i = next(i for i, r in enumerate(ck["check_runs"]) if r["name"] == "lint")
    ck["check_runs"][i] = {**ck["check_runs"][i], "conclusion": "failure"}
    sha = load("pull")["head"]["sha"]
    monkeypatch.setattr(P, "_client", github(recorded(**{f"commits/{sha}/check-runs?per_page=100": ck})))
    s = P.snapshot(c, P._client(), REPO, N)
    assert s["ci"] == "failing" and [f["what"] for f in s["feedback"] if f["kind"] == "ci"] == ["CI failed: lint"]
    assert P.ci_state(None) is None and P.ci_state({"check_runs": []}) is None    # no CI is unknown, never "passing"


def test_github_error_gives_unavailable_and_keeps_the_badge(c, monkeypatch):
    v = new_run(c)
    monkeypatch.setattr(P, "_client", github(recorded()))
    assert P.refresh(c, [v])[v.run_id]["state"] == "merged"
    def limited(req):
        return httpx.Response(403, text="API rate limit exceeded", headers={"x-ratelimit-reset": "60"})
    monkeypatch.setattr(P, "_client", github({f"/repos/{REPO}/pulls/{N}": limited}))
    s = P.refresh(c, [v])[v.run_id]
    assert s["state"] is None and s["ci"] is None                                   # "Status unavailable", not a guess
    assert len(P.new_feedback(c, v.run_id)) == 3                                    # last-known feedback still flagged
    monkeypatch.setattr(P, "_client", github({}))                                   # PR gone / 404
    assert P.refresh(c, [v])[v.run_id]["state"] is None


def test_conditional_requests_reuse_the_stored_body_on_304(c, monkeypatch):
    calls, routes = [], recorded()
    monkeypatch.setattr(P, "_client", github(routes, calls))
    first = P.snapshot(c, P._client(), REPO, N)
    assert calls and all(tag is None for _, tag in calls)
    calls.clear()
    monkeypatch.setattr(P, "_client", github({k: (lambda req: httpx.Response(304)) for k in routes}, calls))
    assert P.snapshot(c, P._client(), REPO, N) == first and all(tag for _, tag in calls)


def test_badge_sets_on_new_feedback_clears_after_viewing_and_is_owner_scoped(c, monkeypatch):
    from backend.api import main, session
    monkeypatch.setattr(P, "_client", github(recorded()))
    a, b = (TestClient(main.app, base_url="https://testserver") for _ in range(2))
    a.cookies.set("pp_sid", "tok-a")
    b.cookies.set("pp_sid", "tok-b")
    for tok in ("tok-a", "tok-b"):
        c.execute("INSERT INTO sessions(id_hash,ip_hash,created_at,last_seen_at) VALUES(?,?,?,?)",
                  (session._h(tok), None, db.now().isoformat(), db.now().isoformat()))
    v = new_run(c, session._h("tok-a"))
    row = a.get("/api/me/progress").json()["rows"][0]                               # page load refreshes from GitHub
    assert row["github_pr_status"] == "merged" and row["new_feedback"] == 3 and row["needs_attention"]
    assert a.get("/api/me/runs").json()[0]["new_feedback"] == 3                     # drives the nav badge
    assert b.get(f"/api/runs/{v.run_id}/feedback").status_code == 404
    assert b.post(f"/api/runs/{v.run_id}/feedback/seen").status_code == 404
    assert b.get("/api/me/progress").json()["state"] == "empty"
    fb = a.get(f"/api/runs/{v.run_id}/feedback").json()
    assert fb["state"] == "merged" and [i["new"] for i in fb["items"]] == [True] * 3
    assert a.post(f"/api/runs/{v.run_id}/feedback/seen").status_code == 204
    assert a.get("/api/me/runs").json()[0]["new_feedback"] == 0
    assert not a.get("/api/me/progress").json()["rows"][0]["needs_attention"]
    more = [*load("issue_comments"), {"id": 1, "user": {"login": "patrickballard", "type": "User"},
                                      "created_at": "2026-11-10T08:00:00Z", "html_url": "u"}]
    monkeypatch.setattr(P, "_client", github(recorded(**{f"issues/{N}/comments?per_page=100": more})))
    P.poll(c)                                                                       # merged PRs aren't polled again
    assert a.get("/api/me/runs").json()[0]["new_feedback"] == 0
    c.execute("DELETE FROM kv WHERE key=?", (f"pr_track:{v.run_id}",))              # a PR not known to be done is polled
    P.poll(c)
    assert a.get("/api/me/runs").json()[0]["new_feedback"] == 1
