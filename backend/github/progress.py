"""B16 My progress (S-08) + #101 contribution history: PatchPilot facts and GitHub facts kept apart. No scores, streaks or ranks.
A PR status GitHub didn't give us is None ("Status unavailable"), never open/closed as a guess."""
import json
import time
from datetime import datetime

import httpx

from backend import db
from backend.contracts.models import Outcome, RunView
from backend.github.reader import GitHubError, _check, _client

FIX = {Outcome.VERIFIED_FIX, Outcome.FIX_NEEDS_ATTENTION}
FAILED = {"failure", "timed_out", "action_required"}
DONE = {"merged", "closed"}     # re-read only once a day (a closed PR can be reopened)
DONE_RECHECK = 24 * 3600
PAGE = 100                      # one page per list; a full page may hide more, so the read counts as partial
NO_REVIEW = "review_unavailable"   # open PR whose reviews we couldn't read: never shown as plain "open"
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
    """Only a real "success" counts as a pass. Cancelled/skipped/stale-only CI, or runs we didn't all see, are None."""
    runs = (check_runs or {}).get("check_runs")
    if not runs:
        return None     # no CI, or we couldn't read it
    if any(r.get("conclusion") in FAILED for r in runs):
        return "failing"
    if (check_runs.get("total_count") or 0) > len(runs):
        return None     # more runs than we read: a pass we can't see all of isn't a pass
    if any(r.get("status") != "completed" for r in runs):
        return "pending"
    done = {r.get("conclusion") for r in runs}
    return "passing" if "success" in done and done <= {"success", "skipped", "neutral"} else None


def feedback(author: str | None, reviews, review_comments, issue_comments, check_runs) -> list[dict]:
    """What the owner should see: other people's reviews and comments (bots skipped) and failed CI runs. Ids are stable."""
    def human(x):
        u = x.get("user") or {}
        return u.get("login") and u["login"] != author and u.get("type") != "Bot"
    # body/path/line feed the Feedback Assistant (#102); bodies are capped so the stored snapshot stays small
    out = [{"id": f"review:{r['id']}", "kind": "review", "what": REVIEW[r["state"]], "author": r["user"]["login"],
            "at": r.get("submitted_at"), "url": r.get("html_url"), "state": r["state"], "body": (r.get("body") or "")[:4000]}
           for r in reviews or [] if human(r) and r.get("state") in REVIEW and (r["state"] != "COMMENTED" or r.get("body"))]
    out += [{"id": f"{src}:{x['id']}", "kind": "comment", "what": f"Comment on {x['path']}" if x.get("path") else "Comment",
             "author": x["user"]["login"], "at": x.get("created_at"), "url": x.get("html_url"), "body": (x.get("body") or "")[:4000],
             "path": x.get("path"), "line": x.get("line") or x.get("original_line")}
            for src, xs in (("review_comment", review_comments), ("issue_comment", issue_comments)) for x in xs or [] if human(x)]
    out += [{"id": f"ci:{r['id']}", "kind": "ci", "what": f"CI failed: {r.get('name')}", "author": None,
             "at": r.get("completed_at"), "url": r.get("html_url"), "name": r.get("name"),
             "body": "\n".join(filter(None, [(r.get("output") or {}).get("title"), (r.get("output") or {}).get("summary")]))[:4000]}
            for r in (check_runs or {}).get("check_runs") or [] if r.get("conclusion") in FAILED]
    return sorted(out, key=lambda f: f["at"] or "")


class OutOfTime(Exception):
    """The caller's time budget ran out before this GitHub call."""


def _cget(c, h: httpx.Client, path: str, stop: float | None = None):
    """Conditional GET: a 304 reuses the stored body and doesn't count against GitHub's rate limit.
    stop (monotonic deadline): no call starts after it, and none may run past it."""
    left = stop - time.monotonic() if stop else 10
    if left <= 0:
        raise OutOfTime(path)
    old = json.loads(db.get_kv(c, f"gh_etag:{path}") or "null")
    try:
        r = h.get(path, headers={"If-None-Match": old["etag"]} if old else {}, timeout=min(10, left))
    except httpx.HTTPError:
        return None
    if r.status_code == 304 and old:
        return old["body"]
    body = _check(r, required=False)       # raises GitHubError when rate limited
    if body is not None and r.headers.get("etag"):
        db.put_kv(c, f"gh_etag:{path}", json.dumps({"etag": r.headers["etag"], "body": body}))
    return body


