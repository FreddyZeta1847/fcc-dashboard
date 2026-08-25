"""Unit tests for backend.fcc_dashboard.collector's apply_trace_event."""

import json

import pytest

from fcc_dashboard.collector import apply_trace_event
from fcc_dashboard.db import init_db


@pytest.fixture
def conn():
    return init_db(":memory:")


def _row(conn, request_id):
    return conn.execute(
        "SELECT * FROM requests WHERE request_id = ?", (request_id,)
    ).fetchone()


def test_request_sent_creates_pending_row(conn):
    event = {
        "event": "provider.request.sent",
        "time": "2026-07-16 13:55:49.563956+02:00",
        "request_id": "req_1",
        "provider": "nvidia_nim",
        "gateway_model": "sonnet",
        "downstream_model": "glm-4",
    }
    apply_trace_event(conn, event)
    row = _row(conn, "req_1")
    assert row is not None
    assert row["status"] == "pending"
    assert row["provider"] == "nvidia_nim"
    assert row["gateway_model"] == "sonnet"
    assert row["downstream_model"] == "glm-4"
    assert row["occurred_at"] == "2026-07-16T11:55:49.563Z"
    assert row["occurred_at_is_estimated"] == 0


def test_response_completed_updates_existing_pending_row(conn):
    apply_trace_event(conn, {
        "event": "provider.request.sent",
        "time": "2026-07-16 13:55:49.563956+02:00",
        "request_id": "req_1",
        "provider": "nvidia_nim",
        "gateway_model": "sonnet",
        "downstream_model": "glm-4",
    })
    apply_trace_event(conn, {
        "event": "provider.response.completed",
        "time": "2026-07-16 13:55:52.100000+02:00",
        "request_id": "req_1",
        "finish_reason": "stop",
        "output_tokens": 150,
        "prompt_tokens": 320,
        "prompt_tokens_estimate": 310,
    })
    row = _row(conn, "req_1")
    assert row["status"] == "completed"
    assert row["output_tokens"] == 150
    assert row["input_tokens"] == 320
    assert row["input_tokens_estimate"] == 310
    assert row["finish_reason"] == "stop"
    # occurred_at must stay the request.sent time, NOT the completed time
    assert row["occurred_at"] == "2026-07-16T11:55:49.563Z"
    # provider/gateway_model/downstream_model from request.sent must survive
    assert row["provider"] == "nvidia_nim"
    assert row["gateway_model"] == "sonnet"


def test_transport_error_updates_existing_pending_row(conn):
    apply_trace_event(conn, {
        "event": "provider.request.sent",
        "time": "2026-07-16 13:55:49.563956+02:00",
        "request_id": "req_1",
        "provider": "nvidia_nim",
        "gateway_model": "sonnet",
        "downstream_model": "glm-4",
    })
    apply_trace_event(conn, {
        "event": "provider.response.transport_error",
        "time": "2026-07-16 13:56:00.000000+02:00",
        "request_id": "req_1",
        "http_status": 401,
        "exc_type": "AuthenticationError",
    })
    row = _row(conn, "req_1")
    assert row["status"] == "error"
    assert row["http_status"] == 401
    assert row["exc_type"] == "AuthenticationError"
    assert row["occurred_at"] == "2026-07-16T11:55:49.563Z"


def test_response_completed_without_prior_request_sent_creates_row(conn):
    # Collector's read window missed the request.sent line -- completed
    # event alone must still create a usable row, not be silently dropped.
    apply_trace_event(conn, {
        "event": "provider.response.completed",
        "time": "2026-07-16 13:55:52.100000+02:00",
        "request_id": "req_orphan",
        "finish_reason": "stop",
        "output_tokens": 100,
        "prompt_tokens": 200,
        "prompt_tokens_estimate": 190,
    })
    row = _row(conn, "req_orphan")
    assert row is not None
    assert row["status"] == "completed"
    assert row["output_tokens"] == 100
    assert row["occurred_at"] == "2026-07-16T11:55:52.100Z"


def test_reapplying_same_events_is_idempotent(conn):
    event = {
        "event": "provider.request.sent",
        "time": "2026-07-16 13:55:49.563956+02:00",
        "request_id": "req_1",
        "provider": "nvidia_nim",
        "gateway_model": "sonnet",
        "downstream_model": "glm-4",
    }
    apply_trace_event(conn, event)
    apply_trace_event(conn, event)  # re-applying the same bytes
    apply_trace_event(conn, event)
    count = conn.execute(
        "SELECT COUNT(*) as c FROM requests WHERE request_id = 'req_1'"
    ).fetchone()["c"]
    assert count == 1


def test_unparseable_timestamp_sets_fallback_and_flag(conn):
    apply_trace_event(conn, {
        "event": "provider.request.sent",
        "time": "not a real timestamp",
        "request_id": "req_bad_time",
        "provider": "nvidia_nim",
        "gateway_model": "sonnet",
        "downstream_model": "glm-4",
    })
    row = _row(conn, "req_bad_time")
    assert row["occurred_at_is_estimated"] == 1
    assert row["occurred_at"] is not None  # a real fallback value, not NULL


def test_missing_time_field_sets_fallback_and_flag(conn):
    apply_trace_event(conn, {
        "event": "provider.request.sent",
        "request_id": "req_no_time",
        "provider": "nvidia_nim",
        "gateway_model": "sonnet",
        "downstream_model": "glm-4",
    })
    row = _row(conn, "req_no_time")
    assert row["occurred_at_is_estimated"] == 1
    assert row["occurred_at"] is not None


def test_event_missing_request_id_is_skipped_not_raised(conn):
    # Must not raise, must not insert a row with a NULL/missing primary key.
    apply_trace_event(conn, {
        "event": "provider.request.sent",
        "time": "2026-07-16 13:55:49.563956+02:00",
        "provider": "nvidia_nim",
    })
    count = conn.execute("SELECT COUNT(*) as c FROM requests").fetchone()["c"]
    assert count == 0
