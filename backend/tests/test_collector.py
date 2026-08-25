"""Unit tests for backend.fcc_dashboard.collector's apply_trace_event."""

import asyncio
import builtins
import contextlib
import json
import sqlite3
from pathlib import Path

import pytest

import fcc_dashboard.collector as collector_module
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
        # Deliberately a DIFFERENT provider value than request.sent's, to
        # confirm the completed upsert's `COALESCE(provider,
        # excluded.provider)` never overwrites an already-known provider --
        # it only ever fills in a NULL. If this leaked through, the assertion below
        # would see "some_other_provider" instead of "nvidia_nim".
        "provider": "some_other_provider",
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
    # unchanged -- the completed event's own (different) provider must NOT
    # clobber it.
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
        "provider": "nvidia_nim",
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
    # No prior request.sent row existed to set provider -- the orphan path
    # must rescue it from the completed event itself rather than leave it
    # NULL, since completed events DO carry a "provider" field in FCC's
    # real logs.
    assert row["provider"] == "nvidia_nim"


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
    # Note: req_1's and req_2's lines below are, by construction, exactly
    # the same byte length -- this specifically exercises the case pure
    # size comparison cannot catch (current_size == last_known_file_size
    # after the restart, so a naive "size shrank" check never fires). The
    # head-fingerprint hash is what has to catch this one.
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

    # Simulate FCC restarting: log file truncated and replaced with new
    # content of the exact same size (not smaller -- see note above).
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


def test_poll_once_detects_truncation_when_new_content_is_larger(conn, tmp_path):
    # A restart doesn't just shrink or preserve the file's size -- FCC
    # could easily have logged a lot more before this poll ever ran (e.g.
    # the dashboard was offline for a while, FCC kept writing, then also
    # restarted). The new file here is deliberately much larger than the
    # old one, which a plain "size < last_known_file_size" check would
    # read as ordinary growth, not a restart.
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
    poll_once(conn, log_path)  # last_offset now points past this one short line

    # Simulate FCC restarting after logging a lot more than before --
    # several lines, comfortably larger than the original file.
    _write_log(log_path, [
        json.dumps({
            "event": "provider.request.sent",
            "time": "2026-08-01 09:00:00.000000+02:00",
            "request_id": f"req_new_{i}",
            "provider": "openrouter",
            "gateway_model": "opus",
            "downstream_model": "kimi-k2",
        })
        for i in range(5)
    ])
    count = poll_once(conn, log_path)
    assert count == 5  # all 5 new-generation lines, not zero and not a partial re-read
    for i in range(5):
        row = _row(conn, f"req_new_{i}")
        assert row is not None
        assert row["provider"] == "openrouter"
    # req_1's row from before the restart is untouched history (the
    # collector never deletes rows) -- it must still have its original
    # provider, not something corrupted by misreading the new file at the
    # old (now-meaningless) byte offset.
    old_row = _row(conn, "req_1")
    assert old_row is not None
    assert old_row["provider"] == "nvidia_nim"


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


def test_poll_once_does_not_swallow_real_database_errors(conn, tmp_path, monkeypatch):
    # The per-line guard exists to skip a BAD LINE, not to hide a broken
    # database. A real infrastructure failure (sqlite3.Error and
    # subclasses -- e.g. a locked database) must propagate out of
    # poll_once, not be silently caught alongside malformed-data errors
    # like a bad "time" field. Simulate this by making apply_trace_event
    # itself raise a genuine sqlite3 error and confirming it is NOT
    # swallowed.
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

    def _boom(_conn, _event):
        raise sqlite3.OperationalError("simulated database error")

    monkeypatch.setattr(collector_module, "apply_trace_event", _boom)

    with pytest.raises(sqlite3.OperationalError):
        poll_once(conn, log_path)

    # Since the DB error aborted the poll before the collector_state
    # UPDATE ran, last_offset must still be at its original value (0) --
    # the next poll will naturally retry this same line, not skip it.
    state = conn.execute(
        "SELECT last_offset FROM collector_state WHERE id = 1"
    ).fetchone()
    assert state["last_offset"] == 0


