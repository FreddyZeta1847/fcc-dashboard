"""Tests for GET /stats."""

import json

import pytest
from fastapi.testclient import TestClient

from fcc_dashboard.api import app, get_db, get_pricing_config_path
from fcc_dashboard.db import init_db

SAMPLE_PRICING = {
    "anthropic": {
        "opus": {"input_per_million": 15.0, "output_per_million": 75.0},
        "sonnet": {"input_per_million": 3.0, "output_per_million": 15.0},
        "haiku": {"input_per_million": 0.25, "output_per_million": 1.25},
    },
    "providers": {
        "nvidia_nim": {
            "glm-4": {"input_per_million": 0.0, "output_per_million": 0.0,
                      "currency": "USD", "last_updated": "2026-08-01T00:00:00.000Z",
                      "source": "manual"}
        }
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


def _insert_completed(conn, request_id, provider, gateway_model, downstream_model,
                       input_tokens, output_tokens, occurred_at):
    conn.execute(
        "INSERT INTO requests (request_id, provider, gateway_model, downstream_model, "
        "input_tokens, output_tokens, occurred_at, ingested_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed')",
        (request_id, provider, gateway_model, downstream_model,
         input_tokens, output_tokens, occurred_at, occurred_at),
    )


def test_stats_computes_savings_for_priced_rows(client_and_db):
    client, db = client_and_db
    _insert_completed(db, "req_1", "nvidia_nim", "sonnet", "glm-4",
                       1_000_000, 1_000_000, "2026-08-24T10:00:00.000Z")
    db.commit()

    response = client.get("/stats?range=last_7_days")

    body = response.json()
    assert body["completed_requests"] == 1
    assert body["total_savings"] == 18.0  # sonnet price minus $0 nvidia_nim price
    assert body["unpriced_request_count"] == 0


def test_stats_unpriced_pair_never_counted_as_free(client_and_db):
    client, db = client_and_db
    _insert_completed(db, "req_1", "some_unpriced_provider", "sonnet", "some-model",
                       1_000_000, 1_000_000, "2026-08-24T10:00:00.000Z")
    db.commit()

    response = client.get("/stats?range=last_7_days")

    body = response.json()
    assert body["unpriced_request_count"] == 1
    # total_savings should not silently include a $0 contribution from this row
    assert body["total_savings"] == 0.0  # no OTHER priced rows exist, so sum is legitimately 0


def test_stats_orphan_row_with_null_gateway_model_is_unpriced_not_a_500(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, gateway_model, downstream_model, "
        "input_tokens, output_tokens, occurred_at, ingested_at, status) "
        "VALUES (?, NULL, NULL, NULL, ?, ?, ?, ?, 'completed')",
        ("req_orphan", 100, 50, "2026-08-24T10:00:00.000Z", "2026-08-24T10:00:00.000Z"),
    )
    db.commit()

    response = client.get("/stats?range=last_7_days")

    assert response.status_code == 200
    assert response.json()["unpriced_request_count"] == 1


def test_stats_pending_and_error_rows_excluded_from_cost_but_counted(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, status) "
        "VALUES ('req_pending', 'nvidia_nim', '2026-08-24T10:00:00.000Z', "
        "'2026-08-24T10:00:00.000Z', 'pending')"
    )
    db.commit()

    response = client.get("/stats?range=last_7_days")

    body = response.json()
    assert body["pending_requests"] == 1
    assert body["completed_requests"] == 0
    assert body["total_savings"] == 0.0


def test_stats_invalid_range_returns_422(client_and_db):
    client, _db = client_and_db
    response = client.get("/stats?range=not_a_real_range")
    assert response.status_code == 422


def test_stats_no_pricing_file_returns_null_total_savings(tmp_path):
    test_db = init_db(":memory:")
    missing_path = tmp_path / "does_not_exist.json"
    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_pricing_config_path] = lambda: missing_path
    client = TestClient(app)

    _insert_completed(test_db, "req_1", "nvidia_nim", "sonnet", "glm-4",
                       100, 50, "2026-08-24T10:00:00.000Z")
    test_db.commit()

    response = client.get("/stats?range=last_7_days")

    assert response.status_code == 200
    assert response.json()["total_savings"] is None


