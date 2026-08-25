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

import hashlib
import logging
import sqlite3
from pathlib import Path

from fcc_dashboard.datetime_utils import (
    now_utc_iso8601,
    parse_fcc_timestamp,
    to_utc_iso8601,
)
from fcc_dashboard.log_parser import parse_log_line

logger = logging.getLogger(__name__)

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
SET last_offset = ?, last_known_file_size = ?, last_known_head_hash = ?, last_run_at = ?
WHERE id = 1
"""

# How many leading bytes of the log file we fingerprint for truncation
# detection. Large enough that two genuinely different files essentially
# never collide by chance (SHA-256 over a couple hundred bytes of real
# JSON content), small enough to read on every single poll without it
# mattering performance-wise.
_HEAD_FINGERPRINT_BYTES = 256


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    rather than appended to forever. Whenever that happens, `last_offset`
    can no longer be trusted -- it might point past EOF, or (worse) land
    at a byte position that just happens to still exist in the new file
    but no longer means what it used to.

    Comparing file *size* alone cannot detect this reliably: a restart's
    replacement content could come out smaller (the naive case), the exact
    same size (size comparison alone would see no change at all), or even
    *larger* than before (very plausible here -- e.g. the dashboard was
    offline for a while, FCC kept logging, then also restarted; the new
    file can easily already exceed the old recorded size by the time the
    next poll runs). None of those three outcomes is reliably distinguishable
    from ordinary incremental growth using size or mtime alone.

    Instead, `collector_state.last_known_head_hash` stores a SHA-256
    fingerprint of the file's leading `_HEAD_FINGERPRINT_BYTES` bytes.
    Because FCC only ever *appends* to a live log, those leading bytes are
    invariant under normal growth -- an append can never change what's
    already at the start of the file. So if the file's current leading
    bytes hash differently than what we fingerprinted last time, the file
    beneath `last_offset` isn't a continuation of what we were reading --
    it was truncated and replaced -- regardless of whether the new size is
    smaller, equal, or larger. Reset `last_offset` to 0 in that case.

    One subtlety: while the file is still shorter than
    `_HEAD_FINGERPRINT_BYTES`, its "leading bytes" are just the whole file,
    and legitimate appends *do* grow that window (there's more file to
    read now). To stay append-safe during this ramp-up phase, the
    comparison only ever looks at `min(last_known_file_size,
    _HEAD_FINGERPRINT_BYTES)` bytes -- i.e. only the portion of the file
    that was already there last time we looked, which pure appends can
    never change. Once the file has grown past `_HEAD_FINGERPRINT_BYTES`,
    that window is pinned at exactly `_HEAD_FINGERPRINT_BYTES` and never
    changes again, which is the simple "fingerprint of the first N bytes"
    picture in steady state.

    Never raises on a missing file (FCC simply hasn't been run on this
    machine yet). Never lets a single malformed/unprocessable log line
    abort the poll -- see the per-line loop below for exactly which
    failures are treated that way and which are allowed to propagate.
    """
    log_path = Path(log_path)

    if not log_path.exists():
        # Nothing to read yet, and nothing to conclude about a real file's
        # state -- leave collector_state untouched so a real file appearing
        # later is read from a sensible starting point.
        return 0

    state = conn.execute(
        "SELECT last_offset, last_known_file_size, last_known_head_hash "
        "FROM collector_state WHERE id = 1"
    ).fetchone()
    last_offset = state["last_offset"]
    last_known_file_size = state["last_known_file_size"]
    last_known_head_hash = state["last_known_head_hash"]

    current_size = log_path.stat().st_size
    with open(log_path, "rb") as f:
        head_bytes = f.read(_HEAD_FINGERPRINT_BYTES)
    # Bound the hashed region to current_size: a writer appending between the
    # stat() above and this read can make head_bytes longer than current_size
    # while the file is still under the fingerprint window, which would
    # otherwise store a hash covering more bytes than the next poll's
    # comparison_window expects and falsely declare truncation.
    new_head_hash = _hash_bytes(head_bytes[: min(current_size, _HEAD_FINGERPRINT_BYTES)])

    # Only the portion of the file we'd already seen last poll is safe to
    # compare -- see the docstring's "ramp-up" note.
    comparison_window = min(last_known_file_size, _HEAD_FINGERPRINT_BYTES)

    if last_known_head_hash is None or comparison_window == 0:
        # First-ever poll (or the file was empty last time): nothing
        # established yet to compare against, so there's nothing to
        # detect a restart against either.
        truncated = False
    elif current_size < comparison_window:
        # The file no longer even contains the region we last fingerprinted
        # -- can't be a pure-append continuation of it.
        truncated = True
    else:
        truncated = _hash_bytes(head_bytes[:comparison_window]) != last_known_head_hash

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
                # parse_log_line never raises (Task 2's contract) -- a
                # malformed or irrelevant line just comes back as None and
                # is silently skipped, per BACKEND--resilience ("a
                # well-formed JSON line that isn't a trace event is not an
                # error"). What CAN still fail is applying an event whose
                # shape looks right but whose data doesn't hold up (e.g. a
                # "time" field that's a JSON number instead of a string,
                # which raises TypeError out of apply_trace_event's
                # timestamp parsing).
                event = parse_log_line(line)
                if event is None:
                    continue
                try:
                    apply_trace_event(conn, event)
                    applied_count += 1
                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    sqlite3.InterfaceError,
                    sqlite3.ProgrammingError,
                ) as exc:
                    # BACKEND--resilience: "skip the line, log a warning,
                    # keep going" -- one bad line must never crash the
                    # collector loop. InterfaceError/ProgrammingError are
                    # sqlite3.Error subclasses, but a bad parameter binding
                    # (e.g. a list where an int was expected) is a
                    # data-shape failure wearing a sqlite3 costume -- left
                    # uncaught, the same malformed line would fail on every
                    # retry forever, since last_offset would never advance
                    # past it. OperationalError/DatabaseError/IntegrityError
                    # (a locked DB, a real infrastructure fault) are
                    # deliberately left uncaught: those aren't a bad line,
                    # they're a real problem, and should abort the poll
                    # loudly. Either way, aborting loses nothing already
                    # applied earlier in this same poll (apply_trace_event
                    # commits per-event); the collector_state UPDATE below
                    # simply never runs, so the next poll retries cleanly
                    # from this same last_offset -- idempotent, no data
                    # loss, no double-counting.
                    logger.warning(
                        "Skipping malformed trace event in %s "
                        "(event=%r, request_id=%r): %s",
                        log_path,
                        event.get("event"),
                        event.get("request_id"),
                        exc,
                    )
                    continue

    new_offset = start_offset + bytes_consumed

    conn.execute(
        _UPDATE_COLLECTOR_STATE_SQL,
        (new_offset, current_size, new_head_hash, now_utc_iso8601()),
    )
    conn.commit()

    return applied_count
