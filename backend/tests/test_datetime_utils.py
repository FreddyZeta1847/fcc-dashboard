"""Unit tests for backend.fcc_dashboard.datetime_utils."""

from datetime import datetime, timezone

import pytest

from fcc_dashboard.datetime_utils import (
    now_utc_iso8601,
    parse_fcc_timestamp,
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
