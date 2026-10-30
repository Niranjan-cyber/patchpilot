import importlib

import pytest

from backend import artifacts, db
from backend.contracts.models import CheckStatus, IssueSpec, Patch
from backend.llm_gateway import QuotaPause
from backend.worker.nodes import StepContext

RV = importlib.import_module("backend.agents.review")


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="t"), "sha")
    v.patch = Patch(fix_diff_id=artifacts.put("fix"), test_diff_id=artifacts.put("test"), attempt=1, policy_result=CheckStatus.PASSED)
    db.save_run(db.connect(), v)
    return StepContext(v.run_id, v, lambda *a, **k: None), monkeypatch


def test_no_concerns_keeps_readiness(ctx):
    c, mp = ctx
    mp.setattr(RV, "complete", lambda *a, **k: '{"concerns": []}')
    assert RV.review(c).status == CheckStatus.PASSED
    assert db.get_run(db.connect(), c.run_id).review.lowers_readiness is False


def test_high_concern_lowers_readiness(ctx):
    c, mp = ctx
    mp.setattr(RV, "complete", lambda *a, **k: 'ok {"concerns": [{"severity": "high", "text": "hard-codes the test input"}]}')
    RV.review(c)
    assert db.get_run(db.connect(), c.run_id).review.lowers_readiness is True


@pytest.mark.parametrize("fake", [lambda *a, **k: "not json", lambda *a, **k: (_ for _ in ()).throw(QuotaPause(None, "groq"))])
def test_unavailable_review_is_never_a_silent_pass(ctx, fake):
    c, mp = ctx
    mp.setattr(RV, "complete", fake)
    RV.review(c)
    r = db.get_run(db.connect(), c.run_id).review
    assert r.lowers_readiness is True and r.concerns


def test_added_silent_except_lowers_readiness_even_when_the_llm_sees_nothing(ctx):   # run 11's TypeError retry
    from tests.test_diff_policy import RUN11
    c, mp = ctx
    v = db.get_run(db.connect(), c.run_id)
    v.patch = Patch(fix_diff_id=artifacts.put(RUN11), test_diff_id=artifacts.put("test"), attempt=1, policy_result=CheckStatus.PASSED)
    db.save_run(db.connect(), v)
    mp.setattr(RV, "complete", lambda *a, **k: '{"concerns": []}')
    RV.review(c)
    r = db.get_run(db.connect(), c.run_id).review
    assert r.lowers_readiness is True and any("except TypeError:" in x["text"] for x in r.concerns)
