"""B15: Ask why. An answer without valid citations is rejected; the Explainer never answers uncited."""
import json

import pytest

from backend import artifacts, db
from backend.agents import explain as X
from backend.contracts.models import (CheckStatus, Diagnosis, IssueSpec, Location, Patch, ReproTest, RunView, TourItem)
from backend.llm_gateway import QuotaPause


def test_check_answer():
    known = {"a", "b"}
    assert X.check_answer({"answer": "Because x.", "evidence_ids": ["a"]}, known) is None
    assert X.check_answer({"answer": "Because x.", "evidence_ids": []}, known) == "no_citations"
    assert X.check_answer({"answer": "Because x."}, known) == "no_citations"
    assert X.check_answer({"answer": "Because x.", "evidence_ids": ["zzz"]}, known) == "unknown_evidence_id"
    assert X.check_answer({"answer": " ", "evidence_ids": ["a"]}, known) == "no_answer"
    assert X.check_answer("just text", known) == "no_result"
    assert X.check_answer({"answer": "x", "evidence_ids": "a"}, known) == "no_citations"


def test_parse_reply_finds_json():
    assert X.parse_reply('Sure!\n```json\n{"answer": "x", "evidence_ids": ["a"]}\n```') == {"answer": "x", "evidence_ids": ["a"]}
    assert X.parse_reply("no json here") is None


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(artifacts, "STORE", tmp_path / "art")
    ev = [artifacts.put("transcript"), artifacts.put("+def test_x(): assert divide(1, 0)"), artifacts.put("FAILED: DID NOT RAISE"),
          artifacts.put("run 2")]
    fix = artifacts.put("-    return 0\n+    raise ZeroDivisionError")
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="divide"), "sha")
    v.repro = ReproTest(test_diff_id=ev[1], test_ids=["tests/t.py::t"], expected_failure="x", runs_on_base=[CheckStatus.FAILED] * 2,
                        evidence_ids=ev)
    v.diagnosis = Diagnosis(hypothesis="divide swallows the error", locations=[Location(path="src/calc.py", line=3)],
                            tour=[TourItem(path="src/calc.py", why="divide lives here")], evidence_ids=[ev[2]])
    v.patch = Patch(fix_diff_id=fix, test_diff_id=ev[1], attempt=1, policy_result=CheckStatus.PASSED)
    db.save_run(db.connect(), v)
    return db.get_run(db.connect(), v.run_id), ev, fix


def test_evidence_menu_has_only_this_runs_real_artifacts(run):
    v, ev, fix = run
    menu = X.evidence(v)
    assert set(menu) == {*ev, fix} and "DID NOT RAISE" in menu[ev[2]][1]


def test_ask_returns_cited_answer(run):
    v, ev, fix = run
    reply = json.dumps({"answer": "The test fails because divide returns 0.", "evidence_ids": [ev[2]]})
    a = X.ask(v, "why_fails", None, complete=lambda msgs, **k: reply)
    assert a["evidence_ids"] == [ev[2]] and "returns 0" in a["answer"]


def test_ask_rejects_uncited_twice_then_unavailable(run):
    v, ev, fix = run
    calls = []
    def uncited(msgs, **k):
        calls.append(1); return json.dumps({"answer": "Trust me.", "evidence_ids": []})
    with pytest.raises(X.ExplainerUnavailable) as e:
        X.ask(v, "why_fails", None, complete=uncited)
    assert len(calls) == 2 and e.value.reason == "no_citations"


def test_ask_quota_is_unavailable_with_retry(run):
    v, ev, fix = run
    def q(msgs, **k): raise QuotaPause(None, "groq")
    with pytest.raises(X.ExplainerUnavailable) as e:
        X.ask(v, "why_fix", None, complete=q)
    assert e.value.reason == "quota" and e.value.retry_after is None


def test_questions_are_scoped_not_free_chat(run):
    v, ev, fix = run
    with pytest.raises(ValueError):
        X.ask(v, "tell me a joke", None, complete=lambda m, **k: "")
    with pytest.raises(ValueError):
        X.ask(v, "why_file", "src/other.py", complete=lambda m, **k: "")     # only files the diagnosis cites
    v.patch = None
    with pytest.raises(ValueError):
        X.ask(v, "why_fix", None, complete=lambda m, **k: "")               # no fix yet


def test_api_ask_owner_checked_and_unavailable(run, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api import main
    v, ev, fix = run
    c = TestClient(main.app, base_url="https://testserver")
    assert c.post(f"/api/runs/{v.run_id}/ask", json={"question": "why_fails"}).status_code == 404     # not the owner
    monkeypatch.setattr(main, "_own", lambda request, rid: None)
    monkeypatch.setattr(X.llm_gateway, "complete", lambda msgs, **k: '{"answer": "no cites", "evidence_ids": []}')
    r = c.post(f"/api/runs/{v.run_id}/ask", json={"question": "why_fails"})
    assert r.status_code == 503 and r.json()["code"] == "EXPLAINER_UNAVAILABLE"
    assert c.post(f"/api/runs/{v.run_id}/ask", json={"question": "anything"}).status_code == 422
    monkeypatch.setattr(X.llm_gateway, "complete", lambda msgs, **k: json.dumps({"answer": "ok", "evidence_ids": [ev[2]]}))
    assert c.post(f"/api/runs/{v.run_id}/ask", json={"question": "why_fails"}).json()["evidence_ids"] == [ev[2]]
