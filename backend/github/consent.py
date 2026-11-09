"""Maintainer consent (contracts v0.5 §2.2, #70; human decision 2026-11-09). Code decides from what GitHub says, never a model.
Silence, an open issue, no assignee or no PR is never consent."""
import re

from backend import db
from backend.contracts.models import ConsentEvidence

MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}
INVITE_LABELS = {"pr welcome", "prs welcome", "pull request welcome", "pull requests welcome", "contributions welcome", "help wanted"}
_PR = r"(?:a\s+)?(?:pr|pull\s+request|fix|patch)"
_WELCOME = r"\b(?:prs?|pull\s+requests?|fix|patch)\b[^.\n]{0,40}\b(?:would\s+be|is|are)\s+(?:very\s+|most\s+)?welcome\b"   # "a PR fixing this would be welcome"
POSITIVE = re.compile(rf"""(?ix)
  ^\W*(?:yes|yep|yeah|sure|absolutely|definitely|please\ do|go\ (?:for\ it|ahead))\b
| \b(?:go\ ahead|go\ for\ it|please\ do|feel\ free|sounds\ good|that\ would\ be\ (?:great|nice|helpful))\b
| \b(?:prs?|pull\ requests?|contributions?|patch(?:es)?)\ (?:are\ |is\ )?(?:very\ )?welcome\b
| \b(?:would|will|happy\ to|glad\ to)\ (?:welcome|accept|review|merge|appreciate|love)\ {_PR}\b
| \bplease\ (?:send|open|submit|make)\ {_PR}\b
| {_WELCOME}
""")
# before our ask only PR-specific wording counts ("Yes, I can reproduce" is not a request for a fix)
REQUEST = re.compile(rf"""(?ix)
  \b(?:prs?|pull\ requests?|contributions?|patch(?:es)?)\ (?:are\ |is\ )?(?:very\ )?welcome\b
| \b(?:would|will|happy\ to|glad\ to)\ (?:welcome|accept|review|merge|appreciate|love)\ {_PR}\b
| \bplease\ (?:send|open|submit|make)\ {_PR}\b
| \bfeel\ free\ to\ (?:open|send|submit|make)\ {_PR}\b
| {_WELCOME}
""")
DECLINE = re.compile(r"""(?ix)
  \b(?:no\ thanks|no,\ thanks|not\ interested|please\ don'?t|do\ not\ open|won'?t\ fix|wontfix|not\ planned|working\ as\ intended
     |not\ a\ bug|we\ (?:won'?t|will\ not|don'?t)\ (?:accept|merge|take)|closing\ this|i'?ll\ fix\ (?:this|it)\ myself
     |already\ (?:fixed|working\ on\ (?:it|this)))\b
""")
CONTRIB_INVITE = re.compile(r"(?i)(?:pull requests?|prs?|bug ?fix(?:es)?|contributions?)[^.\n]{0,40}\b(?:are |is )?(?:very )?welcome"
                            r"|feel free to (?:open|send|submit) (?:a )?(?:pr|pull request)")
CONTRIB_FIRST = re.compile(r"(?i)open an issue (?:first|before)|discuss[^.\n]{0,40}\b(?:first|before)|before (?:opening|submitting|sending) "
                           r"(?:a |any )?(?:pr|pull request)[^.\n]{0,60}\b(?:issue|discuss|ask)")
_CID = re.compile(r"issuecomment-(\d+)")


def _quote(text: str) -> str:
    return " ".join((text or "").split())[:300]


def _clean(body: str) -> str:   # quoted lines are someone else's words
    return "\n".join(l for l in (body or "").replace("’", "'").splitlines() if not l.lstrip().startswith(">"))


def comment_id(url: str | None) -> int | None:
    m = _CID.search(url or "")
    return int(m.group(1)) if m else None


