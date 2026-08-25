"""Unit tests for backend.fcc_dashboard.datetime_utils."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from fcc_dashboard.datetime_utils import (
    local_date_of,
    now_utc_iso8601,
    parse_fcc_timestamp,
    resolve_range_boundaries,
    to_utc_iso8601,
)


def test_parse_fcc_timestamp_with_offset():
    dt = parse_fcc_timestamp("2026-07-16 13:55:49.563956+02:00")
    assert dt.year == 2026
    assert dt.month == 7
    assert dt.day == 16
    assert dt.hour == 13
    assert dt.minute == 55
    assert dt.second == 49
    assert dt.utcoffset().total_seconds() == 2 * 3600


def test_parse_fcc_timestamp_rejects_malformed_input():
    with pytest.raises(ValueError):
        parse_fcc_timestamp("not a timestamp")


def test_parse_fcc_timestamp_rejects_empty_string():
    with pytest.raises(ValueError):
        parse_fcc_timestamp("")


def test_parse_fcc_timestamp_rejects_date_only_string():
    with pytest.raises(ValueError):
        parse_fcc_timestamp("2026-07-16")


def test_parse_fcc_timestamp_rejects_offsetless_datetime():
    with pytest.raises(ValueError):
        parse_fcc_timestamp("2026-07-16 13:55:49.563956")


def test_to_utc_iso8601_converts_offset_to_utc_with_z_suffix():
    dt = datetime(2026, 7, 16, 13, 55, 49, 563000, tzinfo=timezone.utc)
    # 13:55:49 UTC+2 == 11:55:49 UTC
    from datetime import timedelta

    dt_plus_2 = dt.replace(tzinfo=timezone(timedelta(hours=2)))
    result = to_utc_iso8601(dt_plus_2)
    assert result == "2026-07-16T11:55:49.563Z"


def test_to_utc_iso8601_rejects_naive_datetime():
    naive = datetime(2026, 7, 16, 13, 55, 49)
    with pytest.raises(ValueError):
        to_utc_iso8601(naive)


def test_now_utc_iso8601_format():
    result = now_utc_iso8601()
    # Format check: YYYY-MM-DDTHH:MM:SS.mmmZ (24 chars exactly)
    assert len(result) == 24
    assert result[10] == "T"
    assert result.endswith("Z")
    # Round-trips through parse_fcc_timestamp without raising
    parsed = parse_fcc_timestamp(result.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_resolve_range_boundaries_today():
    # Fixed "now": 2026-08-24 15:30:00 in Europe/Rome (UTC+2 in August, DST)
    fixed_now = datetime(2026, 8, 24, 15, 30, 0, tzinfo=ZoneInfo("Europe/Rome"))
    start, end = resolve_range_boundaries("today", local_tz="Europe/Rome", now=fixed_now)
    # Local midnight 2026-08-24 00:00:00+02:00 -> UTC 2026-08-23T22:00:00.000Z
    assert start == "2026-08-23T22:00:00.000Z"
    # End is "now" itself, normalized to UTC
    assert end == "2026-08-24T13:30:00.000Z"


def test_resolve_range_boundaries_last_7_days():
    fixed_now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=ZoneInfo("Europe/Rome"))
    start, end = resolve_range_boundaries("last_7_days", local_tz="Europe/Rome", now=fixed_now)
    # 7 days back from local midnight of "today"
    assert start == "2026-08-16T22:00:00.000Z"
    assert end == "2026-08-24T10:00:00.000Z"


def test_resolve_range_boundaries_last_30_days():
    fixed_now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=ZoneInfo("Europe/Rome"))
    start, end = resolve_range_boundaries("last_30_days", local_tz="Europe/Rome", now=fixed_now)
    assert start == "2026-07-24T22:00:00.000Z"
    assert end == "2026-08-24T10:00:00.000Z"


def test_resolve_range_boundaries_all_time():
    fixed_now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=ZoneInfo("Europe/Rome"))
    start, end = resolve_range_boundaries("all_time", local_tz="Europe/Rome", now=fixed_now)
    # "all_time" start is a fixed epoch far in the past (project inception),
    # not computed relative to now.
    assert start == "1970-01-01T00:00:00.000Z"
    assert end == "2026-08-24T10:00:00.000Z"


def test_resolve_range_boundaries_rejects_unknown_range():
    with pytest.raises(ValueError):
        resolve_range_boundaries("last_fortnight")


def test_resolve_range_boundaries_uses_real_local_time_by_default():
    # No overrides: must not raise, must return two valid ISO-8601 UTC strings
    # where start <= end.
    start, end = resolve_range_boundaries("today")
    assert start <= end
    assert start.endswith("Z")
    assert end.endswith("Z")


def test_local_zone_returns_real_zoneinfo():
    from fcc_dashboard.datetime_utils import _local_zone

    zone = _local_zone()
    assert isinstance(zone, ZoneInfo)


def test_resolve_range_boundaries_last_30_days_crosses_dst_boundary():
    # 2026-11-10 is CET (UTC+1) in Europe/Rome; 30 days earlier (2026-10-11)
    # was still CEST (UTC+2) -- these differ. A fixed-offset implementation
    # would incorrectly use +1 for both; the correct implementation must
    # use +2 for the historical date. This is the exact bug class the
    # Phase 1 review caught -- this test would have failed under the old
    # fixed-offset code and must keep passing under the fix.
    fixed_now = datetime(2026, 11, 10, 12, 0, 0, tzinfo=ZoneInfo("Europe/Rome"))
    start, end = resolve_range_boundaries("last_30_days", local_tz="Europe/Rome", now=fixed_now)
    assert start == "2026-10-10T22:00:00.000Z"  # local midnight Oct 11 CEST(+2) -> UTC
    assert end == "2026-11-10T11:00:00.000Z"  # CET(+1) -> UTC


def test_local_date_of_same_day_in_utc_and_local():
    # 14:00 UTC on Aug 24, in Europe/Rome (+2 in summer) is still Aug 24.
    assert local_date_of("2026-08-24T14:00:00.000Z", local_tz="Europe/Rome") == "2026-08-24"


def test_local_date_of_rolls_over_to_next_local_day():
    # 23:30 UTC is 01:30 the *next* local day in Europe/Rome (+2 in summer)
    # -- this is exactly the case a naive "just take the UTC date" bug would
    # get wrong, and the case daily bucketing depends on getting right.
    assert local_date_of("2026-08-24T23:30:00.000Z", local_tz="Europe/Rome") == "2026-08-25"


def test_local_date_of_crosses_dst_boundary():
    # Same reasoning as test_resolve_range_boundaries_last_30_days_crosses_dst_boundary:
    # 22:30 UTC on Oct 10 is CEST(+2) in Europe/Rome -> Oct 11 local, but the
    # same UTC clock time a month later (post-DST, CET+1) would NOT roll
    # over -- a fixed-offset implementation would get one of these two wrong.
    assert local_date_of("2026-10-10T22:30:00.000Z", local_tz="Europe/Rome") == "2026-10-11"
    assert local_date_of("2026-11-10T22:30:00.000Z", local_tz="Europe/Rome") == "2026-11-10"


def test_local_date_of_uses_real_local_time_by_default():
    # No override: must not raise, must return a real YYYY-MM-DD string.
    result = local_date_of(now_utc_iso8601())
    assert len(result) == 10
    assert result[4] == "-" and result[7] == "-"
