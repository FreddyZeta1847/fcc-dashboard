"""
`GET`/`PUT /pricing` and `POST /pricing/refresh` -- read, write, and
best-effort-refresh the pricing config file PRICING-ENGINE (Phase 1) reads
via `load_pricing_config`.

Follows the conventions `routes_status.py`, `routes_requests.py`, and
`routes_stats.py` established for this phase: `get_db` and
`get_pricing_config_path` come from `dependencies.py`, never from `api.py`
(avoids the circular import `dependencies.py`'s docstring explains); the
response shapes are Pydantic models, not bare dicts.

This is the first route in the app that WRITES the pricing config file --
`routes_stats.py`'s docstring is explicit that `GET /stats` never does, and
leaves that job to this module. Two of the three routes here are therefore
`def` (plain sync file I/O, like every other route so far) but
`POST /pricing/refresh` is `async def`: it makes two real outbound HTTP
calls (LiteLLM's public catalog, OpenRouter's public models list) and must
never block the event loop's worker thread pool doing that, unlike the
sync-only routes.

Network isolation for `/pricing/refresh` follows `routes_status.py`'s
`_check_fcc_health` pattern exactly: `_fetch_litellm_catalog` and
`_fetch_openrouter_models` are bare module-level `async def` functions,
called by name at request time (not captured in a closure at import time),
so `monkeypatch.setattr(routes_pricing, "_fetch_litellm_catalog", ...)`
in tests actually takes effect. No test in this project's suite may ever
cause a real network call -- see `test_routes_pricing.py`'s
`test_refresh_returns_diff_without_writing`.

Matching logic (LiteLLM/OpenRouter diff against the configured
`(provider, model)` pairs) is deliberately best-effort, per this task's own
brief: PRICING-ENGINE's design never verified exact coverage of FCC's ~20
providers in LiteLLM's catalog, so guessing at a shaky match would be worse
than reporting `not_found` and letting a human confirm it manually. See
`_match_in_litellm_catalog` and `_match_in_openrouter_models` below for the
exact rules.
"""

import copy
import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, model_validator

from .dependencies import get_db, get_pricing_config_path  # noqa: F401 (get_db kept for dependency-pattern consistency)
from .pricing import _validate_price_entry, load_pricing_config

router = APIRouter()

LITELLM_CATALOG_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_FETCH_TIMEOUT = 10.0

# The Anthropic tiers FCC's `gateway_model` field can carry, and the current
# official per-million-token list price for each (platform.claude.com/docs/en/about-claude/pricing,
# checked 2026-08-25). These are the literal model ID strings Claude Code
# sends as `model` in its request -- FCC passes that value straight through
# as `gateway_model` (see free_claude_code.core.gateway_model_ids), it is
# not FCC's own naming -- so a future Claude Code model release can add or
# rename a tier here without any FCC-side change.
REQUIRED_ANTHROPIC_TIERS: tuple[str, ...] = (
    "claude-fable-5",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
)

SEEDED_DEFAULT_PRICING: dict[str, Any] = {
    "anthropic": {
        "claude-fable-5": {"input_per_million": 10.0, "output_per_million": 50.0},
        "claude-opus-5": {"input_per_million": 5.0, "output_per_million": 25.0},
        "claude-sonnet-5": {"input_per_million": 2.0, "output_per_million": 10.0},
        "claude-haiku-4-5-20251001": {"input_per_million": 1.0, "output_per_million": 5.0},
    },
    "providers": {},
}


