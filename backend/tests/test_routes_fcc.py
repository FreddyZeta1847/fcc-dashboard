"""Tests for GET /fcc/catalog.

Covers the route's contract rather than the parsing (that lives in
`test_fcc_admin.py`): that it always returns 200 even when FCC is unreachable,
and that `observed_providers` reports what our own `requests` table has
actually seen -- the cross-check that would expose a stale provider log tag
after an FCC upgrade.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from fcc_dashboard import fcc_admin
from fcc_dashboard.api import app, get_db
from fcc_dashboard.db import init_db

CONFIGURED_PAYLOAD = {
    "provider_status": [
        {
            "provider_id": "nvidia_nim",
            "display_name": "NVIDIA NIM",
            "kind": "remote",
            "status": "configured",
        },
        {
            "provider_id": "ollama",
            "display_name": "Ollama",
            "kind": "local",
            "status": "configured",
        },
    ],
    "cached_models": {
        "nvidia_nim": ["deepseek-ai/deepseek-v4-flash-0731"],
        "ollama": ["gemma3:4b", "phi3:mini"],
    },
}


@pytest.fixture
def client():
    test_db = init_db(":memory:")
    app.dependency_overrides[get_db] = lambda: test_db
    yield TestClient(app), test_db
    app.dependency_overrides.clear()


def _override_fcc_admin(monkeypatch, payload=None, raise_error=None, status_code=200):
    async def fake_fetch():
        if raise_error is not None:
            raise raise_error
        return httpx.Response(
            status_code=status_code,
            json=payload,
            request=httpx.Request("GET", "http://127.0.0.1:8082/admin/api/status"),
        )

    monkeypatch.setattr(fcc_admin, "_fetch_admin_status", fake_fetch)


def _insert_request(db, request_id, provider):
    db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, status)"
        " VALUES (?, ?, '2026-08-27T10:00:00Z', '2026-08-27T10:00:00Z', 'completed')",
        (request_id, provider),
    )
    db.commit()


def test_catalog_returns_configured_providers(client, monkeypatch):
    test_client, _ = client
    _override_fcc_admin(monkeypatch, payload=CONFIGURED_PAYLOAD)

    response = test_client.get("/fcc/catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["error"] is None

    by_id = {p["provider_id"]: p for p in body["providers"]}
    assert by_id["nvidia_nim"]["log_tag"] == "NIM"
    assert by_id["ollama"]["log_tag"] == "OLLAMA"
    assert "gemma3:4b" in by_id["ollama"]["models"]


def test_catalog_returns_200_when_fcc_is_down(client, monkeypatch):
    """FCC being stopped is ordinary -- the UI needs a body, not an error status."""
    test_client, _ = client
    _override_fcc_admin(monkeypatch, raise_error=httpx.ConnectError("refused"))

    response = test_client.get("/fcc/catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["providers"] == []
    assert body["error"]


def test_observed_providers_is_empty_with_no_requests(client, monkeypatch):
    test_client, _ = client
    _override_fcc_admin(monkeypatch, payload=CONFIGURED_PAYLOAD)

    body = test_client.get("/fcc/catalog").json()

    assert body["observed_providers"] == []


def test_observed_providers_reports_distinct_stored_values(client, monkeypatch):
    test_client, test_db = client
    _insert_request(test_db, "req_1", "NIM")
    _insert_request(test_db, "req_2", "NIM")
    _insert_request(test_db, "req_3", "OLLAMA")
    _override_fcc_admin(monkeypatch, payload=CONFIGURED_PAYLOAD)

    body = test_client.get("/fcc/catalog").json()

    assert body["observed_providers"] == ["NIM", "OLLAMA"]


def test_observed_providers_skips_null_and_empty(client, monkeypatch):
    """A pending row created by an orphan completion can have a NULL provider."""
    test_client, test_db = client
    _insert_request(test_db, "req_1", None)
    _insert_request(test_db, "req_2", "")
    _insert_request(test_db, "req_3", "NIM")
    _override_fcc_admin(monkeypatch, payload=CONFIGURED_PAYLOAD)

    body = test_client.get("/fcc/catalog").json()

    assert body["observed_providers"] == ["NIM"]


def test_observed_providers_still_reported_when_fcc_is_down(client, monkeypatch):
    """The DB half must not depend on FCC being reachable."""
    test_client, test_db = client
    _insert_request(test_db, "req_1", "NIM")
    _override_fcc_admin(monkeypatch, raise_error=httpx.ConnectError("refused"))

    body = test_client.get("/fcc/catalog").json()

    assert body["available"] is False
    assert body["observed_providers"] == ["NIM"]


def test_log_tag_matches_a_real_observed_provider(client, monkeypatch):
    """The cross-check this whole feature rests on.

    A row stored by the collector for FCC's `nvidia_nim` provider holds `NIM`.
    The catalog's `log_tag` for that provider must equal it, or prices written
    through the picker would never match a request.
    """
    test_client, test_db = client
    _insert_request(test_db, "req_1", "NIM")
    _override_fcc_admin(monkeypatch, payload=CONFIGURED_PAYLOAD)

    body = test_client.get("/fcc/catalog").json()

    nim = next(p for p in body["providers"] if p["provider_id"] == "nvidia_nim")
    assert nim["log_tag"] in body["observed_providers"]
