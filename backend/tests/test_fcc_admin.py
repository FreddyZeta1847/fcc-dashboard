"""Unit tests for backend.fcc_dashboard.fcc_admin.

The network call is stubbed by rebinding the module-level `_fetch_admin_status`
name -- the same interception `routes_status._check_fcc_health` is designed for.
Nothing here touches a real FCC.

Async tests drive the coroutine with `asyncio.run()` from a sync test body,
matching `test_collector.py`; this project has no pytest async plugin and does
not need one for calls this simple.

The payloads below are trimmed copies of a real `GET /admin/api/status`
response from a live FCC (v5.14.3), so parsing is tested against the actual
shape rather than an invented one.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from fcc_dashboard import fcc_admin
from fcc_dashboard.fcc_admin import fetch_fcc_catalog, provider_log_tag

# Trimmed from a real response: two configured providers (one remote, one
# local) and one present in FCC's catalog but not usable.
REAL_STATUS_PAYLOAD = {
    "status": "ok",
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
        {
            "provider_id": "groq",
            "display_name": "Groq",
            "kind": "remote",
            "status": "missing_key",
        },
    ],
    "cached_models": {
        "nvidia_nim": ["deepseek-ai/deepseek-v4-flash-0731", "01-ai/yi-large"],
        "ollama": ["gemma3:4b", "phi3:mini", "qwen2:7b"],
    },
}


def _stub_response(payload, status_code=200):
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "http://127.0.0.1:8082/admin/api/status"),
    )


@pytest.fixture
def catalog_from(monkeypatch):
    """Stub FCC's admin call, then run `fetch_fcc_catalog()` and return it."""

    def _run(response=None, raises=None):
        async def _fake():
            if raises is not None:
                raise raises
            return response

        monkeypatch.setattr(fcc_admin, "_fetch_admin_status", _fake)
        return asyncio.run(fetch_fcc_catalog())

    return _run


# --- provider_log_tag: the load-bearing mapping --------------------------


def test_log_tag_defaults_to_uppercase():
    assert provider_log_tag("ollama") == "OLLAMA"
    assert provider_log_tag("groq") == "GROQ"


def test_log_tag_uses_overrides_for_the_irregular_providers():
    """These four do NOT follow the upper-case rule -- see _LOG_TAG_OVERRIDES."""
    assert provider_log_tag("nvidia_nim") == "NIM"
    assert provider_log_tag("openai") == "OpenAI"
    assert provider_log_tag("open_router") == "OPENROUTER"
    assert provider_log_tag("mistral_codestral") == "CODESTRAL"


def test_log_tag_for_nvidia_nim_matches_what_the_collector_stores():
    """Guards the one mapping this project has real log evidence for.

    A live database row for FCC's `nvidia_nim` provider stores `NIM`. If this
    ever fails, every price written through the picker for NIM would silently
    stop matching any request.
    """
    assert provider_log_tag("nvidia_nim") == "NIM"


# --- parsing a real payload ----------------------------------------------


def test_parses_configured_providers_with_models(catalog_from):
    catalog = catalog_from(_stub_response(REAL_STATUS_PAYLOAD))

    assert catalog.available is True
    assert catalog.error is None

    by_id = {p.provider_id: p for p in catalog.providers}
    assert set(by_id) == {"nvidia_nim", "ollama"}

    nim = by_id["nvidia_nim"]
    assert nim.log_tag == "NIM"
    assert nim.display_name == "NVIDIA NIM"
    assert nim.kind == "remote"
    assert "deepseek-ai/deepseek-v4-flash-0731" in nim.models

    ollama = by_id["ollama"]
    assert ollama.log_tag == "OLLAMA"
    assert ollama.kind == "local"
    assert "gemma3:4b" in ollama.models


def test_unconfigured_providers_are_excluded(catalog_from):
    catalog = catalog_from(_stub_response(REAL_STATUS_PAYLOAD))

    assert "groq" not in {p.provider_id for p in catalog.providers}


def test_models_are_sorted(catalog_from):
    catalog = catalog_from(_stub_response(REAL_STATUS_PAYLOAD))

    nim = next(p for p in catalog.providers if p.provider_id == "nvidia_nim")
    assert nim.models == sorted(nim.models)


