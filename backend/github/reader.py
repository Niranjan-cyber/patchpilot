"""Read-only GitHub reader for the issue check (B03 / G0). Parsers are pure and tested on fixtures/github/."""
import base64
import os
import re
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel

from backend.contracts.models import CheckStatus, IssueAssessment, IssueSpec, RepoPolicy

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
    warnings: list[str] = []          # codes the user must accept via continue_despite: closed, assigned, linked_pr, already_fixed, prs_collaborators_only, lookup_failed, unclear_type, needs_info
    unsupported: str | None = None    # reason nothing can execute (v0.4: an ASSESSMENT_ONLY run, not an error)
    assessment: IssueAssessment | None = None   # #48 intake assessment, decided by code
    fetched_at: datetime
    suitability: list[dict] | None = None       # #70 item 7: per-dimension outcome + evidence (backend/github/suitability.py)
    # #70 item 3/4.3: what was checked for existing work, where, and when. Each source is "checked" or "failed" (unknown,
    # never "none found"). Stored at run start and compared again at publish (approval.stale_checks).
    existing_work: dict | None = None


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
    grab = lambda k: (m.group(1).strip()[:300] if (m := re.search(rf"(?im)^\W*{k}[^:\n]*:[\s*]*(.+)$", body or "")) else None)
    return grab("expected"), grab("actual")


def linked_open_prs(timeline: list[dict]) -> list[int]:
    out = []
    for e in timeline:
        src = (e.get("source") or {}).get("issue") or {}
        if e.get("event") == "cross-referenced" and "pull_request" in src and src.get("state") == "open":
            out.append(src.get("number"))
    return out


def merged_prs(timeline, closed, found, repo: str, num: int) -> list[int]:
    """Merged PRs that fixed this issue: a merged timeline cross-reference, or a merged PR (recent closed list or the
    search API) whose title/body really references #num. The timeline alone isn't enough: with a fine-grained read token
    it can come back empty (pyparsing#702), and more-itertools#1268 stayed open after its fix (#1294) merged."""
    out = {(e.get("source") or {}).get("issue", {}).get("number") for e in timeline if isinstance(e, dict)
           and e.get("event") == "cross-referenced"
           and ((e.get("source") or {}).get("issue") or {}).get("pull_request", {}).get("merged_at")} if isinstance(timeline, list) else set()
    merged = [p for p in closed if isinstance(p, dict) and p.get("merged_at")] if isinstance(closed, list) else []
    merged += [{**p, "merged_at": (p.get("pull_request") or {}).get("merged_at")} for p in found if isinstance(p, dict)
               and (p.get("pull_request") or {}).get("merged_at")] if isinstance(found, list) else []
    out |= set(mentioning_open_prs(merged, repo, num, "", title_words=False))   # a real reference only, never title words
    return sorted(n for n in out if isinstance(n, int))


_STOP = {"with", "when", "that", "this", "from", "into", "should", "does", "doesn", "fixes", "issue", "error", "errors",
         "returns", "return", "instead", "using", "support", "allow", "make", "makes", "properly", "correctly", "after",
         "before", "about", "where", "which", "their", "there", "while"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9_]+", (text or "").lower()) if len(w) >= 4 and w not in _STOP}


# code names in an issue title: `merge_tree()`, intword: …, jwt.decode(, max_rounds (humanize#356 vs open #475)
CODE_ID = re.compile(r"`([A-Za-z_][\w.]*)|\b([A-Za-z_][\w.]*)\(|^\W*([A-Za-z_][\w.]*):|\b([a-z]+_[a-z0-9_]+)\b")


def _code_ids(title: str) -> set[str]:
    return {x.lower().rstrip(".") for m in CODE_ID.finditer(title or "") for x in m.groups() if x and len(x) >= 4}


def commented_open_prs(comments, pulls) -> list[int]:
    """Open PRs a commenter points to ("#2510 is already open", pip-tools#2509): the PR itself may never name the issue.
    Quoted lines don't count. Only numbers that ARE open PRs here, so an issue reference ("dup of #17") never matches."""
    open_ = {p["number"] for p in pulls if isinstance(p, dict) and isinstance(p.get("number"), int)} if isinstance(pulls, list) else set()
    refs = set()
    for cm in comments if isinstance(comments, list) else []:
        text = "\n".join(l for l in ((cm or {}).get("body") or "").splitlines() if not l.lstrip().startswith(">"))
        refs |= {int(n) for n in re.findall(r"(?<![\w/&])#(\d+)\b", text)}
    return sorted(refs & open_)


