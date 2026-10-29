"""B16 My progress (S-08): PatchPilot facts and GitHub facts kept apart. No scores, streaks or ranks.
A PR status GitHub didn't give us is None ("Status unavailable"), never open/closed as a guess."""
from backend.contracts.models import Outcome, RunView
from backend.github.reader import GitHubError, _client, _get

FIX = {Outcome.VERIFIED_FIX, Outcome.FIX_NEEDS_ATTENTION}


def pr_state(pr: dict | None) -> str | None:
    if not isinstance(pr, dict) or "state" not in pr:
        return None
    if pr["state"] == "closed":
        return "merged" if pr.get("merged_at") else "closed"
    return "draft" if pr.get("draft") else "open" if pr["state"] == "open" else None


def fetch_pr_states(runs: list[RunView]) -> dict[int, str | None]:
    """One read per PR with the server's read-only token. Any failure -> None for that PR."""
    out: dict[int, str | None] = {}
    want = [(v.issue.repo, v.pr.number) for v in runs if v.pr and v.pr.number]
    if not want:
        return out
    try:
        with _client() as h:
            for repo, n in want:
                try:
                    out[n] = pr_state(_get(h, f"/repos/{repo}/pulls/{n}", required=False))
                except GitHubError:     # rate limited: everything left is unknown
                    out[n] = None
    except Exception:
        pass
    return {n: out.get(n) for _, n in want}


def counts(runs: list[RunView], gh: dict[int, str | None]) -> dict[str, int]:
    prs = [v.pr.number for v in runs if v.pr and v.pr.url and v.pr.number]
    return {"started": len(runs),
            "analyzed": sum(v.outcome is not None for v in runs),
            "fix_proposed": sum(v.outcome in FIX for v in runs),
            "pr_opened": len(prs),
            "pr_merged": sum(gh.get(n) == "merged" for n in prs),
            "pr_status_unknown": sum(gh.get(n) is None for n in prs)}


def summary(runs: list[RunView], gh: dict[int, str | None]) -> dict:
    if not runs:
        return {"state": "empty", "counts": counts([], {}), "rows": []}
    rows = [{"run_id": v.run_id, "repo": v.issue.repo, "number": v.issue.number, "title": v.issue.title,
             "issue_url": v.issue.html_url, "created_at": v.created_at,
             "patchpilot": {"status": v.status, "outcome": v.outcome, "readiness": v.readiness,
                            "pr_url": v.pr.url if v.pr else None, "compare_url": v.pr.compare_url if v.pr else None},
             "github_pr_status": gh.get(v.pr.number) if v.pr and v.pr.number else None,
             "has_pr": bool(v.pr and v.pr.number)}
            for v in sorted(runs, key=lambda v: v.created_at, reverse=True)]
    c = counts(runs, gh)
    return {"state": "partial" if c["pr_status_unknown"] else "success", "counts": c, "rows": rows}