def test_provider_absent_from_cache_still_listed_with_no_models(catalog_from):
    """An unwarmed model cache must read as 'nothing discovered yet'."""
    catalog = catalog_from(
        _stub_response(
            {
                "provider_status": [
                    {
                        "provider_id": "ollama",
                        "display_name": "Ollama",
                        "kind": "local",
                        "status": "configured",
                    }
                ],
                "cached_models": {},
            }
        )
    )

    assert catalog.available is True
    assert len(catalog.providers) == 1
    assert catalog.providers[0].models == []


# --- degradation: every failure must yield available=False ---------------


def test_connection_error_reports_unavailable(catalog_from):
    catalog = catalog_from(raises=httpx.ConnectError("connection refused"))

    assert catalog.available is False
    assert catalog.providers == []
    assert catalog.error is not None
    assert "Could not reach FCC" in catalog.error


def test_timeout_reports_unavailable(catalog_from):
    catalog = catalog_from(raises=httpx.ReadTimeout("too slow"))

    assert catalog.available is False
    assert catalog.providers == []


def test_non_200_reports_unavailable(catalog_from):
    """A 403 is the realistic case -- FCC rejects non-loopback admin calls."""
    catalog = catalog_from(
        _stub_response({"detail": "Admin UI is local-only"}, status_code=403)
    )

    assert catalog.available is False
    assert catalog.error is not None
    assert "403" in catalog.error


def test_malformed_json_reports_unavailable(monkeypatch):
    response = httpx.Response(
        status_code=200,
        content=b"not json at all",
        request=httpx.Request("GET", "http://127.0.0.1:8082/admin/api/status"),
    )

    async def _fake():
        return response

    monkeypatch.setattr(fcc_admin, "_fetch_admin_status", _fake)
    catalog = asyncio.run(fetch_fcc_catalog())

    assert catalog.available is False
    assert catalog.error is not None
    assert "valid JSON" in catalog.error


def test_json_that_is_not_an_object_reports_unavailable(catalog_from):
    catalog = catalog_from(_stub_response(["unexpected", "shape"]))

    assert catalog.available is False


# --- defensive parsing: a shape change must not 500 ----------------------


def test_missing_provider_status_key_yields_no_providers(catalog_from):
    catalog = catalog_from(_stub_response({"status": "ok"}))

    assert catalog.available is True
    assert catalog.providers == []


def test_garbage_entries_are_skipped_not_fatal(catalog_from):
    catalog = catalog_from(
        _stub_response(
            {
                "provider_status": [
                    "not a dict",
                    {"status": "configured"},  # no provider_id
                    {"provider_id": "", "status": "configured"},  # empty id
                    {"provider_id": "ollama", "status": "configured"},  # no name/kind
                ],
                "cached_models": {"ollama": ["gemma3:4b", 42, None]},
            }
        )
    )

    assert catalog.available is True
    assert len(catalog.providers) == 1
    provider = catalog.providers[0]
    assert provider.provider_id == "ollama"
    assert provider.display_name == "ollama"  # falls back to the id
    assert provider.kind == "unknown"
    assert provider.models == ["gemma3:4b"]  # non-strings dropped


def test_cached_models_of_wrong_type_yields_empty_list(catalog_from):
    catalog = catalog_from(
        _stub_response(
            {
                "provider_status": [
                    {
                        "provider_id": "ollama",
                        "display_name": "Ollama",
                        "status": "configured",
                    }
                ],
                "cached_models": "not a dict",
            }
        )
    )

    assert catalog.providers[0].models == []


# --- the base-URL override seam ------------------------------------------


def test_admin_base_uses_env_override(monkeypatch):
    monkeypatch.setenv("FCC_ADMIN_URL", "http://127.0.0.1:9999/")
    assert fcc_admin.get_fcc_admin_base() == "http://127.0.0.1:9999"


def test_admin_base_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("FCC_ADMIN_URL", raising=False)
    assert fcc_admin.get_fcc_admin_base() == fcc_admin.DEFAULT_FCC_ADMIN_BASE


def test_blank_admin_base_override_is_ignored(monkeypatch):
    monkeypatch.setenv("FCC_ADMIN_URL", "   ")
    assert fcc_admin.get_fcc_admin_base() == fcc_admin.DEFAULT_FCC_ADMIN_BASE
