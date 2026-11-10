"""B16 My progress (S-08) + #101 contribution history: PatchPilot facts and GitHub facts kept apart. No scores, streaks or ranks.
A PR status GitHub didn't give us is None ("Status unavailable"), never open/closed as a guess."""
import json

import httpx

from backend import db
from backend.contracts.models import Outcome, RunView
from backend.github.reader import GitHubError, _check, _client

FIX = {Outcome.VERIFIED_FIX, Outcome.FIX_NEEDS_ATTENTION}
FAILED = {"failure", "timed_out", "action_required"}
DONE = {"merged", "closed"}     # the worker stops polling these
REVIEW = {"CHANGES_REQUESTED": "Changes requested", "APPROVED": "Approved", "COMMENTED": "Review"}


def review_state(reviews: list[dict], author: str | None) -> str | None:
    """Latest decisive review per reviewer (GitHub's rule): any changes-requested wins, then approved. A dismissal clears it."""
    latest: dict[str, str] = {}
    for r in sorted(reviews, key=lambda r: r.get("submitted_at") or ""):
        who = (r.get("user") or {}).get("login")
        if who and who != author and r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[who] = r["state"]
    s = set(latest.values())
    return "changes_requested" if "CHANGES_REQUESTED" in s else "approved" if "APPROVED" in s else None


def pr_state(pr: dict | None, reviews: list[dict] | None = None) -> str | None:
    if not isinstance(pr, dict) or "state" not in pr:
        return None
    if pr["state"] == "closed":
        return "merged" if pr.get("merged_at") else "closed"
    if pr["state"] != "open":
        return None
    if pr.get("draft"):
        return "draft"
    return review_state(reviews or [], (pr.get("user") or {}).get("login")) or "open"


def ci_state(check_runs: dict | None) -> str | None:
    runs = (check_runs or {}).get("check_runs")
    if not runs:
        return None     # no CI, or we couldn't read it
    if any(r.get("conclusion") in FAILED for r in runs):
        return "failing"
    return "pending" if any(r.get("status") != "completed" for r in runs) else "passing"


def feedback(author: str | None, reviews, review_comments, issue_comments, check_runs) -> list[dict]:
    """What the owner should see: other people's reviews and comments (bots skipped) and failed CI runs. Ids are stable."""
    def human(x):
        u = x.get("user") or {}
        return u.get("login") and u["login"] != author and u.get("type") != "Bot"
    out = [{"id": f"review:{r['id']}", "kind": "review", "what": REVIEW[r["state"]], "author": r["user"]["login"],
            "at": r.get("submitted_at"), "url": r.get("html_url")}
           for r in reviews or [] if human(r) and r.get("state") in REVIEW and (r["state"] != "COMMENTED" or r.get("body"))]
    out += [{"id": f"comment:{x['id']}", "kind": "comment", "what": f"Comment on {x['path']}" if x.get("path") else "Comment",
             "author": x["user"]["login"], "at": x.get("created_at"), "url": x.get("html_url")}
            for x in [*(review_comments or []), *(issue_comments or [])] if human(x)]
    out += [{"id": f"ci:{r['id']}", "kind": "ci", "what": f"CI failed: {r.get('name')}", "author": None,
             "at": r.get("completed_at"), "url": r.get("html_url")}
            for r in (check_runs or {}).get("check_runs") or [] if r.get("conclusion") in FAILED]
    return sorted(out, key=lambda f: f["at"] or "")


def _cget(c, h: httpx.Client, path: str):
    """Conditional GET: a 304 reuses the stored body and doesn't count against GitHub's rate limit."""
    old = json.loads(db.get_kv(c, f"gh_etag:{path}") or "null")
    try:
        r = h.get(path, headers={"If-None-Match": old["etag"]} if old else {})
    except httpx.HTTPError:
        return None
    if r.status_code == 304 and old:
        return old["body"]
    body = _check(r, required=False)       # raises GitHubError when rate limited
    if body is not None and r.headers.get("etag"):
        db.put_kv(c, f"gh_etag:{path}", json.dumps({"etag": r.headers["etag"], "body": body}))
    return body


def snapshot(c, h: httpx.Client, repo: str, n: int) -> dict:
    """Everything is read with the read-only token. A missing PR read is "unavailable"; missing sub-reads are just left out."""
    pr = _cget(c, h, f"/repos/{repo}/pulls/{n}")
    if not isinstance(pr, dict) or "state" not in pr:
        return {"state": None, "ci": None}
    author = (pr.get("user") or {}).get("login")
    rv = _cget(c, h, f"/repos/{repo}/pulls/{n}/reviews?per_page=100")
    rc = _cget(c, h, f"/repos/{repo}/pulls/{n}/comments?per_page=100")
    ic = _cget(c, h, f"/repos/{repo}/issues/{n}/comments?per_page=100")
    sha = (pr.get("head") or {}).get("sha")
    ck = _cget(c, h, f"/repos/{repo}/commits/{sha}/check-runs?per_page=100") if sha else None
    fb = feedback(author, rv, rc, ic, ck)
    people = [f["at"] for f in fb if f["kind"] != "ci" and f["at"]]
    return {"state": pr_state(pr, rv if isinstance(rv, list) else None), "ci": ci_state(ck),
            "last_activity_at": max(people, default=None), "feedback": fb}


