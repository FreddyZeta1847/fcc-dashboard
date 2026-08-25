"""Tests for GET /status."""

import httpx
import pytest
from fastapi.testclient import TestClient

from fcc_dashboard.api import app, get_db
from fcc_dashboard.db import init_db


@pytest.fixture
def client():
    test_db = init_db(":memory:")
    app.dependency_overrides[get_db] = lambda: test_db
    yield TestClient(app), test_db
    app.dependency_overrides.clear()


def _mock_transport(status_code):
    def handler(request):
        return httpx.Response(status_code)
    return httpx.MockTransport(handler)


def _override_fcc_health(monkeypatch, status_code=None, raise_error=False):
    """Patch the httpx client used for the FCC health check."""
    import fcc_dashboard.routes_status as routes_status

    async def fake_check(*args, **kwargs):
        if raise_error:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(status_code)

    monkeypatch.setattr(routes_status, "_check_fcc_health", fake_check)


def test_status_fcc_up_no_errors(monkeypatch):
    test_db = init_db(":memory:")
    app.dependency_overrides[get_db] = lambda: test_db
    _override_fcc_health(monkeypatch, status_code=200)
    client = TestClient(app)

    response = client.get("/status")

    assert response.status_code == 200
    body = response.json()
    assert body["fcc_status"] == "up"
    assert body["providers"] == []
    app.dependency_overrides.clear()


def test_status_fcc_down_on_connection_error(monkeypatch):
    test_db = init_db(":memory:")
    app.dependency_overrides[get_db] = lambda: test_db
    _override_fcc_health(monkeypatch, raise_error=True)
    client = TestClient(app)

    response = client.get("/status")

    assert response.status_code == 200
    assert response.json()["fcc_status"] == "down"
    app.dependency_overrides.clear()


def test_status_reports_stale_key_and_rate_limited_providers(monkeypatch):
    test_db = init_db(":memory:")
    app.dependency_overrides[get_db] = lambda: test_db
    _override_fcc_health(monkeypatch, status_code=200)
    client = TestClient(app)

    test_db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, "
        "status, http_status) VALUES (?, ?, ?, ?, 'error', ?)",
        ("req_1", "nvidia_nim", "2026-08-24T10:00:00.000Z", "2026-08-24T10:00:00.000Z", 401),
    )
    test_db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, "
        "status, http_status) VALUES (?, ?, ?, ?, 'error', ?)",
        ("req_2", "openrouter", "2026-08-24T10:05:00.000Z", "2026-08-24T10:05:00.000Z", 429),
    )
    test_db.commit()

    response = client.get("/status")

    body = response.json()
    by_provider = {p["provider"]: p for p in body["providers"]}
    assert by_provider["nvidia_nim"]["status"] == "stale_key"
    assert by_provider["openrouter"]["status"] == "rate_limited"
    app.dependency_overrides.clear()


def test_status_uses_most_recent_error_per_provider(monkeypatch):
    test_db = init_db(":memory:")
    app.dependency_overrides[get_db] = lambda: test_db
    _override_fcc_health(monkeypatch, status_code=200)
    client = TestClient(app)

    # Older error: 401 (stale key). Newer error: 500 (down). Must report the newer.
    test_db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, "
        "status, http_status) VALUES (?, ?, ?, ?, 'error', ?)",
        ("req_1", "nvidia_nim", "2026-08-24T10:00:00.000Z", "2026-08-24T10:00:00.000Z", 401),
    )
    test_db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, "
        "status, http_status) VALUES (?, ?, ?, ?, 'error', ?)",
        ("req_2", "nvidia_nim", "2026-08-24T11:00:00.000Z", "2026-08-24T11:00:00.000Z", 500),
    )
    test_db.commit()

    response = client.get("/status")

    body = response.json()
    assert len(body["providers"]) == 1
    assert body["providers"][0]["status"] == "down"
    assert body["providers"][0]["http_status"] == 500
    app.dependency_overrides.clear()
