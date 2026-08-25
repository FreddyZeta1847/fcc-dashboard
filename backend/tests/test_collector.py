"""Unit tests for backend.fcc_dashboard.collector's apply_trace_event."""

import json

import pytest

from fcc_dashboard.collector import apply_trace_event, poll_once
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


def _write_log(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_poll_once_reads_new_lines_and_applies_them(conn, tmp_path):
    log_path = tmp_path / "server.log"
    _write_log(log_path, [
        json.dumps({
            "event": "provider.request.sent",
            "time": "2026-07-16 13:55:49.563956+02:00",
            "request_id": "req_1",
            "provider": "nvidia_nim",
            "gateway_model": "sonnet",
            "downstream_model": "glm-4",
        }),
        json.dumps({
            "event": "provider.response.completed",
            "time": "2026-07-16 13:55:52.100000+02:00",
            "request_id": "req_1",
            "finish_reason": "stop",
            "output_tokens": 150,
            "prompt_tokens": 320,
            "prompt_tokens_estimate": 310,
        }),
    ])
    count = poll_once(conn, log_path)
    assert count == 2
    row = _row(conn, "req_1")
    assert row["status"] == "completed"


def test_poll_once_is_incremental_no_duplicate_reprocessing(conn, tmp_path):
    log_path = tmp_path / "server.log"
    _write_log(log_path, [
        json.dumps({
            "event": "provider.request.sent",
            "time": "2026-07-16 13:55:49.563956+02:00",
            "request_id": "req_1",
            "provider": "nvidia_nim",
            "gateway_model": "sonnet",
            "downstream_model": "glm-4",
        }),
    ])
    first_count = poll_once(conn, log_path)
    assert first_count == 1

    second_count_no_new_data = poll_once(conn, log_path)
    assert second_count_no_new_data == 0  # nothing new since last_offset

    # simulate FCC appending a new line
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "event": "provider.response.completed",
            "time": "2026-07-16 13:55:52.100000+02:00",
            "request_id": "req_1",
            "finish_reason": "stop",
            "output_tokens": 150,
            "prompt_tokens": 320,
            "prompt_tokens_estimate": 310,
        }) + "\n")

    third_count = poll_once(conn, log_path)
    assert third_count == 1  # only the newly appended line
    row = _row(conn, "req_1")
    assert row["status"] == "completed"


def test_poll_once_returns_zero_when_file_does_not_exist(conn, tmp_path):
    missing_path = tmp_path / "does_not_exist.log"
    count = poll_once(conn, missing_path)
    assert count == 0


def test_poll_once_detects_truncation_and_rereads_from_start(conn, tmp_path):
    log_path = tmp_path / "server.log"
    _write_log(log_path, [
        json.dumps({
            "event": "provider.request.sent",
            "time": "2026-07-16 13:55:49.563956+02:00",
            "request_id": "req_1",
            "provider": "nvidia_nim",
            "gateway_model": "sonnet",
            "downstream_model": "glm-4",
        }),
    ])
    poll_once(conn, log_path)  # last_offset now points past this line

    # Simulate FCC restarting: log file truncated and replaced with new content
    _write_log(log_path, [
        json.dumps({
            "event": "provider.request.sent",
            "time": "2026-08-01 09:00:00.000000+02:00",
            "request_id": "req_2",
            "provider": "openrouter",
            "gateway_model": "opus",
            "downstream_model": "kimi-k2",
        }),
    ])
    count = poll_once(conn, log_path)
    assert count == 1
    row = _row(conn, "req_2")
    assert row is not None
    assert row["provider"] == "openrouter"


def test_poll_once_skips_malformed_and_irrelevant_lines_without_crashing(conn, tmp_path):
    log_path = tmp_path / "server.log"
    _write_log(log_path, [
        "{not valid json at all",
        json.dumps({"event": "api.route.resolved", "provider_id": "nvidia_nim"}),
        json.dumps({
            "event": "provider.request.sent",
            "time": "2026-07-16 13:55:49.563956+02:00",
            "request_id": "req_1",
            "provider": "nvidia_nim",
            "gateway_model": "sonnet",
            "downstream_model": "glm-4",
        }),
    ])
    count = poll_once(conn, log_path)
    assert count == 1  # only the one real trace event
    row = _row(conn, "req_1")
    assert row is not None