def key(v: RunView) -> str | None:
    """PRs are identified by repo AND number: #12 in two repos are different PRs."""
    return f"{v.issue.repo}#{v.pr.number}" if v.pr and v.pr.number else None


def tracked(c, run_id: str) -> dict:
    return json.loads(db.get_kv(c, f"pr_track:{run_id}") or "{}")


def refresh(c, runs: list[RunView]) -> dict[str, dict]:
    """Re-read each run's PR and store it. Rate limited -> the rest are "unavailable" now, keeping their last feedback."""
    out: dict[str, dict] = {}
    todo = [v for v in runs if key(v)]
    if not todo:
        return out
    limited = False
    try:
        with _client() as h:
            for v in todo:
                snap = None
                if not limited:
                    try:
                        snap = snapshot(c, h, v.issue.repo, v.pr.number)
                    except GitHubError:
                        limited = True
                prev = tracked(c, v.run_id)
                if not snap or snap["state"] is None:
                    snap = {**prev, "state": None, "ci": None}
                db.put_kv(c, f"pr_track:{v.run_id}", json.dumps(snap))
                out[v.run_id] = snap
    except Exception:
        pass
    return {v.run_id: out.get(v.run_id) or {**tracked(c, v.run_id), "state": None, "ci": None} for v in todo}


def poll(c) -> None:
    """Worker, every 10 min: refresh every PR that isn't merged or closed yet."""
    runs = [RunView.model_validate_json(r[0]) for r in c.execute("SELECT state_json FROM runs").fetchall()]
    refresh(c, [v for v in runs if key(v) and tracked(c, v.run_id).get("state") not in DONE])


def new_feedback(c, run_id: str, snap: dict | None = None) -> list[dict]:
    seen = set(json.loads(db.get_kv(c, f"pr_seen:{run_id}") or "[]"))
    return [f for f in (snap if snap is not None else tracked(c, run_id)).get("feedback", []) if f["id"] not in seen]


def mark_seen(c, run_id: str) -> None:
    db.put_kv(c, f"pr_seen:{run_id}", json.dumps([f["id"] for f in tracked(c, run_id).get("feedback", [])]))


def counts(runs: list[RunView], gh: dict[str, str | None]) -> dict[str, int]:
    prs = [key(v) for v in runs if v.pr and v.pr.url and v.pr.number]
    return {"started": len(runs),
            "analyzed": sum(v.outcome is not None for v in runs),
            "fix_proposed": sum(v.outcome in FIX for v in runs),
            "pr_opened": len(prs),
            "pr_merged": sum(gh.get(n) == "merged" for n in prs),
            "pr_status_unknown": sum(gh.get(n) is None for n in prs)}


def summary(runs: list[RunView], gh: dict[str, str | None], extra: dict[str, dict] | None = None) -> dict:
    """extra: run_id -> {ci, last_activity_at, new_feedback} from the tracked snapshots."""
    if not runs:
        return {"state": "empty", "counts": counts([], {}), "rows": []}
    extra = extra or {}

    def row(v: RunView) -> dict:
        x, st = extra.get(v.run_id, {}), gh.get(key(v)) if key(v) else None
        new = x.get("new_feedback", 0)
        return {"run_id": v.run_id, "repo": v.issue.repo, "number": v.issue.number, "title": v.issue.title,
                "issue_url": v.issue.html_url, "created_at": v.created_at,
                "patchpilot": {"status": v.status, "outcome": v.outcome, "readiness": v.readiness,
                               "pr_url": v.pr.url if v.pr else None, "compare_url": v.pr.compare_url if v.pr else None},
                "github_pr_status": st, "has_pr": bool(v.pr and v.pr.number),
                "ci": x.get("ci"), "last_activity_at": x.get("last_activity_at"), "new_feedback": new,
                "needs_attention": bool(new) or st == "changes_requested" or x.get("ci") == "failing"
                or v.status == "awaiting_approval"}
    rows = [row(v) for v in sorted(runs, key=lambda v: v.created_at, reverse=True)]
    c = counts(runs, gh)
    return {"state": "partial" if c["pr_status_unknown"] else "success", "counts": c, "rows": rows}
