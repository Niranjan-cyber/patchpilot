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


def opened(**over):
    """The recorded PR as if still open (same comments and CI), so the poll and page load keep re-reading it."""
    return recorded(**{f"pulls/{N}": {**load("pull"), "state": "open", "merged_at": None, "draft": False}, **over})


def changes_requested():
    return [{"id": 77, "user": {"login": "patrickballard", "type": "User"}, "state": "CHANGES_REQUESTED",
             "submitted_at": "2026-11-09T18:50:00Z", "body": "Please keep the --online check.", "html_url": "r"}]


def bad_gateway(req):
    return httpx.Response(502, text="Bad Gateway")


def test_failed_reviews_read_never_shows_plain_open_or_drops_feedback(c, monkeypatch):
    v = new_run(c)
    monkeypatch.setattr(P, "_client", github(opened(**{f"pulls/{N}/reviews?per_page=100": changes_requested()})))
    s = P.refresh(c, [v])[v.run_id]
    assert s["state"] == "changes_requested" and len(s["feedback"]) == 4 and not s["partial"]
    monkeypatch.setattr(P, "_client", github(opened(**{f"pulls/{N}/reviews?per_page=100": bad_gateway})))
    s = P.refresh(c, [v])[v.run_id]
    assert s["state"] == P.NO_REVIEW and s["partial"]                               # "Review status unavailable"
    assert "review:77" in {f["id"] for f in s["feedback"]} and len(s["feedback"]) == 4   # earlier review kept
    assert P.summary([v], {P.key(v): s["state"]}, {v.run_id: {}})["rows"][0]["needs_attention"]


def test_ci_without_a_real_success_is_not_passing():
    def ck(*conclusions, total=None):
        runs = [{"status": "completed", "conclusion": x} for x in conclusions]
        return {"total_count": total or len(runs), "check_runs": runs}
    assert P.ci_state(ck("cancelled", "cancelled")) is None
    assert P.ci_state(ck("skipped", "neutral", "stale")) is None
    assert P.ci_state(ck("success", "cancelled")) is None                          # a cancelled job may be the tests
    assert P.ci_state(ck("success", "skipped")) == "passing"
    assert P.ci_state(ck("success", total=150)) is None                            # runs past the first page unseen
    assert P.ci_state(ck("failure", total=150)) == "failing"


def test_github_error_gives_unavailable_and_keeps_the_badge(c, monkeypatch):
    v = new_run(c)
    monkeypatch.setattr(P, "_client", github(opened()))
    assert P.refresh(c, [v])[v.run_id]["state"] == "open"
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


def test_merged_prs_are_not_re_read_and_shared_prs_are_read_once(c, monkeypatch):
    calls = []
    monkeypatch.setattr(P, "_client", github(recorded(), calls))
    v, w = new_run(c), new_run(c)                                                   # two runs, same PR
    out = P.refresh(c, [v, w])
    assert out[v.run_id]["state"] == out[w.run_id]["state"] == "merged"
    assert sum(p == f"/repos/{REPO}/pulls/{N}" for p, _ in calls) == 1
    calls.clear()
    assert P.refresh(c, [v, w])[v.run_id]["state"] == "merged" and calls == []      # done: stored state, no reads


def test_budget_is_checked_before_every_github_call(c, monkeypatch):
    import time as t
    calls, routes = [], opened()

    def slow(path):
        def h(req):
            t.sleep(0.25)
            return httpx.Response(200, json=routes[path])
        return h
    monkeypatch.setattr(P, "_client", github({k: slow(k) for k in routes}, calls))
    v = new_run(c)
    out = P.refresh(c, [v], budget=0.6)                                            # room for ~2 of the 5 reads
    assert 1 <= len(calls) <= 3                                                     # stopped mid-PR, not after it
    assert out[v.run_id]["state"] is None                                           # unavailable for now...
    assert P.tracked(c, v.run_id) == {}                                             # ...and not stored: the next tick retries