class PricingConfig(BaseModel):
    """The full pricing config document -- PRICING-ENGINE's schema.

    Beyond "well-formed JSON object", this model enforces the one thing
    `GET /stats` genuinely depends on at read time: every Anthropic tier in
    `REQUIRED_ANTHROPIC_TIERS` must be present under `anthropic`, each with
    a valid `{input_per_million, output_per_million}` shape --
    reusing `pricing.py`'s own `_validate_price_entry` rather than
    duplicating its rules. Without this, an incomplete `PUT /pricing` body
    (e.g. `{"anthropic": {}, "providers": {}}`) would pass validation here
    and only blow up later, as an uncaught `ValueError` out of
    `compute_savings`, when `GET /stats` tries to price a row against a
    tier that was never configured -- a write-time mistake surfacing as a
    500 at read time instead of a 422 at write time.

    `providers` has no default: `PUT /pricing` replaces the whole file, so
    a body that simply omits `"providers"` must be rejected (422), not
    silently treated as "no providers" and used to wipe every existing
    provider price on disk.

    `model_config = ConfigDict(extra="allow")` plus a permissive
    `providers` value type means a well-formed document still round-trips
    through this model unchanged -- this route validates the two
    contractual pieces above, but is not a schema owner for the rest of
    the document (e.g. individual provider price entries aren't validated
    here; `pricing.py`'s lookup functions still validate those defensively
    wherever they're actually used).
    """

    model_config = ConfigDict(extra="allow")

    anthropic: dict[str, Any]
    providers: dict[str, Any]

    @model_validator(mode="after")
    def _anthropic_has_all_required_tiers(self) -> "PricingConfig":
        if not isinstance(self.anthropic, dict):
            raise ValueError("'anthropic' must be an object")

        for tier in REQUIRED_ANTHROPIC_TIERS:
            entry = self.anthropic.get(tier)
            if entry is None:
                raise ValueError(
                    f"'anthropic' is missing required tier {tier!r}"
                )
            if not isinstance(entry, dict):
                raise ValueError(
                    f"'anthropic' tier {tier!r} must be an object"
                )
            try:
                _validate_price_entry(entry, context=f"anthropic tier {tier!r}")
            except ValueError as exc:
                raise ValueError(str(exc)) from exc

        return self


class PricingChange(BaseModel):
    provider: str
    model: str
    current: dict[str, Any] | None
    proposed: dict[str, Any] | None
    source: str
    changed: bool


class PricingPairNotFound(BaseModel):
    provider: str
    model: str


class PricingRefreshResponse(BaseModel):
    changes: list[PricingChange]
    not_found: list[PricingPairNotFound]


async def _fetch_litellm_catalog() -> dict[str, Any]:
    """Fetch LiteLLM's public model-price catalog (the primary price source).

    A bare module-level function, deliberately -- see module docstring.
    Real callers get the actual JSON document (a flat `{"<key>": {...}}`
    map); `routes_pricing.py`'s tests replace this name entirely via
    `monkeypatch.setattr`, so no test ever reaches this body.
    """
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
        response = await client.get(LITELLM_CATALOG_URL)
        response.raise_for_status()
        return response.json()


async def _fetch_openrouter_models() -> dict[str, Any]:
    """Fetch OpenRouter's public models list (the secondary cross-check
    source), reshaped into a `{"<model id>": {<entry>}}` map keyed the same
    way `_match_in_openrouter_models` expects to look it up.

    A bare module-level function, deliberately -- see module docstring and
    `_fetch_litellm_catalog`.
    """
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
        response = await client.get(OPENROUTER_MODELS_URL)
        response.raise_for_status()
        body = response.json()
        return {entry["id"]: entry for entry in body.get("data", []) if "id" in entry}


def _configured_pairs(config: dict) -> list[tuple[str, str]]:
    """Every `(provider, model)` pair a refresh should attempt to price:
    the three Anthropic tiers (always -- FCC always routes through one of
    them) plus every pair currently under `"providers"` in the config file.
    Order is deterministic (Anthropic tiers first in their fixed order,
    then providers/models sorted) so the response is stable across runs.
    """
    pairs = [("anthropic", tier) for tier in REQUIRED_ANTHROPIC_TIERS]
    providers = config.get("providers", {})
    for provider in sorted(providers):
        for model in sorted(providers[provider]):
            pairs.append((provider, model))
    return pairs


def _current_price(config: dict, provider: str, model: str) -> dict[str, Any] | None:
    """The currently-configured price for a pair, or None if unconfigured.
    Only reads `input_per_million`/`output_per_million` even if the stored
    entry carries extra bookkeeping fields (`currency`, `source`, ...) --
    `current`/`proposed` in the response are meant to be directly
    comparable, so both sides are normalized to the same two-key shape.
    """
    if provider == "anthropic":
        entry = config.get("anthropic", {}).get(model)
    else:
        entry = config.get("providers", {}).get(provider, {}).get(model)
    if entry is None:
        return None
    return {
        "input_per_million": entry.get("input_per_million"),
        "output_per_million": entry.get("output_per_million"),
    }


