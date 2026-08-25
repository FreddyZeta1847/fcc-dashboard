"""Tests for GET/PUT /pricing and POST /pricing/refresh."""

import json

import pytest
from fastapi.testclient import TestClient

from fcc_dashboard.api import app, get_db, get_pricing_config_path
from fcc_dashboard.db import init_db

SAMPLE_PRICING = {
    "anthropic": {"sonnet": {"input_per_million": 3.0, "output_per_million": 15.0}},
    "providers": {
        "nvidia_nim": {
            "glm-4": {"input_per_million": 0.0, "output_per_million": 0.0,
                      "currency": "USD", "last_updated": "2026-08-01T00:00:00.000Z",
                      "source": "manual"}
        }
    },
}


@pytest.fixture
def client_and_paths(tmp_path):
    test_db = init_db(":memory:")
    pricing_path = tmp_path / "pricing.json"
    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_pricing_config_path] = lambda: pricing_path
    yield TestClient(app), pricing_path
    app.dependency_overrides.clear()


def test_get_pricing_creates_seeded_file_when_missing(client_and_paths):
    client, pricing_path = client_and_paths
    assert not pricing_path.exists()

    response = client.get("/pricing")

    assert response.status_code == 200
    body = response.json()
    assert body["anthropic"]["opus"]["input_per_million"] == 15.0
    assert body["anthropic"]["sonnet"]["input_per_million"] == 3.0
    assert body["anthropic"]["haiku"]["input_per_million"] == 0.25
    assert body["providers"] == {}
    assert pricing_path.exists()


def test_get_pricing_returns_existing_file_unchanged(client_and_paths):
    client, pricing_path = client_and_paths
    pricing_path.write_text(json.dumps(SAMPLE_PRICING), encoding="utf-8")

    response = client.get("/pricing")

    assert response.json() == SAMPLE_PRICING


def test_put_pricing_writes_config(client_and_paths):
    client, pricing_path = client_and_paths

    response = client.put("/pricing", json=SAMPLE_PRICING)

    assert response.status_code == 200
    assert json.loads(pricing_path.read_text(encoding="utf-8")) == SAMPLE_PRICING


def test_put_pricing_rejects_malformed_body(client_and_paths):
    client, _pricing_path = client_and_paths

    response = client.put("/pricing", json={"not_the_right_shape": True})

    assert response.status_code == 422


def test_refresh_returns_diff_without_writing(client_and_paths, monkeypatch):
    client, pricing_path = client_and_paths
    pricing_path.write_text(json.dumps(SAMPLE_PRICING), encoding="utf-8")

    import fcc_dashboard.routes_pricing as routes_pricing

    async def fake_fetch_litellm_catalog():
        return {
            "nvidia_nim/glm-4": {
                "input_cost_per_token": 0.0, "output_cost_per_token": 0.0,
                "litellm_provider": "nvidia_nim",
            }
        }

    async def fake_fetch_openrouter_models():
        return {}

    monkeypatch.setattr(routes_pricing, "_fetch_litellm_catalog", fake_fetch_litellm_catalog)
    monkeypatch.setattr(routes_pricing, "_fetch_openrouter_models", fake_fetch_openrouter_models)

    response = client.post("/pricing/refresh")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["changes"], list)
    # nothing written -- config file on disk is unchanged
    assert json.loads(pricing_path.read_text(encoding="utf-8")) == SAMPLE_PRICING