def test_stats_corrupt_pricing_file_returns_null_total_savings(tmp_path):
    test_db = init_db(":memory:")
    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("{not valid json", encoding="utf-8")
    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_pricing_config_path] = lambda: corrupt_path
    client = TestClient(app)

    _insert_completed(test_db, "req_1", "nvidia_nim", "sonnet", "glm-4",
                       100, 50, "2026-08-24T10:00:00.000Z")
    test_db.commit()

    response = client.get("/stats?range=last_7_days")

    assert response.status_code == 200
    body = response.json()
    assert body["total_savings"] is None
    assert body["unpriced_request_count"] == 1


def test_volume_by_provider_counts_all_rows_regardless_of_pricing_or_status(client_and_db):
    client, db = client_and_db
    # Priced, completed.
    _insert_completed(db, "req_1", "nvidia_nim", "sonnet", "glm-4",
                       1_000_000, 1_000_000, "2026-08-24T10:00:00.000Z")
    # Same provider, UNPRICED downstream model -- by_provider would skip
    # this row entirely; volume_by_provider must still count it.
    _insert_completed(db, "req_2", "nvidia_nim", "sonnet", "some-unpriced-model",
                       500_000, 500_000, "2026-08-24T11:00:00.000Z")
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    volume = {row["provider"]: row for row in body["volume_by_provider"]}
    assert volume["nvidia_nim"]["request_count"] == 2
    assert volume["nvidia_nim"]["input_tokens"] == 1_500_000
    assert volume["nvidia_nim"]["output_tokens"] == 1_500_000
    # by_provider (the savings-only breakdown) should still only see the
    # one priced row -- confirms the two aggregates are genuinely
    # independent, not accidentally sharing a filter.
    by_provider_savings = {row["provider"]: row for row in body["by_provider"]}
    assert by_provider_savings["nvidia_nim"]["request_count"] == 1


def test_volume_by_provider_excludes_null_provider_rows(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, status) "
        "VALUES ('req_orphan', NULL, '2026-08-24T10:00:00.000Z', "
        "'2026-08-24T10:00:00.000Z', 'pending')"
    )
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    assert body["volume_by_provider"] == []


def test_volume_by_model_groups_by_provider_and_downstream_model(client_and_db):
    client, db = client_and_db
    _insert_completed(db, "req_1", "nvidia_nim", "sonnet", "glm-4",
                       1_000_000, 1_000_000, "2026-08-24T10:00:00.000Z")
    _insert_completed(db, "req_2", "openrouter", "sonnet", "glm-4",
                       200_000, 200_000, "2026-08-24T11:00:00.000Z")
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    assert len(body["volume_by_model"]) == 2
    keyed = {(row["provider"], row["model"]): row for row in body["volume_by_model"]}
    assert keyed[("nvidia_nim", "glm-4")]["request_count"] == 1
    assert keyed[("openrouter", "glm-4")]["request_count"] == 1


def test_volume_by_model_excludes_rows_with_null_downstream_model(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, downstream_model, occurred_at, "
        "ingested_at, status) VALUES "
        "('req_orphan', 'nvidia_nim', NULL, '2026-08-24T10:00:00.000Z', "
        "'2026-08-24T10:00:00.000Z', 'pending')"
    )
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    assert body["volume_by_model"] == []


def test_volume_estimated_count_reflects_estimated_timestamp_rows(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, downstream_model, occurred_at, "
        "occurred_at_is_estimated, ingested_at, status) VALUES "
        "('req_est', 'nvidia_nim', 'glm-4', '2026-08-24T10:00:00.000Z', 1, "
        "'2026-08-24T10:00:00.000Z', 'pending')"
    )
    _insert_completed(db, "req_real", "nvidia_nim", "sonnet", "glm-4",
                       100, 100, "2026-08-24T11:00:00.000Z")
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    provider_entry = next(r for r in body["volume_by_provider"] if r["provider"] == "nvidia_nim")
    assert provider_entry["request_count"] == 2
    assert provider_entry["estimated_count"] == 1

    model_entry = next(r for r in body["volume_by_model"] if r["model"] == "glm-4")
    assert model_entry["estimated_count"] == 1