def test_poll_once_end_to_end_with_real_fcc_log_shape(conn, tmp_path):
    # Uses FCC's REAL log-line shape (level/trace/etc. beyond the bare
    # minimum, matching test_log_parser.py's REQUEST_SENT_LINE /
    # RESPONSE_COMPLETED_LINE fixtures), driven through the real
    # parse_log_line -> apply_trace_event pipeline via poll_once -- not a
    # hand-built dict passed straight to apply_trace_event. This is the
    # integration seam a unit test against apply_trace_event alone can't
    # cover: it specifically confirms the plan's documented field-name
    # "trap" (prompt_tokens -> input_tokens, prompt_tokens_estimate ->
    # input_tokens_estimate) survives the real parsing step too.
    log_path = tmp_path / "server.log"
    _write_log(log_path, [
        json.dumps({
            "time": "2026-07-16 13:55:49.563956+02:00",
            "level": "DEBUG",
            "event": "provider.request.sent",
            "trace": True,
            "request_id": "req_abc123",
            "provider": "nvidia_nim",
            "gateway_model": "sonnet",
            "downstream_model": "glm-4",
        }),
        json.dumps({
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
        }),
    ])

    count = poll_once(conn, log_path)

    assert count == 2
    row = _row(conn, "req_abc123")
    assert row is not None
    assert row["status"] == "completed"
    assert row["provider"] == "nvidia_nim"
    assert row["gateway_model"] == "sonnet"
    assert row["downstream_model"] == "glm-4"
    assert row["finish_reason"] == "stop"
    assert row["output_tokens"] == 150
    # The plan's documented "trap": FCC's completed line names these
    # fields prompt_tokens/prompt_tokens_estimate, but the requests table
    # (and the rest of the dashboard) names them input_tokens/
    # input_tokens_estimate.
    assert row["input_tokens"] == 320
    assert row["input_tokens_estimate"] == 310
    assert row["occurred_at"] == "2026-07-16T11:55:49.563Z"
    assert row["occurred_at_is_estimated"] == 0


def test_poll_once_survives_non_string_time_field(conn, tmp_path):
    # Watch item from Task 3's review: does poll_once's line loop actually
    # guard against apply_trace_event raising at all (not just
    # parse_log_line returning None)? A "time" value that's a JSON number
    # instead of a string is valid JSON and a relevant event, so it sails
    # through parse_log_line -- the failure mode this guards is internal to
    # timestamp parsing. This must not raise out of poll_once, and it must
    # not stall the collector (processing must continue past this line to
    # the next one, with last_offset actually advancing).
    log_path = tmp_path / "server.log"
    _write_log(log_path, [
        json.dumps({
            "event": "provider.request.sent",
            "time": 1234567890,  # a JSON number, not a string
            "request_id": "req_bad_time_type",
            "provider": "nvidia_nim",
            "gateway_model": "sonnet",
            "downstream_model": "glm-4",
        }),
        json.dumps({
            "event": "provider.request.sent",
            "time": "2026-08-01 09:00:00.000000+02:00",
            "request_id": "req_after",
            "provider": "openrouter",
            "gateway_model": "opus",
            "downstream_model": "kimi-k2",
        }),
    ])

    count = poll_once(conn, log_path)

    # Both lines processed: the bad-time-type line falls back to "now"
    # (estimated) rather than raising, and the loop keeps going to the
    # next line instead of stalling on it.
    assert count == 2
    bad_row = _row(conn, "req_bad_time_type")
    assert bad_row is not None
    assert bad_row["occurred_at_is_estimated"] == 1
    assert bad_row["occurred_at"] is not None
    after_row = _row(conn, "req_after")
    assert after_row is not None

    # last_offset must have advanced past both lines, not be stuck at 0.
    state = conn.execute(
        "SELECT last_offset FROM collector_state WHERE id = 1"
    ).fetchone()
    assert state["last_offset"] == log_path.stat().st_size


def test_poll_once_skips_oversized_line_and_advances_offset(
    conn, tmp_path, monkeypatch, caplog
):
    # Guard against a single line larger than _MAX_READ_BYTES: the capped
    # chunk then contains no newline at all, which must not be confused
    # with the ordinary "legitimately reached EOF mid-line" case (a short
    # chunk that's also missing a newline). Use a small test-only override
    # of _MAX_READ_BYTES so the test stays fast instead of writing a real
    # multi-megabyte fixture.
    monkeypatch.setattr(collector_module, "_MAX_READ_BYTES", 50)

    log_path = tmp_path / "server.log"
    # One single "line" with no newline anywhere, comfortably longer than
    # two capped reads -- so we can observe last_offset actually advancing
    # across polls instead of getting stuck re-reading byte 0 forever.
    log_path.write_bytes(b"x" * 130)

    with caplog.at_level("WARNING"):
        first_count = poll_once(conn, log_path)
    assert first_count == 0  # the oversized fragment was skipped, not parsed
    assert any("oversized" in record.message.lower() for record in caplog.records)

    state_after_first = conn.execute(
        "SELECT last_offset FROM collector_state WHERE id = 1"
    ).fetchone()
    assert state_after_first["last_offset"] == 50  # advanced past the cap, not stuck at 0

    caplog.clear()
    second_count = poll_once(conn, log_path)
    assert second_count == 0
    state_after_second = conn.execute(
        "SELECT last_offset FROM collector_state WHERE id = 1"
    ).fetchone()
    # Offset keeps advancing on every poll -- never gets stuck re-reading
    # the same oversized fragment forever.
    assert state_after_second["last_offset"] == 100
    assert state_after_second["last_offset"] > state_after_first["last_offset"]


