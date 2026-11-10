"""B11 publisher: the ONLY code that uses a GitHub write token (contracts §5, architecture §3).
Re-checks everything, re-applies the approved diff on a clean checkout, then opens or updates ONE draft PR per run."""
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from urllib.parse import quote

from backend import artifacts
from backend.api import approval
from backend.api.approval import exact_diff, hashes
from backend.contracts.models import PublishBlocker, PullRequestRef, RunView

GIT_HOST = "https://github.com"   # tests point this at a local fixture repo
BOT_EMAIL = "patchpilot@users.noreply.github.com"
HEAD_MOVED = ("Someone else pushed to this pull request's branch since PatchPilot's last push, so we stopped instead of "
              "overwriting their commits. Nothing was published. Start a new run from the latest code if you still need it.")

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


def _changed(diff: str) -> list[str]:
    """`path` (+added −removed) per file, counted from the diff itself."""
    files: dict[str, list[int]] = {}
    cur, hunk = None, False
    for line in diff.splitlines():
        if line.startswith("diff --git "):   # same path rule as approval.changed_files (the Review screen's list)
            cur, hunk = (line.split(" b/", 1)[1].strip() if " b/" in line else None), False
            if cur:
                files[cur] = [0, 0]
        elif line.startswith("@@"):
            hunk = True
        elif cur and hunk and line[:1] in "+-":   # inside a hunk, so "----" or "+++x" are content, not headers
            files[cur][line[0] == "-"] += 1
    return [f"`{p}` (+{a} −{d})" for p, (a, d) in files.items()]


def _repo_checks(run_id: str) -> tuple[str, list[str]]:
    """(Tests sentence, limitation lines) from kv repo_checks:<run_id> (#70 item 3). Missing = "not checked", never passed."""
    from backend import db
    rows = (db.repo_checks(db.connect(), run_id) or {}).get("checks")   # malformed = "not checked", never a crash mid-publish
    if not rows:
        return "The repository's own linters and type checkers were not checked.", []
    ran = [f"{c['tool']} ({'no new problems' if c['status'] == 'PASS' else 'new problems'})" for c in rows if c["status"] in ("PASS", "FAIL")]
    other = [c["tool"] for c in rows if c["status"] not in ("PASS", "FAIL")]
    return (f"Repository checks run on the changed files: {', '.join(ran) or 'none'}.",
            [f"Not run here: {', '.join(other)}; please check {'them' if len(other) > 1 else 'it'} in CI."] if other else [])


COVERAGE_NOTE = "The test designer didn't claim"   # review.py's coverage concern: our own wording, not a maintainer's


def _clause(text: str) -> str:
    """'A CHANGELOG entry is added.' -> 'a CHANGELOG entry is added', for a '; '-joined list (live PR wheelgap#133: '.; ')."""
    t = text.strip().rstrip(".")
    return t[:1].lower() + t[1:] if t[:1].isupper() and not t[1:2].isupper() else t


def pr_body(v: RunView) -> str:
    """Problem / Cause / Fix / Tests / Limitations / AI as bold labels (#70 item 5). Short on purpose (mcstatus #1238 was
    closed as "too much vibe-coding"): no headings, no agent history; run details stay in the report."""
    a, base = v.approval, v.baseline
    tests = ", ".join(f"`{t}`" for t in (v.repro.test_ids if v.repro else [])) or "(not recorded)"
    problem = v.issue.title.strip()   # the reporter's words, which the user approved in the PR title; never model text
    fix = _changed(artifacts.get(v.patch.fix_diff_id).decode("utf-8", "replace")) if v.patch and artifacts.get(v.patch.fix_diff_id) else []
    checks, not_run = _repo_checks(v.run_id)
    existing = ((f" {len(base.pass_set)} existing tests passed before and still pass."
                 + (f" {len(base.fail_set)} were already failing before this change." if base.fail_set else "")) if base else "")
    sg = v.supplyguard
    deps = ("Dependency check (SupplyGuard): no known-malicious packages; "
            f"{sum(1 for f in sg.findings if f.get('type') == 'vulnerability')} known vulnerabilities listed."
            if sg and sg.status.value == "passed" else "Dependency check: see the PatchPilot report.")
    uncovered = v.repro.uncovered if v.repro else None
    # only a maintainer's own words count as "asked for"; an override or CONTRIBUTING is never claimed as a request
    asked = (f" A maintainer agreed to a pull request [on the issue]({v.consent.source_url})."
             if v.consent and v.consent.kind in ("maintainer_reply", "maintainer_request") and v.consent.source_url else "")
    lines = [
        f"Fixes #{v.issue.number}", "",
        f"**Problem:** {problem}{asked}", "",
        f"**Cause and fix:** {a.pr_summary.strip() or '(not given)'}", "",   # the summary the user edited and approved
        f"**Changes:** {', '.join(fix) if fix else '(not recorded)'}.", "",
        f"**Tests:** the new regression test {tests} fails 2/2 on the original code (`{v.base_sha[:7]}`) and passes 2/2 "
        f"with the fix in a fresh sandbox.{existing} {checks}", "",
        "**Limitations:** passing tests don't prove the change is bug-free; please review the logic. "
        + " ".join([*not_run, *([f"Not covered by the new tests: {'; '.join(_clause(u) for u in uncovered)}."] if uncovered else [])]), "",
        f"**AI assistance:** _{AI_NOTE}_", "",
        "<details><summary>More detail</summary>", "",
        f"- {deps}",
        *[f"- Reviewer note ({(c.get('level') or c.get('severity') or 'note').replace('_', ' ').lower()}): {c.get('text', '')}"
          for c in (v.review.concerns if v.review else [])   # the maintainer can tell a blocker from an accepted tradeoff
          if not str(c.get("text", "")).startswith(COVERAGE_NOTE)],   # already under Limitations, in plainer words
        f"- Base commit `{v.base_sha}`; PatchPilot run {v.run_id[:8]}, revision {v.revision}.", "",
        "</details>",
    ]
    return "\n".join(line.rstrip() for line in lines)


