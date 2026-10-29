"""B18 Explore one repo (S-09): shortlist 3-5 open issues PatchPilot can likely run, ranked by runnable signals, not labels."""
import re

from backend.github.reader import GitHubError, _client, _get, detect, expected_actual, linked_open_prs

REPO_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?(?:[?#].*)?$")
LOCKS = {"requirements.txt", "poetry.lock", "pipfile.lock", "uv.lock"}     # files SupplyGuard can read
RECIPE = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "pipfile", "tox.ini", "noxfile.py"}
ERROR = re.compile(r"Traceback \(most recent call last\)|\b\w+(?:Error|Exception)\b|\braises?\b|\bcrash", re.I)
BUGGY = re.compile(r"\b(?:wrong|incorrect|fails?|failing|broken|bug|unexpected(?:ly)?|instead of|regression)\b", re.I)
NOT_RUNNABLE = re.compile(r"\b(?:document(?:ation)?|docs?|feature request|add support|would be nice|proposal|typo|"
                          r"question|discussion|rfc)\b", re.I)
OTHER_OS = re.compile(r"\b(?:on windows|windows only|winerror|cmd\.exe|powershell|on macos|macos only|on mac\b|darwin)\b", re.I)
STEPS = re.compile(r"(?im)^\W*(?:steps to reproduce|to reproduce|reproduc\w*|minimal example|mcve)\b")
MAX_SUGGESTIONS, CANDIDATES = 5, 8


def parse_repo_url(url: str) -> str:
    """Only https://github.com/<owner>/<repo>[/...] (SSRF: we never fetch other hosts)."""
    m = REPO_URL.match(url.strip())
    if not m or m.group(2) in (".", ".."):
        raise GitHubError("INVALID_URL", "Paste a link to a GitHub repository, like https://github.com/owner/repo.")
    return f"{m.group(1)}/{m.group(2)}"


def score_issue(i: dict) -> dict:
    body, title = i.get("body") or "", i.get("title") or ""
    text = f"{title}\n{body}"
    exp, act = expected_actual(body)
    sig, reasons, score = [], [], 0
    if ERROR.search(text):
        sig.append("has_error"); score += 2; reasons.append("Describes a concrete error, so a failing test is likely")
    if exp and act:
        sig.append("expected_actual"); score += 2; reasons.append("States expected vs actual behaviour")
    if STEPS.search(body):
        sig.append("has_steps"); score += 1; reasons.append("Has steps to reproduce")
    if "```" in body or re.search(r"(?m)^ {4}\S", body):
        sig.append("has_code"); score += 1; reasons.append("Includes a code example")
    if BUGGY.search(text):
        score += 1
    if NOT_RUNNABLE.search(title) or (NOT_RUNNABLE.search(body) and not ERROR.search(text)):
        sig.append("not_a_bug"); score -= 3; reasons.append("Looks like docs or a feature request, not a bug")
    if OTHER_OS.search(text):
        sig.append("other_os"); score -= 2; reasons.append("Seems to happen only on Windows or macOS; our sandbox runs Linux")
    if len(body.strip()) < 80:
        sig.append("vague"); score -= 2; reasons.append("Very short description")
    if (i.get("comments") or 0) > 15:
        sig.append("busy"); score -= 1; reasons.append("Long discussion; the fix may be contested")
    size = len(body)
    effort = "small" if size < 1500 and "has_error" in sig else "large" if size > 5000 else "medium"
    return {"number": i["number"], "title": title, "html_url": i.get("html_url"), "score": score, "signals": sig,
            "reasons": reasons, "effort": effort, "comments": i.get("comments") or 0}


def candidates(items: list[dict]) -> list[dict]:
    """Open, real issues nobody is assigned to, best first (before the per-issue linked-PR lookups)."""
    ok = [score_issue(i) for i in items if "pull_request" not in i and not i.get("assignees") and not i.get("locked")]
    return sorted((s for s in ok if s["score"] >= 2), key=lambda s: -s["score"])


def rank(items: list[dict], linked: dict[int, bool | None]) -> list[dict]:
    """linked[n]: True = an open PR already links it (dropped); None = couldn't check (kept, shown as unknown)."""
    out = []
    for s in candidates(items):
        lk = linked.get(s["number"], False)
        if lk is True:
            continue
        out.append({**s, "linked_pr": lk})
        if len(out) == MAX_SUGGESTIONS:
            break
    return out


def shortlist(repo: str, meta: dict, root_names: list[str] | None, items: list[dict], linked: dict[int, bool | None]) -> dict:
    """root_names None = the file listing failed: repo signals are unknown (None), never "no"."""
    known = root_names is not None
    python, tests = detect(root_names or [], meta.get("language"))
    names = {n.lower() for n in root_names or []}
    unk = lambda v: v if known else (v or None)
    signals = {"python": unk(python), "tests_found": unk(tests), "recipe_known": unk(bool(names & RECIPE)),
               "deps_checkable": unk(bool(names & LOCKS))}
    base = {"repo": repo, "repo_signals": signals, "language": meta.get("language")}
    if signals["python"] is False or signals["tests_found"] is False:
        return {**base, "state": "unsupported", "unsupported": "not_python" if signals["python"] is False else "no_tests",
                "suggestions": []}
    sug = rank(items, linked)
    unsure = not known or any(s["linked_pr"] is None for s in sug)
    state = "empty" if not sug else "partial" if unsure else "success"
    return {**base, "state": state, "unsupported": None, "suggestions": sug}


_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 600


def explore(url: str) -> dict:
    """Cached per repo for 10 min (only complete reads), else a live read; the result says when it was fetched."""
    import time
    from datetime import datetime, timezone
    repo = parse_repo_url(url)
    hit = _CACHE.get(repo.lower())
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return {**hit[1], "cached": True}
    out = {**_explore(repo), "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cached": False}
    if out["state"] in ("success", "empty", "unsupported"):   # never cache a partial read
        if len(_CACHE) > 200:
            _CACHE.clear()     # shortcut: crude bound, fine for one demo host; use an LRU if this ever serves many users
        _CACHE[repo.lower()] = (time.time(), out)
    return out


def _explore(repo: str) -> dict:
    """Live GitHub read with the server's read-only token. Per-issue timeline failures make the result partial."""
    with _client() as h:
        meta = _get(h, f"/repos/{repo}")
        if meta.get("private"):
            raise GitHubError("PRIVATE_REPO", "This repository is private; PatchPilot only reads public repositories.")
        root = _get(h, f"/repos/{repo}/contents/", required=False)
        names = [x["name"] for x in root] if isinstance(root, list) else None
        items = _get(h, f"/repos/{repo}/issues?state=open&per_page=50&sort=updated") or []
        linked: dict[int, bool | None] = {}
        for s in candidates(items)[:CANDIDATES]:
            tl = _get(h, f"/repos/{repo}/issues/{s['number']}/timeline?per_page=100", required=False)
            linked[s["number"]] = bool(linked_open_prs(tl)) if isinstance(tl, list) else None
    return shortlist(repo, meta, names, items, linked)
