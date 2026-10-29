"""B11 publisher: the ONLY code that uses a GitHub write token (contracts §5, architecture §3).
Re-checks everything, re-applies the approved diff on a clean checkout, then opens or updates ONE draft PR per run."""
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from urllib.parse import quote

from backend.api import approval
from backend.api.approval import exact_diff, hashes
from backend.contracts.models import PublishBlocker, PullRequestRef, RunView

AI_NOTE = ("This pull request was prepared with PatchPilot, an AI-assisted bug-fix tool. A human reviewed and approved "
           "this exact diff before it was opened. Please review it like any other contribution.")


class PublishRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message); self.code = code


@dataclass
class Result:
    status: str                    # created | updated | branch_only
    pr: PullRequestRef


def branch_name(v: RunView) -> str:
    return f"patchpilot/issue-{v.issue.number}-{v.run_id[:8]}"


def pr_body(v: RunView) -> str:
    a, base = v.approval, v.baseline
    tests = ", ".join(f"`{t}`" for t in (v.repro.test_ids if v.repro else []))
    sg = v.supplyguard
    deps = ("Dependency check (SupplyGuard): no known-malicious packages; "
            f"{sum(1 for f in sg.findings if f.get('type') == 'vulnerability')} known vulnerabilities listed."
            if sg and sg.status.value == "passed" else "Dependency check: see the PatchPilot report.")
    concerns = [c.get("text", "") for c in (v.review.concerns if v.review else [])]
    lines = [
        f"Fixes #{v.issue.number}", "",
        "## Summary", a.pr_summary.strip() or "(no summary)", "",
        "## Evidence",
        f"- New regression test {tests} **fails 2/2 on the original code** (`{v.base_sha[:7]}`) and **passes 2/2 after the fix in a fresh sandbox**.",
        (f"- {len(base.pass_set)} existing tests passed before and still pass."
         + (f" {len(base.fail_set)} were already failing before this change (unrelated)." if base.fail_set else "")) if base else "- Existing tests: not recorded.",
        f"- {deps}", "",
        "## Limitations",
        "- Passing tests don't prove the change is bug-free; please review the logic.",
        *([f"- Reviewer note: {c}" for c in concerns] or []), "",
        "## AI assistance", AI_NOTE, "",
        f"<sub>Base commit {v.base_sha}. PatchPilot run {v.run_id[:8]}, revision {v.revision}.</sub>",
    ]
    return "\n".join(lines)


def compare_url(upstream: str, base_branch: str, owner: str, branch: str, title: str, body: str) -> str:
    return (f"https://github.com/{upstream}/compare/{base_branch}...{owner}:{quote(branch, safe='')}?expand=1"
            f"&title={quote(title)}&body={quote(body[:6000])}")


def preflight_checks(v: RunView) -> str:
    """Everything that must still be true at publish time. Returns the canonical diff."""
    if v.approval is None or v.approval.revision != v.revision:
        raise PublishRefused("APPROVAL_STALE", "Approve the current version of the change before publishing.")
    diff = exact_diff(v)
    if (v.approval.diff_hash, v.approval.evidence_hash) != hashes(v, diff):
        raise PublishRefused("HASH_MISMATCH", "The change or its evidence changed after you approved it, so we stopped.")
    blocked = [b for b in v.publish_blockers if b not in (PublishBlocker.NOT_SIGNED_IN,)]
    if blocked:
        raise PublishRefused("PUBLISH_BLOCKED", "Publishing is blocked: " + ", ".join(b.value for b in blocked))
    new = approval.stale_checks(v, diff)
    if new:
        raise PublishRefused("UPSTREAM_CHANGED" if PublishBlocker.UPSTREAM_CHANGED in new else "APPROVAL_STALE",
                             "Something changed upstream since you approved. Re-run on the latest code.")
    return diff


