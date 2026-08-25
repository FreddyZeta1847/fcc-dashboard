"""Unit tests for backend.fcc_dashboard.log_parser."""

import json

from fcc_dashboard.log_parser import parse_log_line

REQUEST_SENT_LINE = json.dumps({
    "time": "2026-07-16 13:55:49.563956+02:00",
    "level": "DEBUG",
    "event": "provider.request.sent",
    "trace": True,
    "request_id": "req_abc123",
    "provider": "nvidia_nim",
    "gateway_model": "sonnet",
    "downstream_model": "glm-4",
})

RESPONSE_COMPLETED_LINE = json.dumps({
    "time": "2026-07-16 13:55:52.100000+02:00",
    "level": "DEBUG",
    "event": "provider.response.completed",
    "trace": True,
    "request_id": "req_abc123",
    "provider": "nvidia_nim",
    "finish_reason": "stop",
    "output_tokens": 150,
    "prompt_tokens": 320,
    "prompt_tokens_estimate": 310,
})

TRANSPORT_ERROR_LINE = json.dumps({
    "time": "2026-07-16 13:56:00.000000+02:00",
    "level": "ERROR",
    "event": "provider.response.transport_error",
    "trace": True,
    "request_id": "req_xyz789",
    "http_status": 401,
    "exc_type": "AuthenticationError",
})

IRRELEVANT_TRACE_LINE = json.dumps({
    "time": "2026-07-16 13:55:48.000000+02:00",
    "level": "DEBUG",
    "event": "api.route.resolved",
    "trace": True,
    "provider_id": "nvidia_nim",
})

STARTUP_LOG_LINE = json.dumps({
    "time": "2026-07-16 13:55:49.688943+02:00",
    "level": "INFO",
    "message": "Starting Claude Code Proxy...",
    "module": "api.runtime",
    "function": "startup",
    "line": 104,
})


def test_parses_request_sent_line():
    result = parse_log_line(REQUEST_SENT_LINE)
    assert result is not None
    assert result["event"] == "provider.request.sent"
    assert result["request_id"] == "req_abc123"


def test_parses_response_completed_line():
    result = parse_log_line(RESPONSE_COMPLETED_LINE)
    assert result is not None
    assert result["event"] == "provider.response.completed"
    assert result["output_tokens"] == 150


def test_parses_transport_error_line():
    result = parse_log_line(TRANSPORT_ERROR_LINE)
    assert result is not None
    assert result["event"] == "provider.response.transport_error"
    assert result["http_status"] == 401


def test_ignores_irrelevant_trace_event():
    assert parse_log_line(IRRELEVANT_TRACE_LINE) is None


def test_ignores_non_trace_log_line():
    assert parse_log_line(STARTUP_LOG_LINE) is None


def test_ignores_blank_line():
    assert parse_log_line("") is None
    assert parse_log_line("   \n") is None


def test_ignores_malformed_json_without_raising():
    assert parse_log_line("{not valid json") is None
    assert parse_log_line("this is not json at all") is None


def test_ignores_valid_json_that_is_not_an_object():
    assert parse_log_line("[1, 2, 3]") is None
    assert parse_log_line('"just a string"') is None
    assert parse_log_line("42") is None


def test_ignores_json_object_with_no_event_key():
    assert parse_log_line(json.dumps({"foo": "bar"})) is None


def test_ignores_non_string_event_value_without_raising():
    # Regression test: an "event" value that isn't a string (a list, a
    # dict, a number, a bool, or null) previously crashed the membership
    # check with `TypeError: unhashable type` for the list/dict cases,
    # because `value not in a_set` must hash `value` first. This must
    # degrade to None like any other irrelevant line, never raise.
    assert parse_log_line(json.dumps({"event": ["provider.request.sent"]})) is None
    assert parse_log_line(json.dumps({"event": {"nested": "value"}})) is None
    assert parse_log_line(json.dumps({"event": 42})) is None
    assert parse_log_line(json.dumps({"event": None})) is None
    assert parse_log_line(json.dumps({"event": True})) is None
