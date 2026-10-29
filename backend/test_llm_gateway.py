"""Pause maths for provider 429s: contracts.md:248 and B06.

`resume_at` is set only from a provider's `Retry-After` or a documented reset
time (for Gemini's free tier, midnight Pacific). Anything else is null, and
the UI says "until capacity is available" — never a guessed time.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from backend.llm_gateway import next_midnight_pacific, parse_retry_after, resume_at

PACIFIC = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)  # 11:00 PDT


# --- parse_retry_after ----------------------------------------------------


def test_delay_seconds():
    assert parse_retry_after("3600", NOW) == NOW + timedelta(seconds=3600)


def test_delay_seconds_with_whitespace():
    assert parse_retry_after(" 30 ", NOW) == NOW + timedelta(seconds=30)


def test_zero_seconds_is_now():
    assert parse_retry_after("0", NOW) == NOW


def test_http_date():
    assert parse_retry_after("Fri, 30 Oct 2026 19:30:00 GMT", NOW) == datetime(
        2026, 10, 30, 19, 30, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "soon",
        "-5",  # a negative delay is not a time
        "Fri, 30 Oct 2026 17:00:00 GMT",  # already past
        "Thu, 32 Oct 2026 19:00:00 GMT",  # unparseable date
        "1e3",
    ],
)
def test_unusable_values_are_none(value):
    assert parse_retry_after(value, NOW) is None


def test_absurd_delay_is_still_reported_truthfully():
    # Clamping belongs to max_pause_seconds at the call site, not here.
    assert parse_retry_after("86400", NOW) == NOW + timedelta(days=1)


# --- next_midnight_pacific ------------------------------------------------


def test_next_midnight_during_pdt():
    assert next_midnight_pacific(NOW) == datetime(2026, 10, 31, 0, 0, tzinfo=PACIFIC)


def test_next_midnight_crossing_the_dst_fall_back():
    # 2026-11-01 is the PDT -> PST switch; the night before must not skip a day.
    late_oct_31 = datetime(2026, 10, 31, 20, 0, tzinfo=PACIFIC)
    assert next_midnight_pacific(late_oct_31) == datetime(2026, 11, 1, 0, 0, tzinfo=PACIFIC)


def test_next_midnight_after_the_switch_is_pst():
    after = datetime(2026, 11, 1, 12, 0, tzinfo=PACIFIC)
    result = next_midnight_pacific(after)
    assert result == datetime(2026, 11, 2, 0, 0, tzinfo=PACIFIC)
    assert result.utcoffset() == timedelta(hours=-8)


def test_exactly_midnight_pacific_gives_the_next_one():
    midnight = datetime(2026, 10, 31, 0, 0, tzinfo=PACIFIC)
    assert next_midnight_pacific(midnight) == datetime(2026, 11, 1, 0, 0, tzinfo=PACIFIC)


def test_result_is_always_in_the_future():
    assert next_midnight_pacific(NOW) > NOW


# --- resume_at ------------------------------------------------------------


def test_retry_after_wins_over_the_daily_reset():
    assert resume_at(NOW, retry_after="60", daily_quota=True) == NOW + timedelta(seconds=60)


def test_daily_quota_without_a_header_uses_midnight_pacific():
    assert resume_at(NOW, daily_quota=True) == next_midnight_pacific(NOW)


def test_unusable_header_falls_back_to_the_daily_reset():
    assert resume_at(NOW, retry_after="soon", daily_quota=True) == next_midnight_pacific(NOW)


def test_no_header_and_no_documented_reset_is_null():
    # The contract forbids guessing: null means "until capacity is available".
    assert resume_at(NOW) is None
    assert resume_at(NOW, retry_after=None, daily_quota=False) is None


def test_unusable_header_and_no_daily_quota_is_null():
    assert resume_at(NOW, retry_after="soon") is None