class GitHubWriter:
    """Thin wrapper over the GitHub REST API with the user's OAuth token. Tests use a fake with the same methods."""
    def __init__(self, token: str):
        import httpx
        self.token = token
        self.h = httpx.Client(base_url="https://api.github.com", timeout=20,
                              headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})

    def login(self) -> str:
        return self.h.get("/user").raise_for_status().json()["login"]

    def can_push(self, repo: str) -> bool:
        return bool(self.h.get(f"/repos/{repo}").raise_for_status().json().get("permissions", {}).get("push"))

    def ensure_fork(self, repo: str, login: str) -> str:
        name = repo.split("/")[1]
        r = self.h.get(f"/repos/{login}/{name}")
        if r.status_code == 200 and r.json().get("fork"):
            return f"{login}/{name}"
        self.h.post(f"/repos/{repo}/forks").raise_for_status()
        return f"{login}/{name}"

    def find_pr(self, repo: str, head: str) -> dict | None:
        prs = self.h.get(f"/repos/{repo}/pulls", params={"head": head, "state": "all"}).raise_for_status().json()
        return prs[0] if prs else None

    def create_pr(self, repo: str, head: str, base: str, title: str, body: str) -> dict | None:
        r = self.h.post(f"/repos/{repo}/pulls", json={"head": head, "base": base, "title": title, "body": body, "draft": True})
        return r.json() if r.status_code == 201 else None    # 403/422: PRs restricted → branch_only

    def update_pr(self, repo: str, number: int, title: str, body: str) -> dict:
        return self.h.patch(f"/repos/{repo}/pulls/{number}", json={"title": title, "body": body}).raise_for_status().json()

    def push_branch(self, target_repo: str, base_sha: str, upstream: str, branch: str, diff: str, message: str) -> None:
        """Clean checkout at base_sha OUTSIDE the sandbox, apply the approved diff, push. Token only in an auth header."""
        d = tempfile.mkdtemp(prefix="pp-pub-")
        auth = ["-c", f"http.extraHeader=Authorization: Basic {_basic(self.token)}"]
        git = lambda *a, inp=None: subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *a], cwd=d, input=inp, text=True,
                                                  capture_output=True, check=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        try:
            git("init", "-q"); git("remote", "add", "origin", f"https://github.com/{target_repo}.git")
            git(*auth, "fetch", "-q", "--depth", "1", f"https://github.com/{upstream}.git", base_sha)
            git("checkout", "-q", "-b", branch, "FETCH_HEAD")
            git("apply", "--index", "-", inp=diff)
            git("-c", "user.name=PatchPilot", "-c", "user.email=patchpilot@users.noreply.github.com", "commit", "-qm", message)
            git(*auth, "push", "-q", "--force-with-lease", "origin", f"HEAD:refs/heads/{branch}")
        finally:
            shutil.rmtree(d, ignore_errors=True)


def _basic(token: str) -> str:
    import base64
    return base64.b64encode(f"x-access-token:{token}".encode()).decode()


def publish(v: RunView, gh, default_branch: str) -> Result:
    diff = preflight_checks(v)
    login = gh.login()
    target = v.issue.repo if gh.can_push(v.issue.repo) else gh.ensure_fork(v.issue.repo, login)
    owner, branch = target.split("/")[0], branch_name(v)
    title, body = v.approval.pr_title, pr_body(v)
    gh.push_branch(target, v.base_sha, v.issue.repo, branch, diff, f"{title}\n\nPrepared with PatchPilot (AI-assisted, human-approved).")
    head = f"{owner}:{branch}"
    fork = None if target == v.issue.repo else owner
    existing = gh.find_pr(v.issue.repo, head)           # idempotent: one PR per run
    if existing:
        pr = gh.update_pr(v.issue.repo, existing["number"], title, body)
        return Result("updated", PullRequestRef(url=pr["html_url"], number=pr["number"], head_branch=branch, fork_owner=fork, state="open"))
    pr = gh.create_pr(v.issue.repo, head, default_branch, title, body)
    if pr is None:
        return Result("branch_only", PullRequestRef(head_branch=branch, fork_owner=fork,
                                                    compare_url=compare_url(v.issue.repo, default_branch, owner, branch, title, body)))
    return Result("created", PullRequestRef(url=pr["html_url"], number=pr["number"], head_branch=branch, fork_owner=fork, state="open"))