def test_a_pr_that_missed_the_budget_is_read_first_next_time(c, monkeypatch):
    v, w = new_run(c), new_run(c)
    w.pr = w.pr.model_copy(update={"number": 134, "url": f"https://github.com/{REPO}/pull/134"})
    db.save_run(c, w)
    order = []

    def one_per_call(c_, h, repo, n, stop=None):          # time for one PR per refresh
        if order and order[-1][1] == "call":
            raise P.OutOfTime(str(n))
        order.append((n, "call"))
        return {"state": "open", "ci": None, "partial": False, "last_activity_at": None, "feedback": []}
    monkeypatch.setattr(P, "_client", github({}))
    monkeypatch.setattr(P, "snapshot", one_per_call)
    first = P.refresh(c, [v, w], budget=8)
    order.append((None, "next"))
    second = P.refresh(c, [v, w], budget=8)
    read = [n for n, k in order if k == "call"]
    assert len(read) == 2 and read[0] != read[1]                                    # the other PR goes first next time
    assert {first[v.run_id]["state"], first[w.run_id]["state"]} == {"open", None}
    assert {second[v.run_id]["state"], second[w.run_id]["state"]} == {"open", None}
    assert P.tracked(c, v.run_id)["state"] == P.tracked(c, w.run_id)["state"] == "open"   # both stored after two loads


def test_poll_stops_at_its_time_budget(c, monkeypatch):
    calls = []
    monkeypatch.setattr(P, "_client", github(opened(), calls))
    new_run(c)
    P.poll(c, budget=-1)                                                            # already over budget: reads nothing
    assert calls == []
    P.poll(c, budget=20)
    assert calls


def test_badge_sets_on_new_feedback_clears_after_viewing_and_is_owner_scoped(c, monkeypatch):
    from backend.api import main, session
    monkeypatch.setattr(P, "_client", github(opened()))
    a, b = (TestClient(main.app, base_url="https://testserver") for _ in range(2))
    a.cookies.set("pp_sid", "tok-a")
    b.cookies.set("pp_sid", "tok-b")
    for tok in ("tok-a", "tok-b"):
        c.execute("INSERT INTO sessions(id_hash,ip_hash,created_at,last_seen_at) VALUES(?,?,?,?)",
                  (session._h(tok), None, db.now().isoformat(), db.now().isoformat()))
    v = new_run(c, session._h("tok-a"))
    row = a.get("/api/me/progress").json()["rows"][0]                               # page load refreshes from GitHub
    assert row["github_pr_status"] == "open" and row["new_feedback"] == 3 and row["needs_attention"]
    assert a.get("/api/me/runs").json()[0]["new_feedback"] == 3                     # drives the nav badge
    assert b.get(f"/api/runs/{v.run_id}/feedback").status_code == 404
    assert b.post(f"/api/runs/{v.run_id}/feedback/seen", json={"ids": []}).status_code == 404
    assert b.get("/api/me/progress").json()["state"] == "empty"
    fb = a.get(f"/api/runs/{v.run_id}/feedback").json()
    shown = [i["id"] for i in fb["items"]]
    assert fb["state"] == "open" and [i["new"] for i in fb["items"]] == [True] * 3
    more = [*load("issue_comments"), {"id": 1, "user": {"login": "patrickballard", "type": "User"},
                                      "created_at": "2026-11-10T08:00:00Z", "html_url": "u"}]
    monkeypatch.setattr(P, "_client", github(opened(**{f"issues/{N}/comments?per_page=100": more})))
    P.poll(c)                                                                       # arrives between the page's GET and its "seen"
    assert a.post(f"/api/runs/{v.run_id}/feedback/seen", json={"ids": [*shown, "issue_comment:999"]}).status_code == 204
    assert [f["id"] for f in P.new_feedback(c, v.run_id)] == ["issue_comment:1"]   # unseen stays new; unknown ids ignored
    assert a.get("/api/me/runs").json()[0]["new_feedback"] == 1
    assert a.post(f"/api/runs/{v.run_id}/feedback/seen", json={"ids": ["issue_comment:1"]}).status_code == 204
    assert a.get("/api/me/runs").json()[0]["new_feedback"] == 0                     # union with what was seen before
    assert not a.get("/api/me/progress").json()["rows"][0]["needs_attention"]