def mentioning_open_prs(pulls: list, repo: str, num: int, title: str, *, title_words: bool = True) -> list[int]:
    """Open PRs that likely fix this issue without a timeline cross-reference (A's P1, 2026-11-08: python-dotenv #715,
    jmespath #381). A hit is only the overridable linked_pr warning ("lookups can be wrong"), never a block.
    shortcut: the newest 100 open PRs and a 2-shared-title-words rule; upgrade to the search API if it misses real cases."""
    ref = re.compile(rf"(?<![\w/])#{num}\b|{re.escape(repo)}/issues/{num}\b", re.I)
    want, ids, out = _words(title), _code_ids(title), []
    for p in pulls if isinstance(pulls, list) else []:
        if not isinstance(p, dict) or not isinstance(p.get("number"), int):
            continue
        text = f"{p.get('title') or ''}\n{p.get('body') or ''}"
        pt = (p.get("title") or "").lower()
        if ref.search(text) or (title_words and (len(want & _words(pt)) >= 2 or any(re.search(rf"(?<![\w.]){re.escape(x)}(?![\w])", pt) for x in ids))):
            out.append(p["number"])
    return sorted(out)


CLAIM = re.compile(r"""(?ix)
  \b(?:i'?ll|i\ will|i'?d\ like\ to|i\ want\ to|let\ me|i\ can|i'?m\ going\ to)\ (?:take|pick\ up|grab|work\ on|fix)\ (?:this|it|that)\b
| \bi'?m\ (?:already\ )?(?:working\ on|on)\ (?:this|it|a\ fix|a\ pr)\b
| \b(?:i'?ll|i\ will|i\ can|happy\ to|glad\ to|i'?d\ (?:be\ happy|love|like)\ to)\ (?:send|open|submit|make|create|put\ up)\ (?:a\ |the\ )?(?:pr|pull\ request|fix|patch)\b
| \b(?:can|could|may)\ i\ (?:take|work\ on|pick\ up|grab)\ (?:this|it)\b
| \bassign\ (?:this\ |it\ |the\ issue\ )?to\ me\b
""")


def claimed_by(comments: list) -> list[str]:
    """Commenters who said they'll fix it or send a PR (msoffcrypto #109 was closed: the reporter had offered to send one).
    Folded into the overridable `assigned` warning. Quoted lines don't count.
    shortcut: the first 100 comments and an English phrase list; upgrade if real claims slip through."""
    out = []
    for cm in comments if isinstance(comments, list) else []:
        if not isinstance(cm, dict):
            continue
        text = "\n".join(l for l in (cm.get("body") or "").replace("’", "'").splitlines() if not l.lstrip().startswith(">"))
        who = (cm.get("user") or {}).get("login") or "someone"
        if CLAIM.search(text) and who not in out:
            out.append(who)
    return out


def detect(root_names: list[str], language: str | None) -> tuple[bool, bool]:
    names = {n.lower() for n in root_names}
    python = language == "Python" or bool(names & {n.lower() for n in PY_FILES})
    tests = bool(names & TEST_MARKERS) or any(re.match(r"test_.*\.py$|.*_test\.py$", n) for n in names)
    return python, tests


def tests_in_tree(tree: dict | None) -> bool | None:
    """Tests anywhere in the repo (a recursive git tree), for repos that keep them inside the package. None = unknown."""
    if not isinstance(tree, dict) or not isinstance(tree.get("tree"), list) or tree.get("truncated"):
        return None
    test_file = re.compile(r"(^|/)(tests?|testing)/.+\.py$|(^|/)test_[^/]*\.py$|_test\.py$")
    return any(test_file.search(e.get("path", "")) for e in tree["tree"] if isinstance(e, dict))


def ai_policy(texts: list[str]) -> str:
    blob = "\n".join(texts)
    if FORBID.search(blob):
        return "forbidden"
    if ALLOW.search(blob):
        return "allowed"
    return "unknown"


def g0_status(checks: dict[str, CheckStatus], accepted: list[str] = ()) -> tuple[CheckStatus, str]:
    """G0 for the run's gates (contracts §1.1): a failed check the user accepted = failed, a failed lookup = inconclusive.
    accepted = warning codes the user sent in continue_despite; v0.4's assessment warnings count as accepted failures."""
    failed = [code for key, code in (("open", "closed"), ("unassigned", "assigned"), ("no_linked_pr", "linked_pr"))
              if checks.get(key) == CheckStatus.FAILED]
    failed += [w for w in ("unclear_type", "needs_info", "other_os", "base_unknown") if w in accepted]
    if failed:
        return CheckStatus.FAILED, failed[0]
    if any(s == CheckStatus.INCONCLUSIVE for s in checks.values()):
        return CheckStatus.INCONCLUSIVE, "lookup_failed"
    return CheckStatus.PASSED, "eligible"


