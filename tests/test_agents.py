import pytest

from backend import db, llm_gateway as G
import importlib

from backend.agents import loop

R = importlib.import_module("backend.agents.reproduce")
from backend.contracts.models import CheckStatus, IssueSpec, RunStatus, RunView
from backend.sandbox.docker import Result
from backend.worker.nodes import StepContext

# real pytest 8 output (no -q, -rfE) for a pytest.raises that didn't raise
FAIL_OUT = """============================= test session starts ==============================
collected 1 item

tests/test_patchpilot_issue_1.py F                                       [100%]

=================================== FAILURES ===================================
_________________________ test_divide_by_zero_raises __________________________

    def test_divide_by_zero_raises():
>       with pytest.raises(ZeroDivisionError):
E       Failed: DID NOT RAISE <class 'ZeroDivisionError'>

tests/test_patchpilot_issue_1.py:6: Failed
=========================== short test summary info ============================
FAILED tests/test_patchpilot_issue_1.py::test_divide_by_zero_raises - Failed: DID NOT RAISE <class 'ZeroDivisionError'>
============================== 1 failed in 0.02s ===============================
"""
DIFF = "diff --git a/tests/test_patchpilot_issue_1.py b/tests/test_patchpilot_issue_1.py\nnew file mode 100644\n--- /dev/null\n+++ b/tests/test_patchpilot_issue_1.py\n@@ -0,0 +1 @@\n+x\n"


def scripted(*replies):
    it = iter(replies)
    return lambda msgs, **k: next(it)


def test_loop_runs_one_command_per_step_and_stops_on_done():
    cmds = []
    done = f'```bash\necho {loop.DONE} \'{{"test_ids": ["t::a"]}}\'\n```'
    res, msgs = loop.run("task", exec_=lambda c: (cmds.append(c), (0, f'{loop.DONE} {{"test_ids": ["t::a"]}}') if loop.DONE in c else (0, "ok"))[1],
                         run_id="r", role="x", complete=scripted("think\n```bash\nls\n```", done))
    assert res == {"test_ids": ["t::a"]} and cmds[0] == "ls"


def test_loop_rejects_two_blocks_and_gives_up_at_step_limit():
    res, msgs = loop.run("t", exec_=lambda c: (0, ""), run_id="r", role="x", step_limit=2,
                         complete=scripted("```bash\na\n```\n```bash\nb\n```", "no block at all"))
    assert res is None and "Format error" in msgs[3]["content"]


def test_redaction():
    assert "ghp_" not in G.redact("token ghp_" + "a" * 30) and "[redacted]" in G.redact("Authorization: Bearer xyz")


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(G, "_limits", lambda: {"run_llm_tokens": 1000, "global_llm_tokens_per_day": 5000})


def test_budget_unset_is_never_unlimited(tmpdb, monkeypatch):
    monkeypatch.setattr(G, "_limits", lambda: {"run_llm_tokens": 1000, "global_llm_tokens_per_day": 0})
    with pytest.raises(G.BudgetExceeded):
        G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=lambda **k: None)


def test_429_without_retry_after_has_unknown_resume(tmpdb):
    class RateLimitError(Exception): pass
    def boom(**k): raise RateLimitError("429 Too Many Requests")
    with pytest.raises(G.QuotaPause) as e:
        G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=boom)
    assert e.value.resume_at is None


def test_tokens_are_counted_per_run(tmpdb):
    class U: prompt_tokens, completion_tokens = 600, 500
    class M: content = "hi"
    class Ch: message = M
    class Resp: usage, choices = U, [Ch]
    G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=lambda **k: Resp)
    with pytest.raises(G.BudgetExceeded):
        G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=lambda **k: Resp)


