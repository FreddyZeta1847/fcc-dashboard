"""Tests for GET /requests."""

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


def _insert_request(conn, request_id, provider, status, occurred_at):
    conn.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (request_id, provider, occurred_at, occurred_at, status),
    )


def _insert_priceable_request(
    conn, request_id, provider, downstream_model, gateway_model,
    input_tokens, output_tokens, occurred_at,
):
    conn.execute(
        "INSERT INTO requests (request_id, provider, downstream_model, gateway_model, "
        "input_tokens, output_tokens, occurred_at, ingested_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed')",
        (request_id, provider, downstream_model, gateway_model, input_tokens, output_tokens, occurred_at, occurred_at),
    )


@pytest.fixture
def client_and_db(tmp_path):
    test_db = init_db(":memory:")
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps(SAMPLE_PRICING), encoding="utf-8")
    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_pricing_config_path] = lambda: pricing_path
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


def test_requests_fills_in_savings_live_for_a_priced_row(client_and_db):
    client, db = client_and_db
    _insert_priceable_request(
        db, "req_1", "NIM", "deepseek-ai/deepseek-v4-flash-0731", "claude-opus-5",
        1_000_000, 1_000_000, "2026-08-24T10:00:00.000Z",
    )
    db.commit()

    response = client.get("/requests")

    row = response.json()["results"][0]
    assert row["actual_cost"] == 0.0
    assert row["equivalent_cost"] == 30.0
    assert row["savings"] == 30.0


def test_requests_leaves_savings_null_for_an_unconfigured_pair(client_and_db):
    client, db = client_and_db
    _insert_priceable_request(
        db, "req_1", "some_unpriced_provider", "some-model", "claude-opus-5",
        1_000, 1_000, "2026-08-24T10:00:00.000Z",
    )
    db.commit()

    response = client.get("/requests")

    row = response.json()["results"][0]
    assert row["actual_cost"] is None
    assert row["equivalent_cost"] is None
    assert row["savings"] is None


def test_requests_leaves_savings_null_for_a_pending_row(client_and_db):
    client, db = client_and_db
    _insert_request(db, "req_1", "NIM", "pending", "2026-08-24T10:00:00.000Z")
    db.commit()

    response = client.get("/requests")

    row = response.json()["results"][0]
    assert row["savings"] is None


def test_requests_treats_missing_pricing_file_as_all_unpriced(client_and_db, tmp_path):
    client, db = client_and_db
    app.dependency_overrides[get_pricing_config_path] = lambda: tmp_path / "does-not-exist.json"
    _insert_priceable_request(
        db, "req_1", "NIM", "deepseek-ai/deepseek-v4-flash-0731", "claude-opus-5",
        1_000_000, 1_000_000, "2026-08-24T10:00:00.000Z",
    )
    db.commit()

    response = client.get("/requests")

    assert response.status_code == 200
    assert response.json()["results"][0]["savings"] is None