def _per_million_from_per_token(cost_per_token: Any) -> float | None:
    """LiteLLM prices per-token (`input_cost_per_token`); this project's
    config prices per-million-tokens. None if the source field is missing
    or non-numeric -- callers treat that as "this entry doesn't actually
    give us a usable price", not as a zero price.
    """
    if not isinstance(cost_per_token, (int, float)):
        return None
    return cost_per_token * 1_000_000


def _match_in_litellm_catalog(
    catalog: dict[str, Any], provider: str, model: str
) -> dict[str, Any] | None:
    """Best-effort match of a `(provider, model)` pair against LiteLLM's
    catalog.

    LiteLLM's keys are either `"<provider>/<model>"` or a bare `"<model>"`
    with a separate `"litellm_provider"` field on the entry -- the brief is
    explicit that exact coverage/shape was never verified, so this tries,
    in order, the cheap exact matches first and only falls back to a loose
    substring match as a last resort:

    1. Exact key `"<provider>/<model>"`.
    2. Exact key `"<model>"` whose entry's `litellm_provider` equals
       `provider` (case-insensitive -- LiteLLM's provider slugs aren't
       guaranteed to match FCC's casing exactly).
    3. Any entry whose `litellm_provider` matches (case-insensitive) AND
       whose key (after stripping any `"<provider>/"` prefix) contains
       `model`, or vice versa, as a substring (case-insensitive) -- catches
       minor naming drift (e.g. configured `"glm-4"` vs catalog
       `"glm-4-32b"`) without guessing across an unrelated model family.

    Returns None (-> `not_found`) rather than guessing further if nothing
    matches -- per the brief, a missed match is preferable to a wrong one.
    """
    direct_key = f"{provider}/{model}"
    if direct_key in catalog:
        return catalog[direct_key]

    if model in catalog:
        entry = catalog[model]
        if str(entry.get("litellm_provider", "")).lower() == provider.lower():
            return entry

    provider_lower = provider.lower()
    model_lower = model.lower()
    for key, entry in catalog.items():
        if str(entry.get("litellm_provider", "")).lower() != provider_lower:
            continue
        bare_key = key.split("/", 1)[1] if "/" in key else key
        bare_key_lower = bare_key.lower()
        if model_lower in bare_key_lower or bare_key_lower in model_lower:
            return entry

    return None


def _match_in_openrouter_models(
    models: dict[str, Any], provider: str, model: str
) -> dict[str, Any] | None:
    """Best-effort match of a `(provider, model)` pair against OpenRouter's
    models list (the secondary cross-check, only consulted when LiteLLM
    didn't cover a pair).

    OpenRouter ids are `"<vendor-slug>/<model-slug>"` -- there's no
    guarantee `provider` (FCC's own provider naming) lines up with
    OpenRouter's vendor slug, so this matches by `model` alone: an exact
    id match, then a substring match on the id, same reasoning as the
    LiteLLM fallback above (a missed match beats a wrong one).
    """
    model_lower = model.lower()
    if model in models:
        return models[model]

    for model_id, entry in models.items():
        slug = model_id.split("/", 1)[1] if "/" in model_id else model_id
        if model_lower in slug.lower():
            return entry
    return None


def _proposed_from_litellm(entry: dict[str, Any]) -> dict[str, Any] | None:
    input_per_million = _per_million_from_per_token(entry.get("input_cost_per_token"))
    output_per_million = _per_million_from_per_token(entry.get("output_cost_per_token"))
    if input_per_million is None or output_per_million is None:
        return None
    return {
        "input_per_million": input_per_million,
        "output_per_million": output_per_million,
    }


def _proposed_from_openrouter(entry: dict[str, Any]) -> dict[str, Any] | None:
    pricing = entry.get("pricing", {})
    input_per_million = _per_million_from_per_token(pricing.get("prompt"))
    output_per_million = _per_million_from_per_token(pricing.get("completion"))
    if input_per_million is None or output_per_million is None:
        return None
    return {
        "input_per_million": input_per_million,
        "output_per_million": output_per_million,
    }