def read(issue: dict, comments: list, *, asked_url: str | None, me: str | None, contributing: tuple[str, str] | None = None) -> dict:
    """{state: granted|declined|replied|waiting|none, evidence, replies}. replies = maintainer comments after our ask,
    each {url, author, association, quote, positive, declined}; `replied` = only replies whose wording isn't clearly yes or no."""
    now, asked = db.now(), comment_id(asked_url)
    if issue.get("state") == "closed" and issue.get("state_reason") == "not_planned":
        return {"state": "declined", "evidence": None, "replies": [], "why": "The issue was closed as not planned."}
    replies, request = [], None
    for c in comments if isinstance(comments, list) else []:
        if not isinstance(c, dict) or c.get("author_association") not in MAINTAINER:
            continue
        login = (c.get("user") or {}).get("login")
        if me and login and login.lower() == me.lower():
            continue   # the user's own words are never consent
        text = _clean(c.get("body") or "")
        pos, dec = bool(POSITIVE.search(text)), bool(DECLINE.search(text))
        if asked and isinstance(c.get("id"), int) and c["id"] > asked:
            replies.append({"url": c.get("html_url"), "author": login, "association": c.get("author_association"),
                            "quote": _quote(text), "positive": pos and not dec, "declined": dec})
        elif REQUEST.search(text) and not dec and request is None:
            request = ConsentEvidence(kind="maintainer_request", source_url=c.get("html_url"), author=login,
                                      author_association=c.get("author_association"), quote=_quote(text), recorded_at=now)
    if replies and replies[-1]["declined"]:   # the latest maintainer word wins
        return {"state": "declined", "evidence": None, "replies": replies, "why": "A maintainer declined."}
    if (yes := next((r for r in reversed(replies) if r["positive"]), None)):
        return {"state": "granted", "replies": replies, "evidence": ConsentEvidence(
            kind="maintainer_reply", source_url=yes["url"], author=yes["author"], author_association=yes["association"],
            quote=yes["quote"], recorded_at=now)}
    if request:
        return {"state": "granted", "evidence": request, "replies": replies}
    labels = [l.get("name", "") for l in issue.get("labels", []) if isinstance(l, dict)]
    if (lab := next((l for l in labels if l.lower() in INVITE_LABELS), None)):
        return {"state": "granted", "replies": replies, "evidence": ConsentEvidence(
            kind="maintainer_request", source_url=issue.get("html_url"), quote=f"label: {lab}", recorded_at=now)}
    if contributing and (m := CONTRIB_INVITE.search(contributing[1])) and not CONTRIB_FIRST.search(contributing[1]):
        return {"state": "granted", "replies": replies, "evidence": ConsentEvidence(
            kind="contributing_invites", source_url=contributing[0], quote=_quote(contributing[1][max(0, m.start() - 80):m.end() + 80]),
            recorded_at=now)}
    if replies:
        return {"state": "replied", "evidence": None, "replies": replies}
    return {"state": "waiting" if asked else "none", "evidence": None, "replies": []}


def check(repo: str, number: int, *, asked_url: str | None, me: str | None) -> dict:
    """Read-only GitHub lookup + read(). A failed lookup raises GitHubError: unknown is never consent."""
    import base64
    from backend.github import reader
    with reader._client() as h:
        issue = reader._get(h, f"/repos/{repo}/issues/{number}")
        n = issue.get("comments") or 0   # replies to our ask are the newest: read the first and the last page
        comments = [c for p in sorted({1, -(-n // 100)}) if n
                    for c in (reader._get(h, f"/repos/{repo}/issues/{number}/comments?per_page=100&page={p}") or [])]
        contributing = None
        for path in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"):
            f = reader._get(h, f"/repos/{repo}/contents/{path}", required=False)
            if f and f.get("content"):
                contributing = (f.get("html_url") or path, base64.b64decode(f["content"]).decode("utf-8", "replace"))
                break
    return read(issue, comments, asked_url=asked_url, me=me, contributing=contributing)
