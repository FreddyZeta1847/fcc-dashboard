# Phase 2 — Persistence & Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SQLite schema and the log-tailing collector that turns FCC's log lines into durable rows, decoupled from FCC's own non-durable log.

**Architecture:** Four layers in the `fcc_dashboard` package: `db.py` (schema + connection), `log_parser.py` (raw log line -> structured trace event, or None), `collector.py` (trace event -> row upsert, plus the poll-once/catch-up loop). Each layer is independently testable — `log_parser` never touches a DB, `db` never touches FCC's log format, `collector` composes both.

**Tech Stack:** stdlib `sqlite3` (no ORM, per BACKEND--technologies), stdlib `json`, `pathlib`, `time`. Reuses Phase 1's `fcc_dashboard.datetime_utils` (`parse_fcc_timestamp`, `to_utc_iso8601`, `now_utc_iso8601`).

**Spec:** `vault-fcc-dashboard/plans/PHASE-2-PERSISTENCE-COLLECTOR.md`, `vault-fcc-dashboard/features/BACKEND/BACKEND--architecture.md` (schema), `BACKEND--collector.md` (loop steps), `BACKEND--resilience.md` (failure modes) — all locked decisions this plan implements.

## Global Constraints

- One row per request, keyed by `request_id` (unique/primary key). Upsert-safe: re-applying the same log bytes twice must never create a duplicate row or corrupt existing data.
- `occurred_at` is set ONLY when a row is first created (on whichever event — `provider.request.sent`, or a `provider.response.completed`/`transport_error` arriving without a prior `request.sent` row, e.g. a read window that missed it) — never overwritten by a later event for the same `request_id`.
- Timestamp fallback rule (per DATE-TIME--resilience, already implemented in Phase 1's `datetime_utils`): if the log line's own `time` field is missing or fails `parse_fcc_timestamp`, use `now_utc_iso8601()` as `occurred_at` and set `occurred_at_is_estimated = 1` (true). Otherwise use the real parsed-and-normalized time and `occurred_at_is_estimated = 0`.
- A malformed JSON line must never raise out of the parser or crash the collector loop — it's skipped.
- A well-formed JSON line that isn't one of the three trace events this collector cares about (`provider.request.sent`, `provider.response.completed`, `provider.response.transport_error`) is not an error — it's just irrelevant and skipped silently (FCC's log has many other line types: startup messages, debug traces, etc.).
- **Ruling (ledgered, not in the vault):** cost fields (`actual_cost`, `equivalent_cost`, `savings`) are NOT computed by the collector in this phase — they stay `NULL` on every row this phase writes. Wiring PRICING-ENGINE in belongs to Phase 3, which is also where the pricing config file itself gets created/seeded (via the `/pricing` endpoints) — Phase 2 has no pricing config file to read yet, and inventing one here would blur the phase boundary. This is consistent with the schema's own nullable semantics for those columns.
- SQLite upserts use `INSERT ... ON CONFLICT(request_id) DO UPDATE SET ...` (native SQLite upsert syntax, supported by Python's bundled `sqlite3` on all supported Python versions).

---

### Task 1: SQLite schema and connection helper

**Files:**
- Create: `backend/src/fcc_dashboard/db.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Consumes: nothing (stdlib `sqlite3` only).
- Produces: `init_db(path: str | Path) -> sqlite3.Connection` — creates the `requests` and `collector_state` tables if they don't exist (idempotent — safe to call on every backend startup), returns a connection with `row_factory = sqlite3.Row` (so rows are accessible by column name, needed by later tasks/phases). Consumed by Task 3 (collector upsert logic) and Phase 3's API.

**Contract for `init_db`:**
- Must be idempotent: calling it twice on the same file must not error or lose existing data (use `CREATE TABLE IF NOT EXISTS`).
- Must also work with SQLite's special `:memory:` path (used by every test in this phase — an in-memory DB, no file I/O, torn down automatically per test).
- The `requests` table columns, exactly matching BACKEND--architecture.md's schema:
  - `request_id TEXT PRIMARY KEY`
  - `provider TEXT`, `gateway_model TEXT`, `downstream_model TEXT`
  - `input_tokens INTEGER`, `output_tokens INTEGER`, `input_tokens_estimate INTEGER`
  - `finish_reason TEXT`, `http_status INTEGER`, `exc_type TEXT`
  - `occurred_at TEXT NOT NULL` (ISO-8601 UTC text, per DATE-TIME's convention)
  - `occurred_at_is_estimated INTEGER NOT NULL DEFAULT 0` (SQLite has no native boolean; 0/1)
  - `ingested_at TEXT NOT NULL`
  - `actual_cost REAL`, `equivalent_cost REAL`, `savings REAL` (all nullable — stay NULL in this phase, per the Global Constraints ruling above)
  - `status TEXT NOT NULL DEFAULT 'pending'` (`'pending'` | `'completed'` | `'error'`)
- The `collector_state` table: a single-row table (enforce with `id INTEGER PRIMARY KEY CHECK (id = 1)`) with columns `id`, `last_offset INTEGER NOT NULL DEFAULT 0`, `last_known_file_size INTEGER NOT NULL DEFAULT 0`, `last_run_at TEXT`. `init_db` must ensure exactly one row exists (id=1) after it runs — insert the default row (`last_offset=0, last_known_file_size=0, last_run_at=NULL`) if the table was just created, using `INSERT OR IGNORE INTO collector_state (id) VALUES (1)` or equivalent, so calling `init_db` again never duplicates or resets it.

  **Post-Task-4 amendment (kept for history, not re-executed):** Task 4's review found the size-only truncation check above misses same-size and larger-content restarts. The schema gained a `last_known_head_hash TEXT` column (a hash of the file's leading bytes, replacing the size comparison as the actual truncation signal) instead — see `BACKEND--architecture.md`/`BACKEND--resilience.md` (updated) and the Phase 2 SDD ledger for the full reasoning. Task 1 as originally written above did not include this column; it was added by Task 4's fix round, touching `db.py` out of its own stated file list, with the deviation reviewed and confirmed sound.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_db.py`:
```python
"""Unit tests for backend.fcc_dashboard.db."""

import sqlite3

from fcc_dashboard.db import init_db


def test_init_db_creates_requests_table():
    conn = init_db(":memory:")
    cursor = conn.execute("PRAGMA table_info(requests)")
    columns = {row[1] for row in cursor.fetchall()}
    expected = {
        "request_id", "provider", "gateway_model", "downstream_model",
        "input_tokens", "output_tokens", "input_tokens_estimate",
        "finish_reason", "http_status", "exc_type",
        "occurred_at", "occurred_at_is_estimated", "ingested_at",
        "actual_cost", "equivalent_cost", "savings", "status",
    }
    assert expected.issubset(columns)


def test_init_db_creates_collector_state_table_with_one_default_row():
    conn = init_db(":memory:")
    rows = conn.execute("SELECT * FROM collector_state").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["last_offset"] == 0
    assert row["last_known_file_size"] == 0
    assert row["last_run_at"] is None


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    conn1 = init_db(db_path)
    conn1.execute(
        "UPDATE collector_state SET last_offset = 42 WHERE id = 1"
    )
    conn1.commit()
    conn1.close()

    # Re-running init_db against the same file must not reset collector_state
    conn2 = init_db(db_path)
    row = conn2.execute("SELECT last_offset FROM collector_state").fetchone()
    assert row["last_offset"] == 42


def test_requests_table_enforces_unique_request_id():
    conn = init_db(":memory:")
    conn.execute(
        "INSERT INTO requests (request_id, occurred_at, ingested_at) "
        "VALUES ('req_1', '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z')"
    )
    conn.commit()
    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO requests (request_id, occurred_at, ingested_at) "
            "VALUES ('req_1', '2026-01-01T00:00:01.000Z', '2026-01-01T00:00:01.000Z')"
        )


def test_row_factory_allows_column_name_access():
    conn = init_db(":memory:")
    conn.execute(
        "INSERT INTO requests (request_id, occurred_at, ingested_at, provider) "
        "VALUES ('req_1', '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z', 'nvidia_nim')"
    )
    conn.commit()
    row = conn.execute("SELECT * FROM requests WHERE request_id = 'req_1'").fetchone()
    assert row["provider"] == "nvidia_nim"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fcc_dashboard.db'`

- [ ] **Step 3: Write the implementation**

Write `backend/src/fcc_dashboard/db.py` to satisfy the contract above and make every test in Step 1 pass. Start the file with a module docstring explaining its role (schema + connection helper for the `requests`/`collector_state` tables, per BACKEND--architecture). Use `CREATE TABLE IF NOT EXISTS` for both tables and an idempotent way to guarantee exactly one `collector_state` row exists. Set `conn.row_factory = sqlite3.Row` before returning.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_db.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/db.py backend/tests/test_db.py
git commit -m "feat(backend): add SQLite schema and connection helper"
```

---

### Task 2: Log line parser

**Files:**
- Create: `backend/src/fcc_dashboard/log_parser.py`
- Test: `backend/tests/test_log_parser.py`

**Interfaces:**
- Consumes: nothing (stdlib `json` only).
- Produces: `parse_log_line(raw_line: str) -> dict | None`. Consumed by Task 4 (collector loop).

**Contract:**
- Input is one raw line from FCC's `server.log` (a JSON object per line, or blank/whitespace-only lines between them, or non-JSON garbage in a pathological case).
- Returns the parsed JSON object (a `dict`) if and only if: the line parses as valid JSON, the result is a JSON object (not a list/string/number), AND its `"event"` field is one of exactly these three strings: `"provider.request.sent"`, `"provider.response.completed"`, `"provider.response.transport_error"`.
- Returns `None` for: blank/whitespace-only lines, invalid JSON, valid JSON that isn't an object, valid JSON objects with no `"event"` key or an `"event"` value outside the three above (e.g. `"api.route.resolved"`, or a line with no `"event"` key at all like a plain startup log message).
- Must never raise an exception for any string input — always either returns the dict or `None`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_log_parser.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_log_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fcc_dashboard.log_parser'`

- [ ] **Step 3: Write the implementation**

Write `backend/src/fcc_dashboard/log_parser.py` to satisfy the contract and pass every test above. Module docstring should explain this parses FCC's per-line JSON log format and filters to only the three trace events the collector cares about, per BACKEND--collector.md, never raising on bad input.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_log_parser.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/log_parser.py backend/tests/test_log_parser.py
git commit -m "feat(backend): add FCC log line parser"
```

---

### Task 3: Trace event upsert into `requests`

**Files:**
- Create: `backend/src/fcc_dashboard/collector.py`
- Test: `backend/tests/test_collector.py`

**Interfaces:**
- Consumes: `init_db` (Task 1, via test fixtures), `parse_fcc_timestamp`/`to_utc_iso8601`/`now_utc_iso8601` (Phase 1's `datetime_utils`).
- Produces: `apply_trace_event(conn: sqlite3.Connection, event: dict) -> None`. Consumed by Task 4 (the poll loop) and any future backfill/replay tooling.

**Contract:**
- `event` is a dict as returned by `parse_log_line` (Task 2) — always has an `"event"` key with one of the three known values, and always has `"request_id"` in practice (if it's ever missing, skip the event defensively — do not raise, do not insert a row with a NULL primary key).
- **occurred_at resolution** (implements DATE-TIME--resilience's fallback rule): read the event's `"time"` field. If present, try `parse_fcc_timestamp` on it; on success, `occurred_at = to_utc_iso8601(parsed)`, `occurred_at_is_estimated = 0`. If `"time"` is missing OR `parse_fcc_timestamp` raises `ValueError`, `occurred_at = now_utc_iso8601()`, `occurred_at_is_estimated = 1`.
- **`ingested_at`** is set to `now_utc_iso8601()` on every call (it tracks "last time the collector touched this row", including on updates — it is audit-only, never used for calculations, so this is safe).
- **On `"provider.request.sent"`:** insert a new row (status `'pending'`) with `request_id`, `provider`, `gateway_model`, `downstream_model`, `occurred_at`, `occurred_at_is_estimated`, `ingested_at`. If a row with this `request_id` already exists (e.g. a re-read of the same bytes, or the completed event somehow arrived first and this is a late/duplicate request.sent), update `provider`/`gateway_model`/`downstream_model`/`ingested_at` in place but **do not** touch `occurred_at`, `occurred_at_is_estimated`, or `status` on conflict — the row's original `occurred_at` and whatever status it has already reached must survive a duplicate/out-of-order `request.sent`.
- **On `"provider.response.completed"`:** upsert the row (status `'completed'`) with `output_tokens` (from event's `"output_tokens"`), `input_tokens` (from event's `"prompt_tokens"` — note the field name difference between FCC's log and our column name), `input_tokens_estimate` (from event's `"prompt_tokens_estimate"`), `finish_reason`, `ingested_at`, `status`. If no row exists yet for this `request_id` (the collector's read window missed the `request.sent` line), INSERT a new row using this event's own `occurred_at`/`occurred_at_is_estimated` as a reasonable fallback for when the row was first seen. If a row already exists, do NOT touch its existing `occurred_at`/`occurred_at_is_estimated` (keep the original, from whenever the row was first created).
- **On `"provider.response.transport_error"`:** same upsert pattern as `completed`, but status `'error'`, columns `http_status`, `exc_type` instead of the completion fields.
- Every write commits (`conn.commit()`) before returning, so tests can query the same connection immediately after calling `apply_trace_event`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_collector.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fcc_dashboard.collector'`

- [ ] **Step 3: Write the implementation**

Write `backend/src/fcc_dashboard/collector.py` (just `apply_trace_event` for this task — the poll loop is Task 4, same file) to satisfy the contract above and pass every test. Import `parse_fcc_timestamp`, `to_utc_iso8601`, `now_utc_iso8601` from `fcc_dashboard.datetime_utils`. Use SQLite's `INSERT ... ON CONFLICT(request_id) DO UPDATE SET ...` syntax for the upserts, being careful that the `DO UPDATE SET` clause for each event type only touches the columns that event type should ever update (per the contract's rules about `occurred_at`/`occurred_at_is_estimated`/`provider`/`gateway_model`/`downstream_model` needing to survive certain updates unchanged). Module docstring should explain the upsert-by-request_id model and link the rationale to BACKEND--architecture.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_collector.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/collector.py backend/tests/test_collector.py
git commit -m "feat(backend): add trace event upsert logic"
```

---

### Task 4: Poll loop, truncation detection, and catch-up read

**Files:**
- Modify: `backend/src/fcc_dashboard/collector.py` (add `poll_once`)
- Modify: `backend/tests/test_collector.py` (add tests)

**Interfaces:**
- Consumes: `apply_trace_event` (Task 3, same file), `parse_log_line` (Task 2), `now_utc_iso8601` (Phase 1).
- Produces: `poll_once(conn: sqlite3.Connection, log_path: str | Path) -> int` — reads whatever new bytes exist since `collector_state.last_offset`, applies every trace event found, updates `collector_state`, and returns the number of trace events applied (useful for logging/testing). This single function IS both the "one-shot catch-up on startup" and each tick of the continuous poll loop — callers (a future `main.py`/FastAPI startup hook in a later phase) just call it once at startup and then again on a timer; this task does not need to build the timer/scheduling wrapper itself, only the idempotent single-poll unit.

**Contract:**
- Reads `collector_state.last_offset` and `collector_state.last_known_file_size` from the DB.
- If `log_path` doesn't exist (FCC never started, or was never run on this machine yet), treat it as "nothing to read" — return 0, do not raise, do not update `collector_state` in a way that would misrepresent a real file's state.
- Determine the current file size. **Truncation/rotation detection**: if current file size < `last_known_file_size`, FCC restarted and the log was truncated — reset the read position to the start of the file (byte 0) instead of the stale `last_offset`, per BACKEND--resilience.
- Read bytes from the effective start position (either `last_offset`, or 0 if truncation was detected) to the end of the file. Decode as UTF-8, split into lines.
- For each line: pass it to `parse_log_line`; if it returns a dict, pass that to `apply_trace_event`. A line that fails to decode as UTF-8 partway through (e.g. the file was read mid-write, cutting a multi-byte character) should not crash the whole poll — skip that malformed trailing fragment gracefully (reading in a way that only processes complete lines, e.g. splitting on `"\n"` and ignoring a final incomplete fragment without a trailing newline, is an acceptable and expected way to satisfy this — a partial line gets picked up whole on the next poll once the writer finishes it).
- After processing, update `collector_state`: `last_offset` = the byte position actually consumed (only up through the last complete line processed, so a trailing incomplete line is re-read next time, not skipped), `last_known_file_size` = the file's size as observed this call, `last_run_at` = `now_utc_iso8601()`. Commit this update.
- Returns the count of trace events successfully applied (i.e. how many lines `parse_log_line` did NOT return `None` for and were passed to `apply_trace_event`) — 0 if the file didn't exist, was empty, or had no new bytes.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_collector.py`:
```python
from fcc_dashboard.collector import poll_once


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_collector.py -v -k poll_once`
Expected: FAIL with `ImportError: cannot import name 'poll_once'`

- [ ] **Step 3: Write the implementation**

Add `poll_once` to `backend/src/fcc_dashboard/collector.py`, satisfying the contract above and passing every test. Read `collector_state` via the existing connection (`SELECT * FROM collector_state WHERE id = 1`), open the log file in binary mode and seek to the effective start offset, read to EOF, decode as UTF-8 (handle a trailing incomplete line per the contract — track how many bytes were actually consumed by whole lines, not the full read length), split on `"\n"`, feed each non-empty line through `parse_log_line` then `apply_trace_event` when it returns non-None, then update `collector_state` in one `UPDATE` statement and commit.

- [ ] **Step 4: Run tests to verify they pass, then run the full suite**

Run: `cd backend && uv run pytest tests/test_collector.py -v`
Expected: 13 passed (8 from Task 3 + 5 new). *(Historical note: the fix
rounds during Task 4's review added a larger-content truncation test and a
DB-error-propagation test, so the file shipped with 15, not 13 — see the
Phase 2 SDD ledger.)*

Run: `cd backend && uv run pytest -v`
Expected: all tests across the whole backend pass (Phase 1's 32 + this phase's db/log_parser/collector tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/collector.py backend/tests/test_collector.py
git commit -m "feat(backend): add poll-once loop with truncation detection and catch-up read"
```

## Self-Review Notes

- Spec coverage: PHASE-2-PERSISTENCE-COLLECTOR.md's three bullets (schema, collector loop, resilience handling) are each covered — schema in Task 1, loop mechanics in Tasks 3-4, every named resilience case (truncation, malformed JSON, unparseable timestamp) has a dedicated test in Task 3 or Task 4. "Verifiable" (feeding a sample log file produces correct rows including edge cases) is exercised directly by Task 4's tests, which write real fixture log files to a temp directory and poll against them.
- No placeholders: every task has real, complete test code. Implementations are specified by contract + tests (deliberately NOT hand-written by the plan's author this time, per the lesson from Phase 1's two self-introduced bugs) rather than prescribed code — the implementer writes the body, the tests are the source of truth for correctness.
- Type consistency: `apply_trace_event`'s signature (`conn: sqlite3.Connection, event: dict`) and `poll_once`'s signature (`conn: sqlite3.Connection, log_path: str | Path`) are used identically across Tasks 3-4's tests and each other's dependency.
- Deferred, ruled explicitly in Global Constraints: cost-field computation (Phase 3), not a gap in this plan.