ASK_NOTE = "I used PatchPilot, an AI-assisted bug-fix tool, and reviewed the change myself before asking."


def ask_comment(v: RunView) -> str:
    """The default 'ask first' comment (mcstatus #1238 was closed unasked; the human decided 2026-11-09: comment first).
    The user edits it before it is posted."""
    summary = (v.approval.pr_summary.strip().split("\n\n")[0] if v.approval else "")[:600]
    kept = f" and the {len(v.baseline.pass_set)} existing tests still pass" if v.baseline else ""
    return (f"Hi! I looked into this and have a small fix ready. {summary}\n\n"
            f"It comes with a regression test that fails before the fix and passes after{kept}. "
            "Would you like a pull request for it? I'll only open one if you say yes.\n\n"
            f"_{ASK_NOTE}_")


def ask(v: RunView, gh, body: str) -> str:
    """Post the user's approved 'ask first' comment on the issue. Same pre-checks as a PR: it offers the approved fix."""
    preflight_checks(v, need_consent=False)
    return gh.comment(v.issue.repo, v.issue.number, body)["html_url"]


def compare_url(upstream: str, base_branch: str, owner: str, branch: str, title: str, body: str) -> str:
    return (f"https://github.com/{upstream}/compare/{base_branch}...{owner}:{quote(branch, safe='')}?expand=1"
            f"&title={quote(title)}&body={quote(body[:6000])}")


REAPPROVE = "Approve the change again and answer the three short questions in your own words (now required)."
NO_CONSENT = "No maintainer consent is recorded yet. Ask on the issue and record their reply, or type why you're publishing anyway."


