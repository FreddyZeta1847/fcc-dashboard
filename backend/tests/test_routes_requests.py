"""Tests for GET /requests."""

import pytest
from fastapi.testclient import TestClient

from fcc_dashboard.api import app, get_db
from fcc_dashboard.db import init_db


def _insert_request(conn, request_id, provider, status, occurred_at):
    conn.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (request_id, provider, occurred_at, occurred_at, status),
    )


@pytest.fixture
def client_and_db():
    test_db = init_db(":memory:")
    app.dependency_overrides[get_db] = lambda: test_db
    yield TestClient(app), test_db
    app.dependency_overrides.clear()


def test_requests_returns_all_rows_ordered_by_occurred_at_desc(client_and_db):
    client, db = client_and_db
    _insert_request(db, "req_1", "nvidia_nim", "completed", "2026-08-24T10:00:00.000Z")
    _insert_request(db, "req_2", "openrouter", "completed", "2026-08-24T12:00:00.000Z")
    db.commit()

    response = client.get("/requests")

    body = response.json()
    assert body["total"] == 2
    assert [r["request_id"] for r in body["results"]] == ["req_2", "req_1"]


def test_requests_pagination(client_and_db):
    client, db = client_and_db
    for i in range(5):
        _insert_request(db, f"req_{i}", "nvidia_nim", "completed", f"2026-08-24T10:0{i}:00.000Z")
    db.commit()

    response = client.get("/requests?limit=2&offset=1")

    body = response.json()
    assert body["total"] == 5
    assert len(body["results"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 1


def test_requests_filter_by_status(client_and_db):
    client, db = client_and_db
    _insert_request(db, "req_1", "nvidia_nim", "completed", "2026-08-24T10:00:00.000Z")
    _insert_request(db, "req_2", "nvidia_nim", "error", "2026-08-24T11:00:00.000Z")
    db.commit()

    response = client.get("/requests?status=error")

    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["request_id"] == "req_2"


def test_requests_filter_by_provider(client_and_db):
    client, db = client_and_db
    _insert_request(db, "req_1", "nvidia_nim", "completed", "2026-08-24T10:00:00.000Z")
    _insert_request(db, "req_2", "openrouter", "completed", "2026-08-24T11:00:00.000Z")
    db.commit()

    response = client.get("/requests?provider=openrouter")

    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["provider"] == "openrouter"


def test_requests_invalid_status_returns_422(client_and_db):
    client, _db = client_and_db
    response = client.get("/requests?status=not_a_real_status")
    assert response.status_code == 422


def test_requests_empty_table_returns_empty_results(client_and_db):
    client, _db = client_and_db
    response = client.get("/requests")
    body = response.json()
    assert body["total"] == 0
    assert body["results"] == []