def snapshot(c, h: httpx.Client, repo: str, n: int, stop: float | None = None) -> dict:
    """Everything is read with the read-only token. A missing PR read is "unavailable". A failed or truncated sub-read
    marks the snapshot partial (refresh keeps the earlier feedback) and never makes the PR look cleaner than it is."""
    pr = _cget(c, h, f"/repos/{repo}/pulls/{n}", stop)
    if not isinstance(pr, dict) or "state" not in pr:
        return {"state": None, "ci": None}
    author = (pr.get("user") or {}).get("login")
    rv = _cget(c, h, f"/repos/{repo}/pulls/{n}/reviews?per_page=100", stop)
    rc = _cget(c, h, f"/repos/{repo}/pulls/{n}/comments?per_page=100", stop)
    ic = _cget(c, h, f"/repos/{repo}/issues/{n}/comments?per_page=100", stop)
    sha = (pr.get("head") or {}).get("sha")
    ck = _cget(c, h, f"/repos/{repo}/commits/{sha}/check-runs?per_page=100", stop) if sha else None
    fb = feedback(author, rv, rc, ic, ck)
    lists_ok = [isinstance(x, list) and len(x) < PAGE for x in (rv, rc, ic)]
    partial = not all(lists_ok) or not isinstance(ck, dict) or (ck.get("total_count") or 0) > len(ck.get("check_runs") or [])
    state = pr_state(pr, rv) if isinstance(rv, list) else pr_state(pr)
    if state in ("open", "approved", "changes_requested") and not lists_ok[0]:
        state = NO_REVIEW               # reviews failed or filled a page: a decision from page 1 isn't the latest
    return {"state": state, "ci": ci_state(ck) if isinstance(ck, dict) else None, "partial": partial, "head": sha,
            "last_activity_at": max((f["at"] for f in fb if f["kind"] != "ci" and f["at"]), default=None), "feedback": fb}


def key(v: RunView) -> str | None:
    """PRs are identified by repo AND number: #12 in two repos are different PRs."""
    return f"{v.issue.repo}#{v.pr.number}" if v.pr and v.pr.number else None


def tracked(c, run_id: str) -> dict:
    return json.loads(db.get_kv(c, f"pr_track:{run_id}") or "{}")


def merge(prev: dict, snap: dict | None) -> dict:
    """Unavailable keeps the last feedback; partial adds to it, so a failed sub-read never drops feedback."""
    if not snap or snap["state"] is None:
        return {**prev, "state": None, "ci": None, "partial": True}
    if snap.get("partial"):
        have = {f["id"] for f in snap["feedback"]}
        kept = [f for f in prev.get("feedback", []) if f["id"] not in have]
        return {**snap, "feedback": sorted([*kept, *snap["feedback"]], key=lambda f: f["at"] or "")}
    return snap


