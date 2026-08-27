"""
Read FCC's own configured providers and models, for the pricing picker.

Pricing is looked up by an exact `(provider, downstream_model)` string match
(see `pricing.lookup_price`), and a miss is *silent*: the request is counted as
unpriced and quietly dropped from savings, with no error anywhere. Typing those
two strings by hand is therefore the most error-prone part of configuring this
app. Since a model that isn't configured in FCC can never produce a request row
at all, FCC's own configuration is the only useful set of choices -- so ask FCC
instead of asking the user to remember.

FCC exposes everything needed in one call, `GET /admin/api/status`:

- `provider_status[]` -- every provider in its catalog with a `status` of
  `configured` / `missing_key` / `missing_config`.
- `cached_models{}`   -- a `provider_id -> [model_id]` map.

Two things about that endpoint are worth knowing before changing this module:

1. **Auth.** FCC's `/admin/api/*` routes are gated by a loopback check only, not
   by the bearer token its `/v1/*` proxy routes require. The check also rejects
   a non-local `Origin` header but accepts the header being *absent*, so this
   module must not send one.
2. **`cached_models` is a cache**, filled lazily by FCC's model discovery. An
   empty map means "not discovered yet", not "this provider has no models" --
   so an absent provider yields an empty model list here, never an error. FCC's
   `POST /admin/api/models/refresh` forces a live upstream re-fetch; this module
   deliberately does not call it (it would make a read surprisingly expensive).

Nothing here raises to its caller. FCC being stopped is an ordinary state for
this app -- it can even stop FCC itself via `/control/stop` -- so every failure
becomes `FccCatalog(available=False, error=...)` and the UI falls back to manual
entry.
"""

from __future__ import annotations

import os

import httpx
from pydantic import BaseModel

#: FCC's gateway root. Override for tests or a non-default FCC port.
DEFAULT_FCC_ADMIN_BASE = "http://127.0.0.1:8082"

FCC_ADMIN_STATUS_PATH = "/admin/api/status"

#: Short: this is a picker, not a critical path. If FCC is slow, fall back to
#: manual entry rather than making the Settings page hang.
FCC_ADMIN_TIMEOUT = 3.0

#: Only providers FCC reports with this status can actually serve traffic.
_CONFIGURED_STATUS = "configured"

#: FCC tags each request in its logs with a per-provider constant -- the
#: `provider_name` on its request policy -- and *that* string, not the
#: provider id, is what the collector stores in `requests.provider`. It is
#: usually the id upper-cased, but not always, and it is not exposed by any
#: FCC endpoint. So this table is a deliberate copy of FCC internals.
#:
#: Getting it wrong is worse than the free-text field it replaces: a picker
#: emitting an unmatched string looks authoritative while silently producing
#: rows that never price. `routes_fcc` cross-checks these against the provider
#: values actually observed in the database, which is how a drift shows up.
#:
#: To re-derive after an FCC upgrade, grep its package for `provider_name=`.
_LOG_TAG_OVERRIDES = {
    "nvidia_nim": "NIM",  # not NVIDIA_NIM
    "openai": "OpenAI",  # mixed case, not OPENAI
    "open_router": "OPENROUTER",  # not OPEN_ROUTER
    "mistral_codestral": "CODESTRAL",  # not MISTRAL_CODESTRAL
}


class FccProvider(BaseModel):
    """One provider FCC reports as configured, with the models it can serve."""

    provider_id: str
    display_name: str
    log_tag: str
    kind: str
    models: list[str]


class FccCatalog(BaseModel):
    """What FCC currently has configured, or why we could not find out.

    `available=False` is a normal outcome, not an error condition: FCC may
    simply not be running. `providers` is empty in that case and `error`
    carries a short human-readable reason for the UI to show.
    """

    available: bool
    providers: list[FccProvider]
    error: str | None = None


def get_fcc_admin_base() -> str:
    """FCC's base URL, with an `FCC_ADMIN_URL` override.

    Same call-time-not-import-time override seam as
    `dependencies.get_pricing_config_path` and `get_fcc_log_path`, so a test
    can point this at a local stub server.
    """
    override = os.environ.get("FCC_ADMIN_URL", "").strip()
    return override.rstrip("/") if override else DEFAULT_FCC_ADMIN_BASE