def test_a_done_pr_stored_without_text_is_read_once_more(c, monkeypatch):
    v = new_run(c)
    db.put_kv(c, f"pr_track:{v.run_id}", json.dumps({"state": "merged", "feedback": [
        {"id": "issue_comment:6748392117", "kind": "comment", "author": "patrickballard", "at": "x", "url": "u"}]}))   # pre-#102 shape
    calls = []
    monkeypatch.setattr(P, "_client", github(recorded(), calls))
    s = P.refresh(c, [v])[v.run_id]
    assert calls and all("body" in f for f in s["feedback"])
    calls.clear()
    P.refresh(c, [v])
    assert calls == []                                                              # done and complete: not read again


def test_a_done_pr_is_re_read_once_a_day_so_a_reopen_shows(c, monkeypatch):
    from datetime import timedelta
    v = new_run(c)
    calls = []
    monkeypatch.setattr(P, "_client", github(opened(), calls))                      # it was reopened on GitHub
    fresh = {"state": "closed", "feedback": [], "checked_at": db.now().isoformat()}
    db.put_kv(c, f"pr_track:{v.run_id}", json.dumps(fresh))
    assert P.refresh(c, [v])[v.run_id]["state"] == "closed" and calls == []         # checked today: not re-read
    db.put_kv(c, f"pr_track:{v.run_id}", json.dumps({**fresh, "checked_at": (db.now() - timedelta(days=2)).isoformat()}))
    assert P.refresh(c, [v])[v.run_id]["state"] == "open" and calls


def test_a_full_page_of_reviews_never_shows_page_one_as_the_decision(c, monkeypatch):
    many = [{"id": i, "user": {"login": f"u{i}", "type": "User"}, "state": "APPROVED", "submitted_at": f"2026-11-01T00:00:{i % 60:02d}Z",
             "body": "", "html_url": "r"} for i in range(100)]
    monkeypatch.setattr(P, "_client", github(opened(**{f"pulls/{N}/reviews?per_page=100": many})))
    s = P.snapshot(c, P._client(), REPO, N)
    assert s["state"] == P.NO_REVIEW and s["partial"]


def test_one_broken_pr_never_stops_the_others(c, monkeypatch):
    v, w = new_run(c), new_run(c)
    w.pr = w.pr.model_copy(update={"number": 134, "url": f"https://github.com/{REPO}/pull/134"})
    db.save_run(c, w)
    routes = {**opened(), f"/repos/{REPO}/pulls/134": lambda req: httpx.Response(200, text="<html>not json</html>")}
    monkeypatch.setattr(P, "_client", github(routes))
    out = P.refresh(c, [w, v])
    assert out[w.run_id]["state"] is None and P.tracked(c, w.run_id)["state"] is None   # stored as unavailable
    assert out[v.run_id]["state"] == "open"                                          # and the next PR was still read


def test_poll_skips_forgotten_runs_and_rows_that_dont_validate(c, monkeypatch):
    calls = []
    monkeypatch.setattr(P, "_client", github(opened(), calls))
    v = new_run(c)
    c.execute("UPDATE runs SET owner_session_hash=NULL WHERE run_id=?", (v.run_id,))   # "Forget this run"
    w = new_run(c)
    c.execute("UPDATE runs SET state_json='{\"broken\": true}' WHERE run_id=?", (w.run_id,))
    P.poll(c)
    assert calls == [] and P.tracked(c, v.run_id) == {}
    x = new_run(c)
    P.poll(c)
    assert calls and P.tracked(c, x.run_id)["state"] == "open"


def test_old_head_check_runs_are_pruned_when_the_head_moves(c, monkeypatch):
    v = new_run(c)
    monkeypatch.setattr(P, "_client", github(opened()))
    P.refresh(c, [v])
    old = load("pull")["head"]["sha"]
    old_key = f"gh_etag:/repos/{REPO}/commits/{old}/check-runs?per_page=100"
    assert db.get_kv(c, old_key)
    moved = {**load("pull"), "state": "open", "merged_at": None, "head": {**load("pull")["head"], "sha": "f" * 40}}
    monkeypatch.setattr(P, "_client", github(opened(**{f"pulls/{N}": moved,
                                                        f"commits/{'f' * 40}/check-runs?per_page=100": load("check_runs")})))
    db.put_kv(c, f"pr_track:{v.run_id}", json.dumps({**P.tracked(c, v.run_id), "checked_at": ""}))
    P.refresh(c, [v])
    assert db.get_kv(c, old_key) is None and P.tracked(c, v.run_id)["head"] == "f" * 40