def refresh(c, runs: list[RunView], *, budget: float | None = None) -> dict[str, dict]:
    """Re-read each PR once (runs sharing a PR share the read) and store it per run. Merged/closed PRs aren't re-read.
    Rate limited -> the rest are "unavailable" now, keeping their last feedback. budget (s): no GitHub call runs past
    it; PRs not finished in time are returned as "unavailable" but not stored, so the next tick or load retries them."""
    todo = [v for v in runs if key(v)]
    out = {v.run_id: tracked(c, v.run_id) for v in todo}
    # least recently checked first, so a PR that missed a budget isn't starved by the same PRs every time
    want = sorted((v for v in todo if _due(out[v.run_id])), key=lambda v: out[v.run_id].get("checked_at") or "")
    if not want:
        return out
    stop, limited, read = (time.monotonic() + budget) if budget else None, False, {}
    try:
        with _client() as h:
            for v in want:
                k = key(v)
                if k not in read:
                    snap = None
                    if not limited:
                        try:
                            snap = snapshot(c, h, v.issue.repo, v.pr.number, stop)
                        except GitHubError:
                            limited = True
                        except OutOfTime:
                            break
                        except Exception as e:     # one odd PR (non-JSON 200, malformed item) never stops the rest
                            print(f"PR read failed for {k}: {e!r}", flush=True)
                    read[k] = snap
                _prune(c, v.issue.repo, out[v.run_id].get("head"), (read[k] or {}).get("head"))
                out[v.run_id] = {**merge(out[v.run_id], read[k]), "checked_at": db.now().isoformat()}
                db.put_kv(c, f"pr_track:{v.run_id}", json.dumps(out[v.run_id]))
    except Exception:
        pass
    for v in want:
        if key(v) not in read:          # not reached in time (or the client failed): unavailable for now, not stored
            out[v.run_id] = merge(out[v.run_id], None)
    return out


def _due(t: dict) -> bool:
    """Open or never-read PRs every time; done ones once a day, or at once if stored before bodies were kept."""
    if t.get("state") not in DONE:
        return True
    if any(f["kind"] != "ci" and "body" not in f for f in t.get("feedback", [])):
        return True
    at = t.get("checked_at")
    return not at or (db.now() - datetime.fromisoformat(at)).total_seconds() > DONE_RECHECK


def _prune(c, repo: str, old: str | None, new: str | None) -> None:
    """Check-runs are cached per head SHA; once the PR's head moves, the old SHA's cached body is dead weight."""
    if old and new and old != new:
        c.execute("DELETE FROM kv WHERE key=?", (f"gh_etag:/repos/{repo}/commits/{old}/check-runs?per_page=100",))


def poll(c, budget: float = 20) -> None:
    """Worker, every 10 min: refresh PRs within a time budget so the job loop and its heartbeat aren't held up (what's
    left waits for the next tick). Forgotten runs (no owner) are skipped, and so is a row that doesn't validate."""
    runs = []
    for (raw,) in c.execute("SELECT state_json FROM runs WHERE owner_session_hash IS NOT NULL OR owner_account_id IS NOT NULL"):
        try:
            runs.append(RunView.model_validate_json(raw))
        except ValueError:
            continue
    refresh(c, runs, budget=budget)


def new_feedback(c, run_id: str, snap: dict | None = None) -> list[dict]:
    seen = set(json.loads(db.get_kv(c, f"pr_seen:{run_id}") or "[]"))
    return [f for f in (snap if snap is not None else tracked(c, run_id)).get("feedback", []) if f["id"] not in seen]


def mark_seen(c, run_id: str, ids: list[str]) -> None:
    """Only what the owner was actually shown (ids from the page), added to what they saw before."""
    old = set(json.loads(db.get_kv(c, f"pr_seen:{run_id}") or "[]"))
    shown = set(ids) & {f["id"] for f in tracked(c, run_id).get("feedback", [])}
    db.put_kv(c, f"pr_seen:{run_id}", json.dumps(sorted(old | shown)))


def counts(runs: list[RunView], gh: dict[str, str | None]) -> dict[str, int]:
    prs = [key(v) for v in runs if v.pr and v.pr.url and v.pr.number]
    return {"started": len(runs),
            "analyzed": sum(v.outcome is not None for v in runs),
            "fix_proposed": sum(v.outcome in FIX for v in runs),
            "pr_opened": len(prs),
            "pr_merged": sum(gh.get(n) == "merged" for n in prs),
            "pr_status_unknown": sum(gh.get(n) in (None, NO_REVIEW) for n in prs)}


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
                "needs_attention": bool(new) or st in ("changes_requested", NO_REVIEW) or x.get("ci") == "failing"
                or v.status == "awaiting_approval"}
    rows = [row(v) for v in sorted(runs, key=lambda v: v.created_at, reverse=True)]
    c = counts(runs, gh)
    return {"state": "partial" if c["pr_status_unknown"] else "success", "counts": c, "rows": rows}