def provider_log_tag(provider_id: str) -> str:
    """The string FCC writes into its logs for `provider_id`.

    Defaults to the id upper-cased, which is right for most of FCC's catalog;
    the exceptions live in `_LOG_TAG_OVERRIDES`.
    """
    return _LOG_TAG_OVERRIDES.get(provider_id, provider_id.upper())


async def _fetch_admin_status() -> httpx.Response:
    """GET FCC's admin status endpoint.

    A bare module-level `async def` on purpose: tests intercept it with
    `monkeypatch.setattr(fcc_admin, "_fetch_admin_status", ...)`, which only
    works because the caller looks the name up on the module at call time.
    This mirrors `routes_status._check_fcc_health`.

    Sends no `Origin` header -- see the module docstring. May raise any httpx
    exception; `fetch_fcc_catalog` is responsible for absorbing it.
    """
    url = f"{get_fcc_admin_base()}{FCC_ADMIN_STATUS_PATH}"
    async with httpx.AsyncClient(timeout=FCC_ADMIN_TIMEOUT) as client:
        return await client.get(url)


def _model_ids_for(cached_models: object, provider_id: str) -> list[str]:
    """Model ids FCC has discovered for one provider, defensively parsed.

    Returns `[]` for anything unexpected rather than raising: an empty list
    means "nothing discovered yet", which is exactly how a not-yet-warm cache
    should read.
    """
    if not isinstance(cached_models, dict):
        return []
    models = cached_models.get(provider_id)
    if not isinstance(models, list):
        return []
    return sorted(str(model) for model in models if isinstance(model, str))


def _parse_providers(payload: dict) -> list[FccProvider]:
    """Configured providers from an `/admin/api/status` payload.

    Every field is checked before use. This payload comes from a separate
    program on a version we do not control, so a shape change must degrade to
    "fewer providers listed", never to a 500 on our Settings page.
    """
    provider_status = payload.get("provider_status")
    if not isinstance(provider_status, list):
        return []

    cached_models = payload.get("cached_models")
    providers: list[FccProvider] = []

    for entry in provider_status:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != _CONFIGURED_STATUS:
            continue
        provider_id = entry.get("provider_id")
        if not isinstance(provider_id, str) or not provider_id:
            continue

        display_name = entry.get("display_name")
        kind = entry.get("kind")
        providers.append(
            FccProvider(
                provider_id=provider_id,
                display_name=(
                    display_name if isinstance(display_name, str) and display_name
                    else provider_id
                ),
                log_tag=provider_log_tag(provider_id),
                kind=kind if isinstance(kind, str) and kind else "unknown",
                models=_model_ids_for(cached_models, provider_id),
            )
        )

    providers.sort(key=lambda p: p.display_name.casefold())
    return providers


async def fetch_fcc_catalog() -> FccCatalog:
    """FCC's configured providers and their models. Never raises.

    Every failure mode -- FCC not running, slow, returning a non-200, or
    returning something that is not the JSON object we expect -- collapses into
    `available=False` with a short reason, because the caller's only sensible
    response to any of them is the same: fall back to manual entry.
    """
    try:
        response = await _fetch_admin_status()
    except httpx.HTTPError as exc:
        return FccCatalog(
            available=False,
            providers=[],
            error=f"Could not reach FCC at {get_fcc_admin_base()} ({type(exc).__name__}).",
        )

    if response.status_code != 200:
        return FccCatalog(
            available=False,
            providers=[],
            error=f"FCC returned HTTP {response.status_code} for {FCC_ADMIN_STATUS_PATH}.",
        )

    try:
        payload = response.json()
    except ValueError:
        return FccCatalog(
            available=False,
            providers=[],
            error="FCC returned a response that was not valid JSON.",
        )

    if not isinstance(payload, dict):
        return FccCatalog(
            available=False,
            providers=[],
            error="FCC returned an unexpected response shape.",
        )

    return FccCatalog(available=True, providers=_parse_providers(payload), error=None)
