"""Read-only GitHub reader for the issue check (B03 / G0). Parsers are pure and tested on fixtures/github/."""
import base64
import os
import re
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel

from backend.contracts.models import CheckStatus, IssueSpec, RepoPolicy

GH = "https://api.github.com"
ISSUE_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/(issues|pull)/(\d+)/?(?:[#?].*)?$")
PY_FILES = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"}
TEST_MARKERS = {"tests", "test", "testing", "pytest.ini", "tox.ini", "conftest.py", "noxfile.py"}
AI_WORDS = r"(?:ai|a\.i\.|llm|chatgpt|copilot|generative|machine[- ]generated|ai[- ]generated|ai[- ]assisted)"
FORBID = re.compile(rf"(?:do not|don't|will not|won't|not|never)\s+(?:accept|allow|permit|merge)[^.\n]{{0,80}}{AI_WORDS}|"
                    rf"{AI_WORDS}[^.\n]{{0,60}}(?:prohibited|forbidden|not (?:allowed|accepted|permitted)|banned|will be closed|are rejected)",
                    re.I)
ALLOW = re.compile(rf"{AI_WORDS}[^.\n]{{0,80}}(?:allowed|welcome|permitted|must be disclosed|disclose)|disclose[^.\n]{{0,60}}{AI_WORDS}", re.I)


class GitHubError(Exception):
    def __init__(self, code: str, message: str, retry_after: int | None = None):
        super().__init__(message); self.code, self.retry_after = code, retry_after


class IssueCheck(BaseModel):
    issue: IssueSpec
    base_sha: str | None
    default_branch: str | None
    language: str | None
    policy: RepoPolicy
    warnings: list[str] = []          # codes the user must accept via continue_despite: closed, assigned, linked_pr, lookup_failed
    unsupported: str | None = None    # reason no run can be created
    fetched_at: datetime


def parse_url(url: str) -> tuple[str, int]:
    m = ISSUE_URL.match(url.strip())
    if not m:
        raise GitHubError("INVALID_URL", "Paste a link to a GitHub issue, like https://github.com/owner/repo/issues/123.")
    owner, repo, kind, num = m.groups()
    if kind == "pull":
        raise GitHubError("NOT_AN_ISSUE", "That's a pull request link. Paste the issue it fixes instead.")
    return f"{owner}/{repo}", int(num)


def expected_actual(body: str) -> tuple[str | None, str | None]:
    """Rule-based: lines starting 'Expected' / 'Actual' (common issue templates). None when not stated."""
    grab = lambda k: (m.group(1).strip()[:300] if (m := re.search(rf"(?im)^\W*{k}[^:\n]*:\s*(.+)$", body or "")) else None)
    return grab("expected"), grab("actual")


def linked_open_prs(timeline: list[dict]) -> list[int]:
    out = []
    for e in timeline:
        src = (e.get("source") or {}).get("issue") or {}
        if e.get("event") == "cross-referenced" and "pull_request" in src and src.get("state") == "open":
            out.append(src.get("number"))
    return out


def detect(root_names: list[str], language: str | None) -> tuple[bool, bool]:
    names = {n.lower() for n in root_names}
    python = language == "Python" or bool(names & {n.lower() for n in PY_FILES})
    tests = bool(names & TEST_MARKERS) or any(re.match(r"test_.*\.py$|.*_test\.py$", n) for n in names)
    return python, tests


def ai_policy(texts: list[str]) -> str:
    blob = "\n".join(texts)
    if FORBID.search(blob):
        return "forbidden"
    if ALLOW.search(blob):
        return "allowed"
    return "unknown"


def _client() -> httpx.Client:
    tok = os.getenv("GITHUB_READ_TOKEN")
    return httpx.Client(base_url=GH, timeout=10, headers={"Accept": "application/vnd.github+json",
                        **({"Authorization": f"Bearer {tok}"} if tok else {})})


def _get(h: httpx.Client, path: str, *, required: bool = True):
    try:
        r = h.get(path)
    except httpx.HTTPError:
        if required:
            raise GitHubError("GITHUB_UNAVAILABLE", "GitHub didn't answer. Try again in a minute.", 60)
        return None
    if r.status_code in (403, 429) and ("rate limit" in r.text.lower() or r.status_code == 429):
        reset = r.headers.get("retry-after") or r.headers.get("x-ratelimit-reset")
        wait = int(reset) - int(datetime.now(timezone.utc).timestamp()) if reset and int(reset) > 10**9 else int(reset or 60)
        raise GitHubError("GITHUB_UNAVAILABLE", f"GitHub is rate-limiting us. Try again in {max(wait, 1) // 60 + 1} min.", max(wait, 1))
    if r.status_code == 404 and required:
        raise GitHubError("PRIVATE_REPO", "We can't see that issue. The repository may be private or the issue may not exist.")
    if r.status_code >= 400:
        if required:
            raise GitHubError("GITHUB_UNAVAILABLE", f"GitHub returned an error ({r.status_code}). Try again shortly.", 60)
        return None
    return r.json()


def check_issue(url: str) -> IssueCheck:
    repo, num = parse_url(url)
    warnings: list[str] = []
    with _client() as h:
        issue = _get(h, f"/repos/{repo}/issues/{num}")
        if issue.get("pull_request"):
            raise GitHubError("NOT_AN_ISSUE", "That's a pull request link. Paste the issue it fixes instead.")
        meta = _get(h, f"/repos/{repo}")
        if meta.get("private"):
            raise GitHubError("PRIVATE_REPO", "This repository is private; PatchPilot only reads public repositories.")
        branch = meta.get("default_branch")
        head = _get(h, f"/repos/{repo}/commits/{branch}", required=False)
        root = _get(h, f"/repos/{repo}/contents/", required=False)
        timeline = _get(h, f"/repos/{repo}/issues/{num}/timeline?per_page=100", required=False)
        community = _get(h, f"/repos/{repo}/community/profile", required=False)
        docs = []
        for path in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "AI_POLICY.md", ".github/AI_POLICY.md", "README.md"):
            f = _get(h, f"/repos/{repo}/contents/{path}", required=False)
            if f and f.get("content"):
                docs.append((path, base64.b64decode(f["content"]).decode("utf-8", "replace")))
    names = [x["name"] for x in root] if isinstance(root, list) else []
    python, tests = detect(names, meta.get("language"))
    linked = linked_open_prs(timeline) if isinstance(timeline, list) else None
    exp, act = expected_actual(issue.get("body") or "")
    lookup = lambda ok_val, known: CheckStatus.PASSED if (known and ok_val) else (CheckStatus.FAILED if known else CheckStatus.INCONCLUSIVE)
    checks = {
        "open": lookup(issue.get("state") == "open", True),
        "public": CheckStatus.PASSED,
        "python": lookup(python, root is not None or meta.get("language") is not None),
        "tests_found": lookup(tests, root is not None),
        "unassigned": lookup(not issue.get("assignees"), True),
        "no_linked_pr": lookup(not linked, linked is not None),
    }
    for code, key in (("closed", "open"), ("assigned", "unassigned"), ("linked_pr", "no_linked_pr")):
        if checks[key] == CheckStatus.FAILED:
            warnings.append(code)
    if any(v == CheckStatus.INCONCLUSIVE for v in checks.values()):
        warnings.append("lookup_failed")
    unsupported = ("not_python" if checks["python"] == CheckStatus.FAILED else
                   "no_tests" if checks["tests_found"] == CheckStatus.FAILED else None)
    policy = RepoPolicy(ai_policy=ai_policy([t for _, t in docs]),
                        source_evidence_ids=[p for p, _ in docs])   # shortcut: file paths, not artifact IDs, until B09's store is used here
    spec = IssueSpec(html_url=f"https://github.com/{repo}/issues/{num}", repo=repo, number=num, title=issue.get("title") or "",
                     summary=(issue.get("body") or "").strip()[:600] or None, expected=exp, actual=act,
                     labels=[l["name"] for l in issue.get("labels", [])], checks=checks)
    _ = community   # CONTRIBUTING may live elsewhere; the profile only says whether it exists
    return IssueCheck(issue=spec, base_sha=(head or {}).get("sha"), default_branch=branch, language=meta.get("language"),
                      policy=policy, warnings=warnings, unsupported=unsupported, fetched_at=datetime.now(timezone.utc))
