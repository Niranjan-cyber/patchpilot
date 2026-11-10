"""#102 PR Feedback Assistant. Real maintainer comments from wheelgap/wheelgap#133 (fixtures/github/wheelgap-pr-133);
only the model is faked, at llm_gateway.complete."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import artifacts, db, llm_gateway
from backend.github import pr_feedback as F
from backend.github import progress as P
from tests.test_pr_history import N, REPO, github, load, new_run, recorded

FIRST, SECOND, MERGED = "comment:6748392117", "comment:6749701191", "comment:6750005419"


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(artifacts, "STORE", tmp_path / "artifacts")
    return db.connect()


def model(answers=None, calls=None):
    """Fake model: answers {id: fields}; None -> provider down."""
    def complete(msgs, *, run_id, role, kind, _completion=None):
        if calls is not None:
            calls.append((role, kind, run_id, msgs[1]["content"]))
        if answers is None:
            raise llm_gateway.QuotaPause(None, "groq")
        return json.dumps([{"id": k, **v} for k, v in answers.items()])
    return complete


def ask(c, monkeypatch, comments, answers, checks=None, calls=None):
    sha = load("pull")["head"]["sha"]
    over = {f"issues/{N}/comments?per_page=100": comments}
    if checks is not None:
        over[f"commits/{sha}/check-runs?per_page=100"] = checks
    monkeypatch.setattr(P, "_client", github(recorded(**over)))
    monkeypatch.setattr(llm_gateway, "complete", model(answers, calls))
    v = new_run(c)
    snap = P.refresh(c, [v])[v.run_id]
    return v, F.assist(c, v.run_id, snap, {f["id"] for f in P.new_feedback(c, v.run_id, snap)})


def ans(cat, **k):
    return {"category": cat, "meaning": "m", "why": "w", "reply": "r", "change": "c", "needs_judgement": False, **k}


def test_no_comments_says_no_feedback_yet(c, monkeypatch):
    calls = []
    _, out = ask(c, monkeypatch, [], {}, calls=calls)
    assert out["state"] == "empty" and out["items"] == [] and calls == []          # no model call for nothing


def test_one_actionable_request(c, monkeypatch):
    calls = []
    _, out = ask(c, monkeypatch, load("issue_comments")[1:2], {SECOND: ans("documentation", change="Move the bullet under ### Changed")},
                 calls=calls)
    [i] = out["items"]
    assert i["category"] == "documentation" and i["label"] == "Documentation" and i["new"]
    assert i["quote"].startswith("Thanks for the quick follow-up") and i["url"].endswith("6749701191")
    assert i["change"] == "Move the bullet under ### Changed" and i["reply"] == "r"
    role, kind, run_id, payload = calls[0]
    assert role == "feedback" and kind == "short" and SECOND in payload             # counted against the run's budget


def test_several_requests_and_a_non_actionable_merge_note(c, monkeypatch):
    _, out = ask(c, monkeypatch, load("issue_comments"), {FIRST: ans("code_correctness", needs_judgement=True),
                                                          SECOND: ans("documentation"), MERGED: ans("non_actionable")})
    assert [(i["id"], i["category"]) for i in out["items"]] == [(FIRST, "code_correctness"), (SECOND, "documentation"),
                                                                 (MERGED, "non_actionable")]
    assert out["items"][0]["needs_judgement"] is True and out["model_ok"]


def test_ci_failure_is_classified_by_rule_without_the_model(c, monkeypatch):
    ck = load("check_runs")
    i = next(i for i, r in enumerate(ck["check_runs"]) if r["name"] == "lint")
    ck["check_runs"][i] = {**ck["check_runs"][i], "conclusion": "failure", "output": {"title": "ruff format", "summary": "1 file would be reformatted"}}
    calls = []
    _, out = ask(c, monkeypatch, [], {}, checks=ck, calls=calls)
    [ci] = out["items"]
    assert ci["category"] == "ci" and "lint" in ci["meaning"] and "1 file would be reformatted" in ci["quote"]
    assert calls == []


def test_model_unavailable_shows_not_classified_never_a_guess(c, monkeypatch):
    _, out = ask(c, monkeypatch, load("issue_comments"), None)
    assert not out["model_ok"]
    assert all(i["category"] is None and i["label"] == "Not classified" and i["meaning"] is None for i in out["items"])


def test_model_output_outside_the_enum_is_rejected():
    got = F.parse('noise [{"id": "a", "category": "ci"}, {"id": "b", "category": "vibes"}, {"id": "zz", "category": "performance"},'
                  ' {"id": "c", "category": "performance", "needs_judgement": "yes"}] tail', {"a", "b", "c"})
    assert got["a"]["category"] is None and got["b"]["category"] is None and "zz" not in got   # "ci" is a rule-only category
    assert got["c"]["category"] == "performance" and got["c"]["needs_judgement"] is None
    assert F.parse("not json", {"a"}) == {}


def test_suggestion_block_is_a_code_change_even_when_the_model_is_down(c, monkeypatch):
    body = "Use the helper here:\n```suggestion\nreturn is_pypi(url)\n```"
    snap = {"feedback": [{"id": "comment:1", "kind": "comment", "body": body, "author": "m", "path": "src/x.py", "line": 3}]}
    monkeypatch.setattr(llm_gateway, "complete", model(None))
    [i] = F.assist(c, "r1", snap, set())["items"]
    assert i["category"] == "code_correctness" and i["change"] == "return is_pypi(url)"
    assert (i["path"], i["line"]) == ("src/x.py", 3)
    monkeypatch.setattr(llm_gateway, "complete", model({"comment:1": ans("performance")}))
    [i] = F.assist(c, "r2", snap, set())["items"]
    assert i["category"] == "performance" and i["change"] == "return is_pypi(url)"   # the model's category stands; the change is the block


def test_api_plan_is_saved_as_artifact_and_owner_scoped(c, monkeypatch):
    from backend.api import main, session
    monkeypatch.setattr(P, "_client", github(recorded()))
    monkeypatch.setattr(llm_gateway, "complete", model({FIRST: ans("code_correctness"), SECOND: ans("documentation"),
                                                        MERGED: ans("non_actionable")}))
    a, b = (TestClient(main.app, base_url="https://testserver") for _ in range(2))
    a.cookies.set("pp_sid", "tok-a")
    b.cookies.set("pp_sid", "tok-b")
    for tok in ("tok-a", "tok-b"):
        c.execute("INSERT INTO sessions(id_hash,ip_hash,created_at,last_seen_at) VALUES(?,?,?,?)",
                  (session._h(tok), None, db.now().isoformat(), db.now().isoformat()))
    v = new_run(c, session._h("tok-a"))
    assert b.get(f"/api/runs/{v.run_id}/feedback/assist").status_code == 404
    assert b.put(f"/api/runs/{v.run_id}/feedback/plan", json={"item_ids": [FIRST]}).status_code == 404
    out = a.get(f"/api/runs/{v.run_id}/feedback/assist").json()
    assert out["state"] == "ok" and len(out["items"]) == 3 and out["plan"] is None
    assert a.put(f"/api/runs/{v.run_id}/feedback/plan", json={"item_ids": [MERGED]}).status_code == 422   # not a request
    assert a.put(f"/api/runs/{v.run_id}/feedback/plan", json={"item_ids": ["comment:999"]}).status_code == 422
    r = a.put(f"/api/runs/{v.run_id}/feedback/plan", json={"item_ids": [FIRST, SECOND]}).json()
    plan = json.loads(artifacts.get(r["evidence_id"]))
    assert [g["category"] for g in plan["groups"]] == ["code_correctness", "documentation"]
    assert plan["groups"][0]["items"][0]["quote"].startswith("Thanks for picking up #114")
    assert a.get(f"/api/runs/{v.run_id}/feedback/assist").json()["plan"] == [FIRST, SECOND]


def test_assistant_never_writes_to_github(c, monkeypatch):
    methods, base = [], github(recorded())

    def client():
        h = base()
        h.event_hooks["request"].append(lambda req: methods.append((req.method, req.url.path)))
        return h
    monkeypatch.setattr(P, "_client", client)
    monkeypatch.setattr(llm_gateway, "complete", model({FIRST: ans("code_correctness")}))
    v = new_run(c)
    F.assist(c, v.run_id, P.refresh(c, [v])[v.run_id], set())
    assert methods and all(m == "GET" and p.startswith(f"/repos/{REPO}/") for m, p in methods)
