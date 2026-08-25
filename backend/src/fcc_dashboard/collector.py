"""
Trace event upsert into the `requests` table for FCC Dashboard.

FCC's log describes a single request's life as up to three separate JSON
lines (see `log_parser.py`): a "provider.request.sent" line when the
request leaves FCC, followed later by exactly one of
"provider.response.completed" or "provider.response.transport_error" when
the provider answers. Because the collector (Task 4) tails the log file in
chunks and may re-read the same bytes, restart mid-stream, or observe the
lines out of order, `apply_trace_event` treats every event as an *upsert
keyed by `request_id`* rather than a blind insert: applying the same event
twice, or applying the three events for one request in any order, must
converge on the same row (see BACKEND--architecture's write-path section
for why the collector is designed to be idempotent and order-tolerant).

The one invariant this module exists to protect is `occurred_at` — the
"when did this request actually start" timestamp the rest of the dashboard
uses for all time-range filtering and cost aggregation. `occurred_at` is
set exactly once, the first time a request's row is created (by whichever
of the three events happens to arrive first), and is never overwritten by
a later event for the same `request_id`. Each event type's `ON CONFLICT
... DO UPDATE SET` clause is therefore deliberately narrow: it lists only
the columns that specific event is allowed to touch, so a later event can
never clobber data only an earlier event was responsible for (e.g. a
"provider.response.completed" upsert must never overwrite the `provider`/
`gateway_model`/`downstream_model` that only "provider.request.sent"
carries, and vice versa).
"""

import sqlite3
from pathlib import Path

from fcc_dashboard.datetime_utils import (
    now_utc_iso8601,
    parse_fcc_timestamp,
    to_utc_iso8601,
)
from fcc_dashboard.log_parser import parse_log_line

_REQUEST_SENT_SQL = """
INSERT INTO requests (
    request_id, provider, gateway_model, downstream_model,
    occurred_at, occurred_at_is_estimated, ingested_at, status
) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
ON CONFLICT(request_id) DO UPDATE SET
    provider = excluded.provider,
    gateway_model = excluded.gateway_model,
    downstream_model = excluded.downstream_model,
    ingested_at = excluded.ingested_at
"""

_RESPONSE_COMPLETED_SQL = """
INSERT INTO requests (
    request_id, output_tokens, input_tokens, input_tokens_estimate,
    finish_reason, occurred_at, occurred_at_is_estimated, ingested_at, status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed')
ON CONFLICT(request_id) DO UPDATE SET
    output_tokens = excluded.output_tokens,
    input_tokens = excluded.input_tokens,
    input_tokens_estimate = excluded.input_tokens_estimate,
    finish_reason = excluded.finish_reason,
    ingested_at = excluded.ingested_at,
    status = excluded.status
"""

_TRANSPORT_ERROR_SQL = """
INSERT INTO requests (
    request_id, http_status, exc_type,
    occurred_at, occurred_at_is_estimated, ingested_at, status
) VALUES (?, ?, ?, ?, ?, ?, 'error')
ON CONFLICT(request_id) DO UPDATE SET
    http_status = excluded.http_status,
    exc_type = excluded.exc_type,
    ingested_at = excluded.ingested_at,
    status = excluded.status
"""


def _resolve_occurred_at(event: dict) -> tuple[str, int]:
    """Resolve (occurred_at, occurred_at_is_estimated) for one event.

    Implements DATE-TIME--resilience's fallback rule: try the event's own
    "time" field first; fall back to "now" (and flag the row as estimated)
    if that field is missing or unparseable. Never raises.
    """
    raw_time = event.get("time")
    if raw_time is not None:
        try:
            parsed = parse_fcc_timestamp(raw_time)
            return to_utc_iso8601(parsed), 0
        except ValueError:
            pass
    return now_utc_iso8601(), 1


def apply_trace_event(conn: sqlite3.Connection, event: dict) -> None:
    """Upsert one parsed FCC trace event (from `parse_log_line`) into `requests`.

    `event["event"]` is expected to be one of the three trace events
    `parse_log_line` filters for. `event["request_id"]` is expected to
    always be present in practice; if it is ever missing (or empty), the
    event is skipped defensively — no row is inserted, and nothing is
    raised, since a NULL/missing primary key would either violate the
    schema or (worse) silently corrupt an unrelated row.

    Every write commits before returning, so callers (including tests) can
    query `conn` immediately afterward and see the result.
    """
    request_id = event.get("request_id")
    if not request_id:
        return

    ingested_at = now_utc_iso8601()
    occurred_at, occurred_at_is_estimated = _resolve_occurred_at(event)
    event_type = event.get("event")

    if event_type == "provider.request.sent":
        conn.execute(
            _REQUEST_SENT_SQL,
            (
                request_id,
                event.get("provider"),
                event.get("gateway_model"),
                event.get("downstream_model"),
                occurred_at,
                occurred_at_is_estimated,
                ingested_at,
            ),
        )
    elif event_type == "provider.response.completed":
        conn.execute(
            _RESPONSE_COMPLETED_SQL,
            (
                request_id,
                event.get("output_tokens"),
                event.get("prompt_tokens"),
                event.get("prompt_tokens_estimate"),
                event.get("finish_reason"),
                occurred_at,
                occurred_at_is_estimated,
                ingested_at,
            ),
        )
    elif event_type == "provider.response.transport_error":
        conn.execute(
            _TRANSPORT_ERROR_SQL,
            (
                request_id,
                event.get("http_status"),
                event.get("exc_type"),
                occurred_at,
                occurred_at_is_estimated,
                ingested_at,
            ),
        )
    else:
        # parse_log_line only ever produces one of the three events above,
        # but apply_trace_event is a public entry point (backfill/replay
        # tooling may call it directly) -- degrade to a no-op rather than
        # raise on an unrecognized event type.
        return

    conn.commit()


