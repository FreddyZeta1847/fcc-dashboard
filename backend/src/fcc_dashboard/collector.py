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

from fcc_dashboard.datetime_utils import (
    now_utc_iso8601,
    parse_fcc_timestamp,
    to_utc_iso8601,
)

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
