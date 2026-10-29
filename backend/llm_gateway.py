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
