"""#70 item 9: Reviewer findings carry a level (BLOCKER / IMPORTANT / SUGGESTION / ACCEPTED_TRADEOFF), a dimension,
a checked file:line, evidence and the required action. The stored severity still decides readiness (contracts G6)."""
import importlib

import pytest

from backend import artifacts, db
from backend.contracts.models import CheckStatus, IssueSpec, Patch, ReviewResult
from backend.worker.nodes import StepContext

RV = importlib.import_module("backend.agents.review")
FIX = "diff --git a/pkg/core.py b/pkg/core.py\n--- a/pkg/core.py\n+++ b/pkg/core.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"


@pytest.mark.parametrize("raw, level, severity", [
    ({"level": "BLOCKER", "text": "t"}, "BLOCKER", "high"),
    ({"level": "important", "text": "t"}, "IMPORTANT", "medium"),
    ({"level": "SUGGESTION", "text": "t"}, "SUGGESTION", "low"),
    ({"level": "ACCEPTED_TRADEOFF", "text": "t"}, "ACCEPTED_TRADEOFF", "low"),   # stated to the maintainer, doesn't lower readiness
    ({"severity": "high", "text": "t"}, "BLOCKER", "high"),                        # old replies and code-decided concerns
    ({"severity": "low", "text": "t"}, "SUGGESTION", "low"),
    ({"level": "CRITICAL", "text": "t"}, "IMPORTANT", "medium"),                   # unknown level: never a silent pass
    ({"text": "t"}, "IMPORTANT", "medium"),
])
def test_levels_map_onto_the_stored_severity(raw, level, severity):
    f = RV.finding(raw)
    assert (f["level"], f["severity"]) == (level, severity)


def test_a_location_must_name_a_file_in_the_diff_and_every_value_is_a_string():
    paths = {"pkg/core.py", "tests/test_core.py"}
    reply = ('{"concerns": [{"level": "BLOCKER", "dimension": "correctness", "file": "./pkg/core.py", "line": 12, "text": "drops None",'
             ' "evidence": "return x or 0", "action": "Keep None as None."},'
             ' {"level": "IMPORTANT", "dimension": "vibes", "file": "pkg/made_up.py", "line": 3, "text": "invented"}]}')
    a, b = RV.parse(reply, paths)
    assert a == {"severity": "high", "level": "BLOCKER", "text": "drops None", "dimension": "correctness", "location": "pkg/core.py:12",
                 "evidence": "return x or 0", "action": "Keep None as None."}
    assert "location" not in b and "dimension" not in b   # a made-up path and an unknown dimension are dropped, not shown
    ReviewResult(concerns=[a, b])   # dict[str, str]: no int line sneaks in
    assert RV.finding(a) == a       # normalizing twice keeps everything


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t"), "sha")
    v.patch = Patch(fix_diff_id=artifacts.put(FIX), test_diff_id=artifacts.put(""), attempt=1, policy_result=CheckStatus.PASSED)
    db.save_run(db.connect(), v)
    monkeypatch.setattr("backend.agents.lint.review_concerns", lambda *a: [])
    return StepContext(v.run_id, v, lambda *a, **k: None), monkeypatch


def test_review_stores_located_findings_and_a_blocker_lowers_readiness(ctx):
    c, mp = ctx
    seen = {}
    mp.setattr(RV, "complete", lambda msgs, **k: seen.setdefault("p", msgs[0]["content"]) and
               '{"concerns": [{"level": "BLOCKER", "dimension": "scope", "file": "pkg/core.py", "line": 1, "text": "changes x globally",'
               ' "action": "Limit the change to the failing case."}]}')
    RV.review(c)
    r = db.get_run(db.connect(), c.run_id).review
    assert r.lowers_readiness is True and r.concerns[0]["location"] == "pkg/core.py:1" and r.concerns[0]["level"] == "BLOCKER"
    assert "BLOCKER|IMPORTANT|SUGGESTION|ACCEPTED_TRADEOFF" in seen["p"] and "even if all tests pass" in seen["p"]


def test_only_tradeoffs_and_suggestions_keep_readiness(ctx):
    c, mp = ctx
    mp.setattr(RV, "complete", lambda *a, **k: '{"concerns": [{"level": "ACCEPTED_TRADEOFF", "text": "only handles the str case"},'
                                                ' {"level": "SUGGESTION", "text": "a docstring would help"}]}')
    RV.review(c)
    r = db.get_run(db.connect(), c.run_id).review
    assert r.lowers_readiness is False and [x["level"] for x in r.concerns] == ["ACCEPTED_TRADEOFF", "SUGGESTION"]


def test_report_lists_level_dimension_location_and_action(ctx):
    from backend.report import render
    c, mp = ctx
    mp.setattr(RV, "complete", lambda *a, **k: '{"concerns": [{"level": "IMPORTANT", "dimension": "compatibility", "file": "pkg/core.py",'
                                                ' "line": 1, "text": "renames a public function", "action": "Keep the old name as an alias."}]}')
    RV.review(c)
    text = render(db.get_run(db.connect(), c.run_id))
    assert "- **IMPORTANT** (compatibility, `pkg/core.py:1`): renames a public function. To do: Keep the old name as an alias." in text
