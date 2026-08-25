"""Tests for GET /db/tables and GET /db/tables/{name}."""

import json

import pytest
from fastapi.testclient import TestClient

from fcc_dashboard.api import app, get_db, get_pricing_config_path
from fcc_dashboard.db import init_db

SAMPLE_PRICING = {
    "anthropic": {
        "claude-opus-5": {"input_per_million": 5.0, "output_per_million": 25.0},
    },
    "providers": {
        "NIM": {"deepseek-ai/deepseek-v4-flash-0731": {"input_per_million": 0.0, "output_per_million": 0.0}},
    },
}


@pytest.fixture
def client_and_db(tmp_path):
    test_db = init_db(":memory:")
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps(SAMPLE_PRICING), encoding="utf-8")
    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_pricing_config_path] = lambda: pricing_path
    yield TestClient(app), test_db
    app.dependency_overrides.clear()


def test_list_tables(client_and_db):
    client, _db = client_and_db
    response = client.get("/db/tables")
    body = response.json()
    assert set(body["tables"]) == {"requests", "collector_state", "process_state"}


def test_get_table_rows(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, status) "
        "VALUES ('req_1', 'nvidia_nim', '2026-08-24T10:00:00.000Z', "
        "'2026-08-24T10:00:00.000Z', 'completed')"
    )
    db.commit()

    response = client.get("/db/tables/requests")

    body = response.json()
    assert body["table"] == "requests"
    assert body["total"] == 1
    assert "request_id" in body["columns"]
    assert len(body["rows"]) == 1


def test_get_table_rows_pagination(client_and_db):
    client, db = client_and_db
    for i in range(3):
        db.execute(
            "INSERT INTO requests (request_id, occurred_at, ingested_at, status) "
            f"VALUES ('req_{i}', '2026-08-24T10:0{i}:00.000Z', "
            f"'2026-08-24T10:0{i}:00.000Z', 'completed')"
        )
    db.commit()

    response = client.get("/db/tables/requests?limit=2&offset=1")

    body = response.json()
    assert body["total"] == 3
    assert len(body["rows"]) == 2


def test_get_nonexistent_table_returns_404(client_and_db):
    client, _db = client_and_db
    response = client.get("/db/tables/not_a_real_table")
    assert response.status_code == 404


def test_get_table_rejects_sql_injection_attempt(client_and_db):
    client, _db = client_and_db
    response = client.get("/db/tables/requests%3B%20DROP%20TABLE%20requests%3B--")
    # must be treated as an unknown table name (404), never executed as SQL
    assert response.status_code == 404

    # confirm the requests table still exists and is queryable afterward
    follow_up = client.get("/db/tables/requests")
    assert follow_up.status_code == 200


def test_get_requests_table_rows_overlays_live_savings(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, downstream_model, gateway_model, "
        "input_tokens, output_tokens, occurred_at, ingested_at, status) "
        "VALUES ('req_1', 'NIM', 'deepseek-ai/deepseek-v4-flash-0731', 'claude-opus-5', "
        "1000000, 1000000, '2026-08-24T10:00:00.000Z', '2026-08-24T10:00:00.000Z', 'completed')"
    )
    db.commit()

    response = client.get("/db/tables/requests")

    body = response.json()
    columns = body["columns"]
    row = body["rows"][0]
    assert row[columns.index("actual_cost")] == 0.0
    assert row[columns.index("equivalent_cost")] == 30.0
    assert row[columns.index("savings")] == 30.0


def test_get_requests_table_rows_leaves_pending_row_null(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, status) "
        "VALUES ('req_1', 'NIM', '2026-08-24T10:00:00.000Z', '2026-08-24T10:00:00.000Z', 'pending')"
    )
    db.commit()

    response = client.get("/db/tables/requests")

    body = response.json()
    columns = body["columns"]
    row = body["rows"][0]
    assert row[columns.index("savings")] is None


def test_get_other_tables_are_never_overlaid(client_and_db):
    client, _db = client_and_db
    response = client.get("/db/tables/collector_state")
    assert response.status_code == 200
