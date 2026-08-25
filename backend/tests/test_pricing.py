"""Unit tests for backend.fcc_dashboard.pricing."""

import json

import pytest

from fcc_dashboard.pricing import (
    compute_cost,
    load_pricing_config,
    lookup_anthropic_price,
    lookup_price,
)

SAMPLE_CONFIG = {
    "anthropic": {
        "sonnet": {"input_per_million": 3.0, "output_per_million": 15.0},
        "opus": {"input_per_million": 15.0, "output_per_million": 75.0},
    },
    "providers": {
        "nvidia_nim": {
            "glm-4": {
                "input_per_million": 0.0,
                "output_per_million": 0.0,
                "currency": "USD",
                "last_updated": "2026-08-01T00:00:00.000Z",
                "source": "manual",
            }
        },
        "openrouter": {
            "glm-4": {
                "input_per_million": 0.5,
                "output_per_million": 1.5,
                "currency": "USD",
                "last_updated": "2026-08-01T00:00:00.000Z",
                "source": "litellm_catalog",
            }
        },
    },
}


def test_load_pricing_config_reads_json_file(tmp_path):
    config_path = tmp_path / "pricing.json"
    config_path.write_text(json.dumps(SAMPLE_CONFIG), encoding="utf-8")

    loaded = load_pricing_config(config_path)

    assert loaded == SAMPLE_CONFIG


def test_lookup_price_found():
    price = lookup_price(SAMPLE_CONFIG, "nvidia_nim", "glm-4")
    assert price == SAMPLE_CONFIG["providers"]["nvidia_nim"]["glm-4"]


def test_lookup_price_same_model_different_provider_different_price():
    nim_price = lookup_price(SAMPLE_CONFIG, "nvidia_nim", "glm-4")
    openrouter_price = lookup_price(SAMPLE_CONFIG, "openrouter", "glm-4")
    assert nim_price["input_per_million"] == 0.0
    assert openrouter_price["input_per_million"] == 0.5


def test_lookup_price_not_found_returns_none():
    assert lookup_price(SAMPLE_CONFIG, "nonexistent_provider", "glm-4") is None
    assert lookup_price(SAMPLE_CONFIG, "nvidia_nim", "nonexistent_model") is None


def test_lookup_anthropic_price_found():
    price = lookup_anthropic_price(SAMPLE_CONFIG, "sonnet")
    assert price == SAMPLE_CONFIG["anthropic"]["sonnet"]


def test_lookup_anthropic_price_not_found_returns_none():
    assert lookup_anthropic_price(SAMPLE_CONFIG, "nonexistent_tier") is None


def test_compute_cost_basic():
    price = {"input_per_million": 3.0, "output_per_million": 15.0}
    # 1,000,000 input tokens + 1,000,000 output tokens = $3 + $15 = $18
    assert compute_cost(price, input_tokens=1_000_000, output_tokens=1_000_000) == 18.0


def test_compute_cost_zero_price():
    price = {"input_per_million": 0.0, "output_per_million": 0.0}
    assert compute_cost(price, input_tokens=500_000, output_tokens=200_000) == 0.0


def test_compute_cost_fractional_tokens():
    price = {"input_per_million": 3.0, "output_per_million": 15.0}
    # 500,000 input tokens = half of 1M = $1.50
    assert compute_cost(price, input_tokens=500_000, output_tokens=0) == 1.5
