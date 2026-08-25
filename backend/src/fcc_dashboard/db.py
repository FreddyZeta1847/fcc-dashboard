"""
SQLite schema and connection helper for FCC Dashboard.

Owns the two tables the backend persists to disk, per BACKEND--architecture:

- `requests` — one row per gateway request, keyed by `request_id`. Written by
  the collector (Task 3) as it tails the FCC log, and read by Phase 3's API.
  Cost columns (`actual_cost`/`equivalent_cost`/`savings`) stay NULL in this
  phase — pricing math is wired up later.
- `collector_state` — a single-row table (id is CHECK'd to always be 1) that
  tracks the collector's tail position across restarts: how far into the log
  file it has read (`last_offset`), the file size at that point (used to
  detect truncation/rotation), the file's modification time at that point
  (a secondary truncation signal for the rare case where a rotated file
  happens to land on the exact same size as before -- size alone can't
  tell "nothing changed" apart from "replaced with same-size content"),
  and when it last ran.

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
)
"""

_CREATE_COLLECTOR_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS collector_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_offset INTEGER NOT NULL DEFAULT 0,
    last_known_file_size INTEGER NOT NULL DEFAULT 0,
    last_known_mtime_ns INTEGER NOT NULL DEFAULT 0,
    last_run_at TEXT
)
"""

_ENSURE_COLLECTOR_STATE_ROW = """
INSERT OR IGNORE INTO collector_state
    (id, last_offset, last_known_file_size, last_known_mtime_ns, last_run_at)
VALUES (1, 0, 0, 0, NULL)
"""


def init_db(path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite DB at `path` and ensure its schema.

    Creates the `requests` and `collector_state` tables if they don't already
    exist, and guarantees exactly one `collector_state` row (id=1) is
    present. Safe to call repeatedly against the same file or `:memory:`:
    existing data (including a previously-updated `collector_state` row) is
    never reset or duplicated.

    Returns a connection with `row_factory = sqlite3.Row`, so result rows
    are accessible by column name (`row["provider"]`) as well as by index.
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    conn.execute(_CREATE_REQUESTS_TABLE)
    conn.execute(_CREATE_COLLECTOR_STATE_TABLE)
    conn.execute(_ENSURE_COLLECTOR_STATE_ROW)
    conn.commit()

    return conn
