"""Tests for GET /db/tables and GET /db/tables/{name}."""

import pytest
from fastapi.testclient import TestClient

from fcc_dashboard.api import app, get_db
from fcc_dashboard.db import init_db


@pytest.fixture
def client_and_db():
    test_db = init_db(":memory:")
    app.dependency_overrides[get_db] = lambda: test_db
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