@pytest.fixture
def node(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    t = db.now()
    v = db.create_run(db.connect(), IssueSpec(html_url="https://github.com/o/r/issues/1", repo="o/r", number=1, title="divide",
                                               actual="returns 0 instead of ZeroDivisionError"), "sha")
    monkeypatch.setattr(R.docker, "start", lambda *a: Result(0, "id"))
    monkeypatch.setattr(R.docker, "rm", lambda *a: None)
    monkeypatch.setattr(R.docker, "exec_", lambda name, cmd, timeout=0: Result(0, DIFF if "git diff" in cmd else ""))
    monkeypatch.setattr(R, "limits", lambda: {"retries": {"test_designer": 2}})
    ctx = StepContext(v.run_id, v, lambda *a, **k: None)
    return ctx, monkeypatch


def test_reproduce_passes_g3_on_two_real_failures(node):
    ctx, mp = node
    mp.setattr(R.loop, "run", lambda *a, **k: ({"test_ids": ["tests/test_patchpilot_issue_1.py::test_divide_by_zero_raises"],
                                               "expected_failure": "DID NOT RAISE"}, [{"role": "user", "content": "t"}]))
    mp.setattr(R, "_check_run", lambda rid, d, t: FAIL_OUT)
    r = R.reproduce(ctx)
    assert r.status == CheckStatus.PASSED, r.reason
    assert db.get_run(db.connect(), ctx.run_id).repro.runs_on_base == [CheckStatus.FAILED, CheckStatus.FAILED]


def test_reproduce_retries_then_fails_on_import_error(node):
    ctx, mp = node
    calls = []
    mp.setattr(R.loop, "run", lambda *a, **k: (calls.append(1), ({"test_ids": ["tests/test_patchpilot_issue_1.py::t"]}, []))[1])
    mp.setattr(R, "_check_run", lambda rid, d, t: "E   ModuleNotFoundError: No module named 'nope'\n1 error in 0.1s\n")
    r = R.reproduce(ctx)
    assert r.status == CheckStatus.FAILED and len(calls) == 3


def test_quota_pauses_instead_of_failing(node):
    ctx, mp = node
    def q(*a, **k): raise G.QuotaPause(None, "gemini")
    mp.setattr(R.loop, "run", q)
    r = R.reproduce(ctx)
    assert r.status == CheckStatus.NOT_RUN and ctx.scratch["pause"].resume_at is None


def test_issue_23_reproduction_without_test_ids_never_passes_g3(node):
    ctx, mp = node
    calls = []
    mp.setattr(R.loop, "run", lambda *a, **k: (calls.append(1), ({"expected_failure": "x"}, []))[1])    # DONE line without test_ids
    mp.setattr(R, "_check_run", lambda rid, d, t: FAIL_OUT)
    r = R.reproduce(ctx)
    assert r.status == CheckStatus.FAILED and r.reason == "no_test_written" and len(calls) == 3


def test_503_backs_off_then_succeeds(tmpdb, monkeypatch):
    monkeypatch.setattr(__import__("time"), "sleep", lambda s: None)
    class ServiceUnavailableError(Exception): pass
    class U: prompt_tokens, completion_tokens = 1, 1
    class M: content = "ok"
    class Ch: message = M
    class Resp: usage, choices = U, [Ch]
    calls = []
    def flaky(**k):
        calls.append(1)
        if len(calls) < 3: raise ServiceUnavailableError("503 high demand")
        return Resp
    assert G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=flaky) == "ok" and len(calls) == 3


def test_persistent_503_pauses_with_unknown_resume(tmpdb, monkeypatch):
    monkeypatch.setattr(__import__("time"), "sleep", lambda s: None)
    class ServiceUnavailableError(Exception): pass
    def down(**k): raise ServiceUnavailableError("503")
    with pytest.raises(G.QuotaPause) as e:
        G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=down)
    assert e.value.resume_at is None


def _ok_resp(text="ok"):
    class U: prompt_tokens, completion_tokens = 1, 1
    class M: content = text
    class Ch: message = M
    class Resp: usage, choices = U, [Ch]
    return Resp


@pytest.fixture
def three_models(tmpdb, monkeypatch):
    monkeypatch.setattr(__import__("time"), "sleep", lambda s: None)
    monkeypatch.delenv("PP_AGENT_MODEL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("PP_LOCAL_MODEL", "ollama_chat/qwen2.5-coder:7b")
    assert [m.split("/")[0] for m in G.chain("agent")] == ["gemini", "groq", "ollama_chat"]


def test_quota_on_gemini_falls_back_to_groq(three_models):
    class RateLimitError(Exception): pass
    seen = []
    def fake(model, **k):
        seen.append(model)
        if model.startswith("gemini"): raise RateLimitError("429 quota exceeded per day")
        return _ok_resp("from groq")
    assert G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=fake) == "from groq"
    assert [m.split("/")[0] for m in seen] == ["gemini", "groq"]


def test_overload_and_quota_fall_through_to_local(three_models):
    class ServiceUnavailableError(Exception): pass
    class RateLimitError(Exception): pass
    seen = []
    def fake(model, **k):
        seen.append(model)
        if model.startswith("gemini"): raise ServiceUnavailableError("503")
        if model.startswith("groq"): raise RateLimitError("413 Request too large for model")
        return _ok_resp("local")
    assert G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=fake) == "local"
    assert [m.split("/")[0] for m in seen] == ["gemini", "groq", "ollama_chat"]   # no backoff retries before a fallback exists


def test_all_providers_out_pauses_at_the_earliest_known_resume(three_models):
    class RateLimitError(Exception):
        def __init__(self, msg, h): super().__init__(msg); self.response = type("R", (), {"headers": h})
    def fake(model, **k):
        if model.startswith("groq"): raise RateLimitError("429", {"retry-after": "60"})
        raise RateLimitError("429", {})
    with pytest.raises(G.QuotaPause) as e:
        G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=fake)
    assert e.value.resume_at is not None and (e.value.resume_at - db.now()).total_seconds() <= 61


def test_a_real_error_is_not_hidden_by_fallback(three_models):
    seen = []
    def fake(model, **k):
        seen.append(model); raise ValueError("bad request")
    with pytest.raises(ValueError):
        G.complete([{"role": "user", "content": "x"}], run_id="r", role="x", _completion=fake)
    assert len(seen) == 1