def _client() -> httpx.Client:
    tok = os.getenv("GITHUB_READ_TOKEN")
    # follow_redirects: a renamed repo answers 301 (sdispater/pendulum → python-pendulum/pendulum)
    return httpx.Client(base_url=GH, timeout=10, follow_redirects=True, headers={"Accept": "application/vnd.github+json",
                        **({"Authorization": f"Bearer {tok}"} if tok else {})})


def _get(h: httpx.Client, path: str, *, required: bool = True):
    try:
        r = h.get(path)
    except httpx.HTTPError:
        if required:
            raise GitHubError("GITHUB_UNAVAILABLE", "GitHub didn't answer. Try again in a minute.", 60)
        return None
    return _check(r, required=required)


def _check(r: httpx.Response, *, required: bool = True):
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


def check_issue(url: str, *, extract_model: bool = True) -> IssueCheck:
    """extract_model=False: callers that only need repo facts (approval's stale check, publisher) skip the assessor call."""
    repo, num = parse_url(url)
    warnings: list[str] = []
    with _client() as h:
        issue = _get(h, f"/repos/{repo}/issues/{num}")
        if issue.get("pull_request"):
            raise GitHubError("NOT_AN_ISSUE", "That's a pull request link. Paste the issue it fixes instead.")
        if (moved := (issue.get("repository_url") or "").removeprefix(f"{GH}/repos/")).count("/") == 1:
            repo = moved   # renamed repo: use its current name from here on (sandbox clone, publisher, links)
        meta = _get(h, f"/repos/{repo}")
        if meta.get("private"):
            raise GitHubError("PRIVATE_REPO", "This repository is private; PatchPilot only reads public repositories.")
        branch = meta.get("default_branch")
        head = _get(h, f"/repos/{repo}/commits/{branch}", required=False)
        root = _get(h, f"/repos/{repo}/contents/", required=False)
        root_tests = detect([x["name"] for x in root] if isinstance(root, list) else [], None)[1]
        # no tests at the top level: look inside the package before calling the repo unsupported (G2 checks for real)
        tree = None if root_tests else _get(h, f"/repos/{repo}/git/trees/{branch}?recursive=1", required=False)
        timeline = _get(h, f"/repos/{repo}/issues/{num}/timeline?per_page=100", required=False)
        pulls = _get(h, f"/repos/{repo}/pulls?state=open&per_page=100", required=False)
        comments = _get(h, f"/repos/{repo}/issues/{num}/comments?per_page=100", required=False) if issue.get("comments") else []
        closed = _get(h, f"/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=50", required=False)
        # merged PRs older than the 50 most recent closed ones: the search API finds them by number (filtered below)
        found = (_get(h, f"/search/issues?q=repo:{repo}+is:pr+is:merged+{num}&per_page=20", required=False) or {}).get("items")
        community = _get(h, f"/repos/{repo}/community/profile", required=False)
        docs = []
        for path in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "AI_POLICY.md", ".github/AI_POLICY.md", "README.md"):
            f = _get(h, f"/repos/{repo}/contents/{path}", required=False)
            if f and f.get("content"):
                docs.append((path, base64.b64decode(f["content"]).decode("utf-8", "replace")))
    names = [x["name"] for x in root] if isinstance(root, list) else []
    python, tests = detect(names, meta.get("language"))
    deep = None if tests else tests_in_tree(tree)
    tests = tests or bool(deep)
    title = issue.get("title") or ""
    # timeline cross-references + open PRs that name the issue or share its title (cross-references can be missing)
    found = (set(linked_open_prs(timeline) if isinstance(timeline, list) else []) | set(mentioning_open_prs(pulls, repo, num, title))
             | set(commented_open_prs(comments, pulls)))
    linked = sorted(found) if found or isinstance(timeline, list) else None   # nothing found and no timeline = unknown
    exp, act = expected_actual(issue.get("body") or "")
    lookup = lambda ok_val, known: CheckStatus.PASSED if (known and ok_val) else (CheckStatus.FAILED if known else CheckStatus.INCONCLUSIVE)
    checks = {
        "open": lookup(issue.get("state") == "open", True),
        "public": CheckStatus.PASSED,
        "python": lookup(python, root is not None or meta.get("language") is not None),
        "tests_found": lookup(tests, root is not None and (tests or deep is not None)),
        # an open claim in the comments counts like an assignee; unreadable comments = unknown, unless someone is assigned
        "unassigned": lookup(not issue.get("assignees") and not claimed_by(comments), bool(issue.get("assignees")) or comments is not None),
        "no_linked_pr": lookup(not linked, linked is not None),
    }
    for code, key in (("closed", "open"), ("assigned", "unassigned"), ("linked_pr", "no_linked_pr")):
        if checks[key] == CheckStatus.FAILED:
            warnings.append(code)
    if merged_prs(timeline, closed, found, repo, num):
        warnings.append("already_fixed")   # v0.10: a merged PR references it; it may just not have been closed
    if meta.get("pull_request_creation_policy") == "collaborators_only":
        warnings.append("prs_collaborators_only")   # v0.10: only collaborators may open PRs (jsonschema, pallets)
    if any(v == CheckStatus.INCONCLUSIVE for v in checks.values()):
        warnings.append("lookup_failed")
    unsupported = ("not_python" if checks["python"] == CheckStatus.FAILED else
                   "no_tests" if checks["tests_found"] == CheckStatus.FAILED else None)
    policy = RepoPolicy(ai_policy=ai_policy([t for _, t in docs]),
                        source_evidence_ids=[p for p, _ in docs])   # shortcut: file paths, not artifact IDs, until B09's store is used here
    spec = IssueSpec(html_url=f"https://github.com/{repo}/issues/{num}", repo=repo, number=num, title=issue.get("title") or "",
                     # the agents read this: 600 chars cut the repro code off (#389); the UI never renders it
                     summary=(issue.get("body") or "").strip()[:4000] or None, expected=exp, actual=act,
                     labels=[l["name"] for l in issue.get("labels", [])], checks=checks)
    _ = community   # CONTRIBUTING may live elsewhere; the profile only says whether it exists
    from backend.github.assess import assess, extract, new_warnings   # late: assess imports explore, which imports this module
    body = issue.get("body") or ""
    x = None if unsupported or not extract_model else extract(url=spec.html_url, updated_at=issue.get("updated_at"), title=spec.title, body=body,
                                         labels=spec.labels)   # nothing will run for an unsupported repo: don't spend tokens
    a = assess(title=spec.title, body=body, labels=spec.labels, names=names, state=issue.get("state") or "open",
               checks=checks, unsupported=unsupported, warnings=warnings, linked=linked, extracted=x,
               base_sha=(head or {}).get("sha"), forbids_ai=policy.ai_policy == "forbidden")
    warnings += [w for w in new_warnings(a) if w not in warnings]
    now = datetime.now(timezone.utc)
    # a merged PR hard-blocks publishing, so only a real reference counts, never the 2-title-words guess
    hit = set(mentioning_open_prs(closed, repo, num, title, title_words=False)) if isinstance(closed, list) else set()
    work = {"checked_at": now.isoformat(),
            "sources": {k: "checked" if ok else "failed" for k, ok in (("timeline", isinstance(timeline, list)),
                        ("open_prs", isinstance(pulls, list)), ("comments", comments is not None), ("closed_prs", isinstance(closed, list)))},
            "linked_prs": linked, "assignees": [u.get("login") for u in issue.get("assignees") or [] if isinstance(u, dict)],
            "claimants": claimed_by(comments) if comments is not None else None,
            # shortcut: the 50 most recently updated closed PRs; enough for "fixed while you worked", not a full history
            "closed_prs": [{"number": p["number"], "merged_at": p.get("merged_at"), "closed_at": p.get("closed_at")}
                           for p in closed if isinstance(p, dict) and p.get("number") in hit] if isinstance(closed, list) else None}
    dims = None
    if extract_model:   # approval's stale check and the publisher only need repo facts, not the explanation
        try:   # an explanation panel must never fail G0, approve or publish: a crash here is "not checked"
            from backend.github.suitability import dimensions
            dims = dimensions(a=a, issue=issue, comments=comments if isinstance(comments, list) else None, checks=checks,
                              expected=exp, actual=act, unsupported=unsupported, ai_policy=policy.ai_policy)
        except Exception:
            dims = None
    return IssueCheck(suitability=dims, issue=spec, base_sha=(head or {}).get("sha"), default_branch=branch,
                      language=meta.get("language"), policy=policy, warnings=warnings, unsupported=unsupported, assessment=a,
                      fetched_at=now, existing_work=work)