def preflight_checks(v: RunView, *, need_consent: bool = True) -> str:
    """Everything that must still be true at publish time. Returns the canonical diff.
    need_consent=False only for the ask comment, which is how consent is obtained (contracts v0.5 §2.2)."""
    if v.approval is None or v.approval.revision != v.revision:
        raise PublishRefused("APPROVAL_STALE", "Approve the current version of the change before publishing.")
    if v.approval.ownership is None:   # approvals from before v0.5 (§2.3)
        raise PublishRefused("APPROVAL_STALE", REAPPROVE)
    diff = exact_diff(v)
    if (v.approval.diff_hash, v.approval.evidence_hash) != hashes(v, diff):
        raise PublishRefused("HASH_MISMATCH", "The change or its evidence changed after you approved it, so we stopped.")
    if need_consent and v.consent is None:   # also covers runs that finished before v0.5 and lack the blocker
        raise PublishRefused("PUBLISH_BLOCKED", NO_CONSENT)
    skip = (PublishBlocker.NOT_SIGNED_IN,) + (() if need_consent else (PublishBlocker.NO_MAINTAINER_CONSENT,))
    blocked = [b for b in v.publish_blockers if b not in skip]
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
        """POST /forks is idempotent and returns the fork's REAL full_name (GitHub may name it name-1 when the user
        already owns a same-named repo; C review #2). Forks are created async (202): wait until it's readable."""
        import time
        full = self.h.post(f"/repos/{repo}/forks").raise_for_status().json()["full_name"]
        for _ in range(30):
            r = self.h.get(f"/repos/{full}")
            if r.status_code == 200 and (r.json().get("parent") or {}).get("full_name", "").lower() == repo.lower():
                return full
            time.sleep(2)
        raise RuntimeError("fork not ready after 60 s")

    def find_pr(self, repo: str, head: str) -> dict | None:
        prs = self.h.get(f"/repos/{repo}/pulls", params={"head": head, "state": "open"}).raise_for_status().json()
        return prs[0] if prs else None

    def create_pr(self, repo: str, head: str, base: str, title: str, body: str) -> dict | None:
        r = self.h.post(f"/repos/{repo}/pulls", json={"head": head, "base": base, "title": title, "body": body, "draft": True})
        return r.json() if r.status_code == 201 else None    # 403/422: PRs restricted → branch_only

    def comment(self, repo: str, number: int, body: str) -> dict:
        return self.h.post(f"/repos/{repo}/issues/{number}/comments", json={"body": body}).raise_for_status().json()

    def update_pr(self, repo: str, number: int, title: str, body: str) -> dict:
        return self.h.patch(f"/repos/{repo}/pulls/{number}", json={"title": title, "body": body}).raise_for_status().json()

    def push_branch(self, target_repo: str, base_sha: str, upstream: str, branch: str, diff: str, message: str,
                    on_top: bool = False, expect_head: str | None = None) -> str:
        """Clean checkout at base_sha OUTSIDE the sandbox, apply the approved diff, push; returns the pushed commit.
        on_top (#103, the run already published this branch): the new commit's parent is the branch's current head and
        its files are exactly base + the approved diff, so the PR keeps its history. The head must be expect_head
        (the commit we last pushed) or, for runs published before head_sha was kept, made only of PatchPilot commits;
        otherwise PublishRefused("PR_HEAD_MOVED") and nothing is pushed.
        The token goes only into git's environment config, never argv (C review #5: process list, CalledProcessError)."""
        d = tempfile.mkdtemp(prefix="pp-pub-")
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.extraHeader",
               "GIT_CONFIG_VALUE_0": f"Authorization: Basic {_basic(self.token)}"}
        # bytes, not text=True: on Windows text-mode stdin turns the diff's LF into CRLF and `git apply` fails (first live publish)
        git = lambda *a, inp=None: subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *a], cwd=d,
                                                  input=inp.encode("utf-8") if inp is not None else None,
                                                  capture_output=True, check=True, env=env)
        try:
            git("init", "-q"); git("remote", "add", "origin", f"{GIT_HOST}/{target_repo}.git")
            git("fetch", "-q", "--depth", "1", f"{GIT_HOST}/{upstream}.git", base_sha)
            git("checkout", "-q", "-b", branch, "FETCH_HEAD")
            git("apply", "--index", "-", inp=diff)
            ident = ("-c", "user.name=PatchPilot", "-c", f"user.email={BOT_EMAIL}")
            # C review #3: lease against the branch's CURRENT remote sha ("" = must not exist yet), so re-publish after Revise works
            remote = git("ls-remote", "origin", f"refs/heads/{branch}").stdout.decode().split()
            head = remote[0] if remote else ""
            if on_top:
                if not head:
                    raise PublishRefused("PR_HEAD_MOVED", HEAD_MOVED)   # branch deleted: not ours to recreate silently
                # shortcut: with no recorded head, only the PR's last 100 commits are checked for other authors
                git("fetch", "-q", "--depth", "100", "origin", f"refs/heads/{branch}")
                authors = set(git("log", "--format=%ae", f"{base_sha}..{head}").stdout.decode().split())
                if (expect_head or head) != head or authors - {BOT_EMAIL}:
                    raise PublishRefused("PR_HEAD_MOVED", HEAD_MOVED)
                tree = git("write-tree").stdout.decode().strip()
                new = git(*ident, "commit-tree", tree, "-p", head, "-m", message).stdout.decode().strip()
            else:
                git(*ident, "commit", "-qm", message)
                new = git("rev-parse", "HEAD").stdout.decode().strip()
            git("push", "-q", f"--force-with-lease=refs/heads/{branch}:{head}", "origin", f"{new}:refs/heads/{branch}")
            return new
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
    # #103: once this run has pushed its branch, a revision is a new commit on top of it, never a rewrite
    sha = gh.push_branch(target, v.base_sha, v.issue.repo, branch, diff, f"{title}\n\nPrepared with PatchPilot (AI-assisted, human-approved).",
                         on_top=v.pr is not None, expect_head=v.pr.head_sha if v.pr else None)
    head = f"{owner}:{branch}"
    fork = None if target == v.issue.repo else owner
    link = compare_url(v.issue.repo, default_branch, owner, branch, title, body)
    ref = lambda pr: PullRequestRef(url=pr["html_url"], number=pr["number"], head_branch=branch, fork_owner=fork, state="open", head_sha=sha)
    try:
        if v.pr and v.pr.number:                            # #103: the run's own PR; never a second one
            return Result("updated", ref(gh.update_pr(v.issue.repo, v.pr.number, title, body)))
        existing = gh.find_pr(v.issue.repo, head)           # idempotent: one open PR per run
        if existing:
            return Result("updated", ref(gh.update_pr(v.issue.repo, existing["number"], title, body)))
        pr = gh.create_pr(v.issue.repo, head, default_branch, title, body)
    except Exception:
        pr = None   # C review #4: the branch IS pushed; never claim "nothing was published"
    if pr is None:
        if v.pr and v.pr.number:                            # pushed, but the body update failed: still the same PR
            return Result("branch_only", v.pr.model_copy(update={"head_sha": sha}))
        return Result("branch_only", PullRequestRef(head_branch=branch, fork_owner=fork, compare_url=link, head_sha=sha))
    return Result("created", ref(pr))
