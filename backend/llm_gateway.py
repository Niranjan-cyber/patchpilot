"""LLM gateway: provider calls, token accounting and pause maths (B06).

This file currently holds only the pause maths for a provider 429, which is
pure and testable without a key or a network. The LiteLLM calls, the
`llm_calls` token accounting and redaction land on top of it in B06.

`resume_at` is set **only** from a provider's `Retry-After` or a documented
reset time (contracts.md:248). Gemini's free tier resets at midnight Pacific,
so that is the one documented reset we know. Otherwise it stays null and the
UI says "until capacity is available" — a guessed time would be a failure
shown as a fact.

Needs the `tzdata` package: a Windows host has no system tz database.
"""

from datetime import datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def parse_retry_after(value, now):
    """`Retry-After` (delay-seconds or HTTP-date) as an absolute time, else None.

    A past, negative or unparseable value is None: the caller must not pause
    until a time the provider never gave. The value crosses a trust boundary
    (a provider's 429), so nothing here may raise.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    # isdigit() accepts far more than int() does, e.g. the superscript "²".
    if raw.isascii() and raw.isdigit():
        try:
            when = now + timedelta(seconds=int(raw))
        except (OverflowError, ValueError):
            return None
    else:
        try:
            when = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)

    # Both forms get the same filter: never hand back a time already gone.
    return when if when >= now else None


def next_midnight_pacific(now):
    """The next 00:00 Pacific strictly after `now` (Gemini's free-tier reset).

    Date arithmetic in local wall-clock, so a day is never skipped or doubled
    across a DST switch.
    """
    local = now.astimezone(PACIFIC)
    return datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=PACIFIC)


def resume_at(now, retry_after=None, daily_quota=False):
    """When to resume after a 429, or None when no provider time is known.

    `retry_after` is the raw header value; `daily_quota` says the 429 was the
    provider's daily quota rather than a per-minute rate limit. The returned
    time is truthful even if far away: ending a run that would pause past
    `max_pause_seconds` is the caller's decision (contracts.md:96, :244).
    """
    from_header = parse_retry_after(retry_after, now)
    if from_header is not None:
        return from_header
    if daily_quota:
        return next_midnight_pacific(now)
    return None


# ---- LLM calls (A, B06 takeover). The only path to a model. Never sees credentials beyond the provider key. ----
import os as _os
import re as _re

from backend import db as _db
from backend.config import limits as _limits

# gemini-2.5-flash is closed to new keys (verified 2026-10-30); 3.5-flash answers on the team's key.
GROQ_MODEL = "groq/openai/gpt-oss-120b"


# shortcut: per-process memory of providers out until a known reset; lost on worker restart (harmless: one extra 429).
_out: dict = {}


def chain(kind: str) -> list[str]:
    """Models to try in order (PP_AGENT_MODELS). Short calls may end on a local model (PP_LOCAL_MODEL); agent work never
    does: the 7B model made up evidence and looped (runs 1, 3), so agents pause instead.
    Free-tier quotas are per model, so the list holds several strong ones (verified on the team's keys 2026-10-30). Groq is
    first: fast; gemini-3.8-flash took 48-120 s a call (run 9) and 3.5-flash's free daily cap is a dozen calls.
    Nebius is paid credit: after the free Groq models (short Groq waits are waited out, so it only runs when Groq is out
    for longer), one cheap fast model ($0.15/M input, 0.8 s a call); the daily token budget caps its spend."""
    keyed = {"groq/": bool(_os.getenv("GROQ_API_KEY")), "nebius/": bool(_os.getenv("NEBIUS_API_KEY"))}
    agent = [m for m in _os.getenv("PP_AGENT_MODELS", f"{GROQ_MODEL},groq/qwen/qwen3.8-27b,nebius/openai/gpt-oss-120b,"
                                   "gemini/gemini-3.8-flash,gemini/gemini-3.5-flash").split(",")
             if m and all(ok or not m.startswith(p) for p, ok in keyed.items())]
    if kind != "short":
        return list(dict.fromkeys(agent))
    return list(dict.fromkeys(m for m in (_os.getenv("PP_SHORT_MODEL") or agent[0], *agent, _os.getenv("PP_LOCAL_MODEL")) if m))


_SECRET = _re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{30,}|gsk_[A-Za-z0-9]{20,}|v1\.[A-Za-z0-9_-]{40,}|"
                      r"sk-[A-Za-z0-9]{20,}|Authorization:\s*\S+(?:\s+\S+)?)")
_CALLS = """CREATE TABLE IF NOT EXISTS llm_calls(id INTEGER PRIMARY KEY, run_id TEXT, role TEXT, model TEXT, prompt_tokens INTEGER,
  completion_tokens INTEGER, latency_ms INTEGER, status TEXT, ts TEXT)"""


class QuotaPause(Exception):
    """Provider limit hit. resume_at is None when the provider didn't say (contracts §6: never guessed)."""
    def __init__(self, resume_at, provider):
        super().__init__(f"{provider} quota"); self.resume_at, self.provider = resume_at, provider


class BudgetExceeded(Exception):
    def __init__(self, scope):
        super().__init__(scope); self.scope = scope


def redact(text: str) -> str:
    return _SECRET.sub("[redacted]", text)


def tokens_used(run_id: str | None = None, day: str | None = None) -> int:
    c = _db.connect(); c.execute(_CALLS)
    if run_id:
        q, a = "SELECT COALESCE(SUM(prompt_tokens+completion_tokens),0) FROM llm_calls WHERE run_id=?", (run_id,)
    else:
        q, a = "SELECT COALESCE(SUM(prompt_tokens+completion_tokens),0) FROM llm_calls WHERE substr(ts,1,10)=?", (day,)
    return c.execute(q, a).fetchone()[0]


def complete(messages: list[dict], *, run_id: str, role: str, kind: str = "agent", _completion=None) -> str:
    """One chat completion with budgets (per run + global/day), redaction, logging, and quota → QuotaPause."""
    lim = _limits()
    if tokens_used(run_id=run_id) >= lim["run_llm_tokens"]:
        raise BudgetExceeded("run")
    if lim["global_llm_tokens_per_day"] <= 0 or tokens_used(day=_db.now().date().isoformat()) >= lim["global_llm_tokens_per_day"]:
        raise BudgetExceeded("global")
    if _completion is None:
        import litellm
        _completion = litellm.completion
    msgs = [{**m, "content": redact(m["content"])} for m in messages]
    now, pauses = _db.now(), []
    models = [m for m in chain(kind) if not (m in _out and _out[m] > now)]   # out until a known reset: don't ask again
    if not models:
        raise QuotaPause(min(_out[m] for m in chain(kind)), chain(kind)[0].split("/")[0])
    for i, model in enumerate(models):
        for again in (True, False):
            try:     # back off on overload only when no fallback is left
                return _call(model, msgs, run_id, role, _completion, backoff=i == len(models) - 1)
            except QuotaPause as q:
                wait = (q.resume_at - _db.now()).total_seconds() if q.resume_at else None
                if again and wait is not None and wait <= 60:     # e.g. Groq's per-minute cap: a short wait beats a weaker model
                    __import__("time").sleep(max(wait, 1)); continue
                if wait is not None and wait > 60:
                    _out[model] = q.resume_at
                pauses.append(q); break
    # resume when the first model is back, skipped ones included (run 9 waited for Gemini's daily reset while Groq was back
    # in minutes); unknown stays None
    known = [p.resume_at for p in pauses if p.resume_at] + [_out[m] for m in chain(kind) if m in _out and _out[m] > now]
    raise QuotaPause(min(known) if known else None, pauses[0].provider)


def _call(model, msgs, run_id, role, _completion, backoff):
    import time
    t0 = time.time()
    c = _db.connect(); c.execute(_CALLS)
    log = lambda status, p=0, k=0: c.execute("INSERT INTO llm_calls(run_id,role,model,prompt_tokens,completion_tokens,latency_ms,status,ts) "
                                             "VALUES(?,?,?,?,?,?,?,?)", (run_id, role, model, p, k, int((time.time() - t0) * 1000),
                                                                         status, _db.now().isoformat()))
    r, overloaded = None, False
    for wait in (0, 5, 15, 30) if backoff else (0,):   # provider overload (503 "high demand") is transient
        if wait:
            time.sleep(wait)
        try:     # no temperature: deprecated for Gemini 3+; a local model on a laptop GPU is slow, so it gets longer
            r = _completion(model=model, messages=msgs, timeout=600 if model.startswith("ollama") else 120)
            break
        except Exception as e:
            # overload or a dropped network (DNS/connect, not TLS) is transient: the local model needs no network
            if "ServiceUnavailable" in type(e).__name__ or "503" in str(e) or "overloaded" in str(e).lower() or \
                    ("CERTIFICATE" not in str(e) and _re.search(r"getaddrinfo|ConnectError|Connection (refused|reset|error)|[Tt]imed? ?out", str(e))):
                log("unavailable"); overloaded = True; continue
            _raise_classified(e, model, log)
    if r is None and overloaded:      # still overloaded: pause until capacity is back; time unknown → never guessed
        raise QuotaPause(None, model.split("/")[0])
    u = getattr(r, "usage", None)
    log("ok", getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
    return r.choices[0].message.content or ""


def _raise_classified(e, model, log):
    if True:
        if "RateLimit" in type(e).__name__ or "429" in str(e) or "413" in str(e):   # Groq: 413 = per-minute token cap
            log("rate_limited")
            hdrs = getattr(getattr(e, "response", None), "headers", None) or {}
            daily = "per day" in str(e).lower() or "PerDay" in str(e)
            retry = hdrs.get("retry-after")
            m = _re.search(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)\b", str(e))   # LiteLLM drops Groq's headers; its message states the wait
            if retry is None and m:
                secs = int(m[1] or 0) * 60 + float(m[2]) / (1000 if m[3] == "ms" else 1)
                retry = str(int(secs) + 1)
            raise QuotaPause(resume_at(_db.now(), retry, daily_quota=daily and model.startswith("gemini")),
                             model.split("/")[0]) from e
        log("error"); raise e
