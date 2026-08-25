"""
SQLite schema and connection helper for FCC Dashboard.

Owns the two tables the backend persists to disk, per BACKEND--architecture:

- `requests` — one row per gateway request, keyed by `request_id`. Written by
  the collector (Task 3) as it tails the FCC log, and read by Phase 3's API.
  Cost columns (`actual_cost`/`equivalent_cost`/`savings`) stay NULL in this
  phase — pricing math is wired up later.
- `collector_state` — a single-row table (id is CHECK'd to always be 1) that
  tracks the collector's tail position across restarts: how far into the log
  file it has read (`last_offset`), the file size at that point
  (`last_known_file_size`), a fingerprint of the file's leading bytes at
  that point (`last_known_head_hash`), and when it last ran. The
  fingerprint is what actually drives truncation/rotation detection --
  see `collector.py`'s `poll_once` docstring for why size alone (whether
  it shrank, stayed the same, or even grew) can't reliably tell a restart
  apart from ordinary appended growth.
- `process_state` — a single-row table (same id=1 singleton pattern as
  `collector_state`) that tracks the FCC server process this backend
  itself launched, if any: `pid` and `started_at` (both NULL when nothing
  is currently tracked). See `process_control.py` for the primitives that
  launch/check/terminate that process. This table is advisory bookkeeping
  only -- per BACKEND--process-control, `/health` (an actual reachability
  probe) is the authoritative signal for whether FCC is really up, since a
  PID can be reused by an unrelated process after a reboot.

`init_db(path)` is the only entry point. It is idempotent: safe to call on
every backend startup, whether `path` is a real file (persistent state) or
`:memory:` (used by every test in this phase). It never errors and never
loses existing data on a repeat call against the same file.
"""

import sqlite3
from pathlib import Path

_CREATE_REQUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY,
    provider TEXT,
    gateway_model TEXT,
    downstream_model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    input_tokens_estimate INTEGER,
    finish_reason TEXT,
    http_status INTEGER,
    exc_type TEXT,
    occurred_at TEXT NOT NULL,
    occurred_at_is_estimated INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL,
    actual_cost REAL,
    equivalent_cost REAL,
    savings REAL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed', 'error'))
)
"""

_CREATE_REQUESTS_OCCURRED_AT_INDEX = """
CREATE INDEX IF NOT EXISTS idx_requests_occurred_at ON requests(occurred_at)
"""

_CREATE_REQUESTS_STATUS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status)
"""

_CREATE_COLLECTOR_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS collector_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_offset INTEGER NOT NULL DEFAULT 0,
    last_known_file_size INTEGER NOT NULL DEFAULT 0,
    last_known_head_hash TEXT,
    last_run_at TEXT
)
"""

_ENSURE_COLLECTOR_STATE_ROW = """
INSERT OR IGNORE INTO collector_state
    (id, last_offset, last_known_file_size, last_known_head_hash, last_run_at)
VALUES (1, 0, 0, NULL, NULL)
"""

_CREATE_PROCESS_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS process_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    pid INTEGER,
    started_at TEXT
)
"""

_ENSURE_PROCESS_STATE_ROW = """
INSERT OR IGNORE INTO process_state (id, pid, started_at)
VALUES (1, NULL, NULL)
"""


def init_db(path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite DB at `path` and ensure its schema.

    Creates the `requests`, `collector_state`, and `process_state` tables if
    they don't already exist, and guarantees exactly one row (id=1) is
    present in each of the two singleton state tables. Safe to call
    repeatedly against the same file or `:memory:`: existing data (including
    a previously-updated `collector_state` or `process_state` row) is never
    reset or duplicated.

    Returns a connection with `row_factory = sqlite3.Row`, so result rows
    are accessible by column name (`row["provider"]`) as well as by index.

    The connection is configured for Phase 3's multi-threaded access
    (Starlette's threadpool for sync endpoints, plus the collector's
    background polling potentially sharing this connection):
    `check_same_thread=False` lifts sqlite3's default single-thread
    ownership restriction, `timeout=30.0` makes a caller that hits a locked
    database wait and retry rather than fail immediately, WAL (write-ahead
    logging) mode lets readers and a writer proceed concurrently instead of
    blocking each other, and `busy_timeout` is WAL's own analogous wait
    setting enforced inside SQLite itself. WAL is skipped for `:memory:`
    databases (the pragma doesn't apply there, and an in-memory database
    can't usefully be shared across threads/processes anyway) but the
    other pragmas are still harmless to set.
    """
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    conn.execute(_CREATE_REQUESTS_TABLE)
    conn.execute(_CREATE_COLLECTOR_STATE_TABLE)
    conn.execute(_ENSURE_COLLECTOR_STATE_ROW)
    conn.execute(_CREATE_PROCESS_STATE_TABLE)
    conn.execute(_ENSURE_PROCESS_STATE_ROW)
    conn.execute(_CREATE_REQUESTS_OCCURRED_AT_INDEX)
    conn.execute(_CREATE_REQUESTS_STATUS_INDEX)
    conn.commit()

    return conn