_UPDATE_COLLECTOR_STATE_SQL = """
UPDATE collector_state
SET last_offset = ?, last_known_file_size = ?, last_known_mtime_ns = ?, last_run_at = ?
WHERE id = 1
"""


def poll_once(conn: sqlite3.Connection, log_path: str | Path) -> int:
    """Read whatever new bytes exist in `log_path` since the last poll, apply
    every trace event found, and advance `collector_state` past what was read.

    This is the single "poll tick" unit: a future scheduler calls it once at
    startup (to catch up on everything FCC wrote while the dashboard was
    down) and then again on a timer -- the function itself has no concept of
    "first call" vs. "later call", it just always reconciles the DB's
    recorded read position against the file's current state.

    Truncation/rotation detection (BACKEND--resilience): FCC is a long-running
    process that gets restarted from time to time, and on restart its log
    file is recreated (truncated to empty, or replaced by a new file)
    rather than appended to forever. If the file's current size is
    *smaller* than the size we saw last time, the file we're looking at can't
    be the same one we left off in the middle of -- `last_offset` would point
    past EOF or into unrelated new content. In that case we throw away the
    stale offset and start over from byte 0 instead of trusting it.

    A same-size rewrite is the one case pure size comparison can't catch:
    if the replacement content happens to land on exactly the same byte
    count as before, "size < last_known_file_size" never fires even though
    every byte at `last_offset` is now unrelated new content. The file's
    modification time (`last_known_mtime_ns`) is used as a secondary
    signal for exactly this case: size unchanged but mtime changed, with a
    file we've actually seen data in before, is still treated as a restart.
    Size unchanged *and* mtime unchanged means nothing happened at all
    (the ordinary "polled again, nothing new" case) and is left alone.

    Never raises on a missing file (FCC simply hasn't been run on this
    machine yet) or on any single malformed/unparseable log line -- both are
    treated as "nothing useful here", not as errors.
    """
    log_path = Path(log_path)

    if not log_path.exists():
        # Nothing to read yet, and nothing to conclude about a real file's
        # state -- leave collector_state untouched so a real file appearing
        # later is read from a sensible starting point.
        return 0

    state = conn.execute(
        "SELECT last_offset, last_known_file_size, last_known_mtime_ns "
        "FROM collector_state WHERE id = 1"
    ).fetchone()
    last_offset = state["last_offset"]
    last_known_file_size = state["last_known_file_size"]
    last_known_mtime_ns = state["last_known_mtime_ns"]

    file_stat = log_path.stat()
    current_size = file_stat.st_size
    current_mtime_ns = file_stat.st_mtime_ns

    truncated = current_size < last_known_file_size or (
        current_size == last_known_file_size
        and last_known_file_size > 0
        and current_mtime_ns != last_known_mtime_ns
    )
    start_offset = 0 if truncated else last_offset

    with open(log_path, "rb") as f:
        f.seek(start_offset)
        chunk = f.read()

    applied_count = 0
    bytes_consumed = 0

    if chunk:
        # Only take bytes through the last complete line. A trailing
        # fragment with no "\n" yet is either a torn multi-byte character
        # from reading mid-write, or simply a line the writer hasn't
        # finished -- either way it gets picked up whole on the next poll,
        # rather than risk decoding/parsing a half-written line now.
        last_newline_idx = chunk.rfind(b"\n")
        if last_newline_idx != -1:
            complete_bytes = chunk[: last_newline_idx + 1]
            bytes_consumed = len(complete_bytes)
            try:
                text = complete_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Defensive fallback only: the truncation case above (a
                # multi-byte char split by a mid-write read) can't land
                # here, since anything after the last "\n" was already
                # dropped. This guards against genuinely corrupt bytes
                # inside an otherwise-complete line without ever raising.
                text = complete_bytes.decode("utf-8", errors="replace")

            for line in text.split("\n"):
                if not line:
                    continue
                try:
                    event = parse_log_line(line)
                    if event is not None:
                        apply_trace_event(conn, event)
                        applied_count += 1
                except Exception:
                    # BACKEND--resilience: one bad line must never crash the
                    # collector loop. parse_log_line and apply_trace_event
                    # are each designed to never raise on their own, but
                    # this is the actual backstop the loop relies on (e.g.
                    # a "time" field that's a JSON number instead of a
                    # string would otherwise raise a TypeError out of
                    # apply_trace_event's timestamp parsing) -- skip the
                    # offending line and keep going.
                    continue

    new_offset = start_offset + bytes_consumed

    conn.execute(
        _UPDATE_COLLECTOR_STATE_SQL,
        (new_offset, current_size, current_mtime_ns, now_utc_iso8601()),
    )
    conn.commit()

    return applied_count