def test_poll_once_returns_zero_on_oserror(conn, tmp_path, monkeypatch, caplog):
    # The exists() -> stat() -> open() sequence has a TOCTOU (time-of-check
    # -to-time-of-use) gap: the file could be deleted/rotated, or briefly
    # locked, between those calls. Simulate that by making the *open* of
    # this specific file raise OSError -- unlike patching stat() directly,
    # this doesn't also break the earlier exists() check (which itself
    # calls stat() internally), so it cleanly isolates the guard this test
    # is actually after: does poll_once degrade to "nothing to read this
    # tick" instead of raising once it's past the exists() gate?
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

    real_open = builtins.open

    def _flaky_open(file, mode="r", *args, **kwargs):
        if "b" in mode and Path(file) == log_path:
            raise OSError("simulated transient filesystem error")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _flaky_open)

    with caplog.at_level("WARNING"):
        count = poll_once(conn, log_path)

    assert count == 0
    assert any("filesystem error" in record.message.lower() for record in caplog.records)

    # collector_state must be untouched -- next poll retries cleanly.
    state = conn.execute(
        "SELECT last_offset FROM collector_state WHERE id = 1"
    ).fetchone()
    assert state["last_offset"] == 0


def test_run_collector_loop_polls_immediately_and_again_after_interval(monkeypatch, tmp_path):
    call_count = 0

    def fake_poll_once(conn, log_path):
        nonlocal call_count
        call_count += 1
        return 0

    monkeypatch.setattr(collector_module, "poll_once", fake_poll_once)
    monkeypatch.setattr(collector_module, "get_fcc_log_path", lambda: tmp_path / "server.log")

    db = init_db(":memory:")

    async def run():
        task = asyncio.create_task(collector_module.run_collector_loop(db, interval=0.01))
        await asyncio.sleep(0.035)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())

    # At interval=0.01s over ~0.035s: one immediate call plus at least
    # two more ticks -- assert loosely (>= 2) to avoid timing flakiness,
    # but this must be strictly more than 1 to prove the loop actually
    # re-polls on a timer, not just once at startup.
    assert call_count >= 2


def test_run_collector_loop_survives_poll_once_exception_and_logs_it(
    monkeypatch, tmp_path, caplog
):
    # Finding 1 (final review): a genuine exception out of poll_once (e.g. a
    # momentarily locked database) must not kill the loop's task -- it must
    # be logged loudly and the loop must keep polling on the next tick,
    # instead of collection silently and permanently stopping.
    call_count = 0

    def flaky_poll_once(conn, log_path):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise sqlite3.OperationalError("simulated locked database")
        return 0

    log_path = tmp_path / "server.log"
    monkeypatch.setattr(collector_module, "poll_once", flaky_poll_once)
    monkeypatch.setattr(collector_module, "get_fcc_log_path", lambda: log_path)

    db = init_db(":memory:")

    async def run():
        task = asyncio.create_task(collector_module.run_collector_loop(db, interval=0.01))
        await asyncio.sleep(0.035)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    with caplog.at_level("ERROR"):
        asyncio.run(run())

    # The loop must have survived the first call's exception and kept
    # polling on subsequent ticks -- not died after the first call.
    assert call_count >= 2

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) >= 1
    # Mentions the log path being polled, and actually carries the real
    # exception (via logging.exception's exc_info), not just a bare "it
    # failed" message with no evidence of what failed.
    assert any(str(log_path) in r.getMessage() for r in error_records)
    assert any(r.exc_info is not None for r in error_records)


def test_run_collector_loop_can_be_cancelled_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(collector_module, "poll_once", lambda conn, log_path: 0)
    monkeypatch.setattr(collector_module, "get_fcc_log_path", lambda: tmp_path / "server.log")
    db = init_db(":memory:")

    async def run():
        task = asyncio.create_task(collector_module.run_collector_loop(db, interval=0.01))
        await asyncio.sleep(0.02)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert task.cancelled() or task.done()

    asyncio.run(run())
