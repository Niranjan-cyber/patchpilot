"""B18: rank a repo's open issues by runnable signals (not labels). Pure ranker on fixture + crafted issues."""
import json
from pathlib import Path

import pytest

from backend.github.explore import parse_repo_url, rank, score_issue, shortlist
from backend.github.reader import GitHubError

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "github"


def iss(n, body, title="t", labels=(), assignees=(), comments=0, pr=False):
    d = {"number": n, "title": title, "body": body, "labels": [{"name": l} for l in labels], "assignees": list(assignees),
         "comments": comments, "html_url": f"https://github.com/o/r/issues/{n}"}
    if pr:
        d["pull_request"] = {"url": "x"}
    return d


BUG = """`Path(path_type=...)` returns the wrong error when the file is missing.

Steps to reproduce:
```python
import click
click.Path(exists=True, path_type=str).convert("nope", None, None)
```
Expected: BadParameter saying the file doesn't exist
Actual: TypeError raised

Traceback (most recent call last):
  File "x.py", line 3, in <module>
TypeError: expected str, bytes or os.PathLike object
"""


def test_clear_bug_scores_high_with_reasons():
    s = score_issue(iss(1, BUG, title="Path raises TypeError instead of BadParameter"))
    assert s["score"] >= 5
    assert {"has_error", "expected_actual", "has_steps", "has_code"} <= set(s["signals"])
    assert any("error" in r.lower() for r in s["reasons"]) and s["effort"] in ("small", "medium", "large")


def test_labels_do_not_drive_the_rank():
    a = score_issue(iss(1, BUG, labels=["bug", "good first issue"]))
    b = score_issue(iss(1, BUG, labels=[]))
    assert a["score"] == b["score"]


def test_docs_and_feature_requests_rank_low():
    doc = score_issue(iss(2, "It would be nice to document how the pager behaves. Please add a section to the docs.",
                          title="Document less interruption behavior"))
    feat = score_issue(iss(3, "Feature request: add support for TOML config files.", title="Add TOML support"))
    assert doc["score"] < 2 and feat["score"] < 2


def test_vague_or_contested_issues_rank_lower():
    vague = score_issue(iss(4, "broken", title="doesn't work"))
    busy = score_issue(iss(5, BUG, comments=40))
    assert vague["score"] < 2 and busy["score"] < score_issue(iss(5, BUG))["score"]


def test_rank_drops_prs_assigned_and_linked_and_caps_at_5():
    items = [iss(i, BUG) for i in range(1, 9)] + [iss(20, BUG, pr=True), iss(21, BUG, assignees=[{"login": "x"}])]
    out = rank(items, linked={3: True, 4: None})
    nums = [s["number"] for s in out]
    assert 20 not in nums and 21 not in nums and 3 not in nums and len(out) == 5
    assert next(s for s in out if s["number"] == 4)["linked_pr"] is None     # couldn't check: shown, not hidden


def test_rank_on_fixture_keeps_only_real_issues():
    items = json.loads((FIX / "issues_list_click.json").read_text(encoding="utf-8"))
    out = rank(items, linked={})
    assert all(s["number"] in (3888, 3886) for s in out)


def test_shortlist_states():
    meta = {"language": "Python", "private": False}
    root = ["pyproject.toml", "tests", "requirements.txt"]
    ok = shortlist("o/r", meta, root, [iss(1, BUG)], linked={})
    assert ok["state"] == "success" and ok["repo_signals"]["recipe_known"] and ok["repo_signals"]["tests_found"]
    assert shortlist("o/r", meta, root, [iss(2, "Please document X.")], linked={})["state"] == "empty"
    assert shortlist("o/r", meta, root, [iss(1, BUG)], linked={1: None})["state"] == "partial"
    js = shortlist("o/r", {"language": "JavaScript"}, ["package.json"], [iss(1, BUG)], linked={})
    assert js["state"] == "unsupported" and js["unsupported"] == "not_python" and js["suggestions"] == []


def test_parse_repo_url_only_github():
    assert parse_repo_url("https://github.com/pallets/click") == "pallets/click"
    assert parse_repo_url("https://github.com/pallets/click/issues?q=x") == "pallets/click"
    assert parse_repo_url(" https://github.com/pallets/click.git ") == "pallets/click"
    for bad in ("https://gitlab.com/a/b", "http://github.com/a/b", "https://github.com.evil.com/a/b", "https://github.com/a",
                "file:///etc/passwd", "https://169.254.169.254/latest"):
        with pytest.raises(GitHubError):
            parse_repo_url(bad)


def test_failed_file_listing_is_unknown_not_no_tests():
    s = shortlist("o/r", {"language": "Python"}, None, [iss(1, BUG)], linked={})
    assert s["state"] == "partial" and s["repo_signals"]["tests_found"] is None and s["suggestions"]


def test_api_explore_errors_and_success(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api import main
    from backend.github import explore as E
    c = TestClient(main.app)
    assert c.post("/api/repos/explore", json={"url": "https://gitlab.com/a/b"}).json()["code"] == "INVALID_URL"
    def limited(url): raise GitHubError("GITHUB_UNAVAILABLE", "GitHub is rate-limiting us.", 120)
    monkeypatch.setattr(E, "explore", limited)
    r = c.post("/api/repos/explore", json={"url": "https://github.com/o/r"})
    assert r.status_code == 503 and r.json()["retry_after"] == 120        # a GitHub failure, distinct from empty
    monkeypatch.setattr(E, "explore", lambda url: {"state": "empty", "suggestions": []})
    assert c.post("/api/repos/explore", json={"url": "https://github.com/o/r"}).json()["state"] == "empty"


def test_os_specific_bugs_rank_below_linux_reproducible_ones():
    win = score_issue(iss(6, BUG + "\nThis only happens on Windows: WinError 87.", title="edit throws WinError 87"))
    assert "other_os" in win["signals"] and win["score"] < score_issue(iss(6, BUG))["score"]


def test_explore_caches_complete_reads_only(monkeypatch):
    from backend.github import explore as E
    E._CACHE.clear()
    calls = []
    monkeypatch.setattr(E, "_explore", lambda repo: (calls.append(repo), {"state": "success", "suggestions": []})[1])
    a = E.explore("https://github.com/o/r"); b = E.explore("https://github.com/O/R/issues")
    assert len(calls) == 1 and a["cached"] is False and b["cached"] is True and b["fetched_at"] == a["fetched_at"]
    E._CACHE.clear()
    monkeypatch.setattr(E, "_explore", lambda repo: (calls.append(repo), {"state": "partial", "suggestions": []})[1])
    E.explore("https://github.com/o/r"); E.explore("https://github.com/o/r")
    assert len(calls) == 3                                   # partial results are re-read, never served stale
