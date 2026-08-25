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


def test_init_db_creates_process_state_table_with_one_default_row():
    conn = init_db(":memory:")
    rows = conn.execute("SELECT * FROM process_state").fetchall()
    assert len(rows) == 1
    assert rows[0]["pid"] is None
    assert rows[0]["started_at"] is None