def _build_diff(
    config: dict,
    litellm_catalog: dict[str, Any],
    openrouter_models: dict[str, Any],
) -> PricingRefreshResponse:
    """Build the refresh diff for every configured pair: LiteLLM first,
    OpenRouter as a fallback for anything LiteLLM didn't cover or whose
    matched entry didn't yield a usable price. A pair covered by neither
    source goes to `not_found` instead of being guessed at.
    """
    changes: list[PricingChange] = []
    not_found: list[PricingPairNotFound] = []

    for provider, model in _configured_pairs(config):
        current = _current_price(config, provider, model)

        litellm_entry = _match_in_litellm_catalog(litellm_catalog, provider, model)
        proposed = _proposed_from_litellm(litellm_entry) if litellm_entry else None
        source = "litellm_catalog"

        if proposed is None:
            openrouter_entry = _match_in_openrouter_models(
                openrouter_models, provider, model
            )
            proposed = (
                _proposed_from_openrouter(openrouter_entry)
                if openrouter_entry
                else None
            )
            source = "openrouter"

        if proposed is None:
            not_found.append(PricingPairNotFound(provider=provider, model=model))
            continue

        changes.append(
            PricingChange(
                provider=provider,
                model=model,
                current=current,
                proposed=proposed,
                source=source,
                changed=current != proposed,
            )
        )

    return PricingRefreshResponse(changes=changes, not_found=not_found)


def _write_pricing_config(path: Path, config: dict) -> None:
    """Write `config` to `path` atomically.

    Writes to a sibling temp file first, then `os.replace`s it into place.
    `os.replace` is atomic on both POSIX and Windows (unlike `shutil.move`,
    which can do a non-atomic copy+delete across filesystems) -- this file
    is the one thing the entire pricing subsystem depends on, so a crash
    mid-write must never leave it truncated or corrupt. If the write itself
    fails partway, the temp file is removed (if it still exists) before the
    original exception is re-raised, so a failed write never leaves a stray
    `.tmp` file behind.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


@router.get("/pricing", response_model=PricingConfig)
def get_pricing(
    pricing_config_path: Path = Depends(get_pricing_config_path),
) -> dict:
    """Read the pricing config, seeding it with real Anthropic list prices
    on first access. Unlike `GET /stats`, this route is write-capable: a
    missing file isn't an error, it's "no one has configured pricing yet",
    and the honest fix is to create it with the known-correct Anthropic
    defaults rather than returning an empty/null response.

    A corrupt (invalid-JSON) file is a different case from a missing one --
    someone hand-edited the file and broke it. Rather than let FastAPI
    surface a bare, undiagnosable 500, this raises a 500 with a detail
    message naming the file and the parse error, so it's actually fixable.
    """
    if not pricing_config_path.exists():
        _write_pricing_config(pricing_config_path, SEEDED_DEFAULT_PRICING)
        return copy.deepcopy(SEEDED_DEFAULT_PRICING)
    try:
        return load_pricing_config(pricing_config_path)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Pricing config file at {pricing_config_path} is corrupt: {exc}",
        ) from exc


@router.put("/pricing", response_model=PricingConfig)
def put_pricing(
    config: PricingConfig,
    pricing_config_path: Path = Depends(get_pricing_config_path),
) -> dict:
    """Overwrite the pricing config file with a full document.

    `PricingConfig` (a Pydantic model) is the validation gate: FastAPI
    returns 422 automatically if the body isn't a JSON object, is missing
    `anthropic` or `providers`, `anthropic` isn't itself an object, or any
    of the three required Anthropic tiers is missing/malformed -- see
    `PricingConfig`'s own docstring for why that check exists.
    """
    written = config.model_dump()
    _write_pricing_config(pricing_config_path, written)
    return written


@router.post("/pricing/refresh", response_model=PricingRefreshResponse)
async def refresh_pricing(
    pricing_config_path: Path = Depends(get_pricing_config_path),
) -> PricingRefreshResponse:
    """Fetch candidate prices for every currently-configured pair and
    return a diff -- this route never writes to disk. Missing config file
    is treated the same as an empty one (no providers configured yet, only
    the three Anthropic tiers) rather than a 404/500 -- a refresh before
    the file has ever been created is a reasonable first action.

    A corrupt (invalid-JSON) file is different: that's not "nothing
    configured yet", it's a broken hand-edit, so it's reported as a
    diagnosable 500 rather than silently treated as empty or left to
    surface as an opaque unhandled exception.
    """
    try:
        config = load_pricing_config(pricing_config_path)
    except FileNotFoundError:
        config = {"anthropic": {}, "providers": {}}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Pricing config file at {pricing_config_path} is corrupt: {exc}",
        ) from exc

    litellm_catalog = await _fetch_litellm_catalog()
    openrouter_models = await _fetch_openrouter_models()

    return _build_diff(config, litellm_catalog, openrouter_models)
