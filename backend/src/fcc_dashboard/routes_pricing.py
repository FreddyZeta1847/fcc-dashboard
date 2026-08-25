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

import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dependencies import get_db, get_pricing_config_path  # noqa: F401 (get_db kept for dependency-pattern consistency)
from .pricing import load_pricing_config

router = APIRouter()

LITELLM_CATALOG_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_FETCH_TIMEOUT = 10.0

SEEDED_DEFAULT_PRICING: dict[str, Any] = {
    "anthropic": {
        "opus": {"input_per_million": 15.0, "output_per_million": 75.0},
        "sonnet": {"input_per_million": 3.0, "output_per_million": 15.0},
        "haiku": {"input_per_million": 0.25, "output_per_million": 1.25},
    },
    "providers": {},
}


class PricingConfig(BaseModel):
    """The full pricing config document -- PRICING-ENGINE's schema.

    Deliberately loose beyond the one contractual check the brief asks for
    (`anthropic` present and itself a dict): `pricing.py`'s
    `lookup_price`/`lookup_anthropic_price` already validate individual
    price entries defensively wherever they're actually used, so this
    model doesn't duplicate that. `model_config = ConfigDict(extra="allow")`
    plus a permissive `providers` type means a well-formed document round-
    trips through this model unchanged -- this route is a pass-through
    writer, not a schema owner.
    """

    model_config = ConfigDict(extra="allow")

    anthropic: dict[str, Any]
    providers: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _anthropic_is_a_dict(self) -> "PricingConfig":
        if not isinstance(self.anthropic, dict):
            raise ValueError("'anthropic' must be an object")
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
    pairs = [("anthropic", tier) for tier in ("opus", "sonnet", "haiku")]
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


@router.get("/pricing")
def get_pricing(
    pricing_config_path: Path = Depends(get_pricing_config_path),
) -> dict:
    """Read the pricing config, seeding it with real Anthropic list prices
    on first access. Unlike `GET /stats`, this route is write-capable: a
    missing file isn't an error, it's "no one has configured pricing yet",
    and the honest fix is to create it with the known-correct Anthropic
    defaults rather than returning an empty/null response.
    """
    if not pricing_config_path.exists():
        _write_pricing_config(pricing_config_path, SEEDED_DEFAULT_PRICING)
        return SEEDED_DEFAULT_PRICING
    return load_pricing_config(pricing_config_path)


@router.put("/pricing")
def put_pricing(
    config: PricingConfig,
    pricing_config_path: Path = Depends(get_pricing_config_path),
) -> dict:
    """Overwrite the pricing config file with a full document.

    `PricingConfig` (a Pydantic model) is the validation gate: FastAPI
    returns 422 automatically if the body isn't a JSON object, is missing
    `anthropic`, or `anthropic` isn't itself an object -- exactly the
    contract's "reject with 422" rule, and nothing more, per the brief
    ("don't need deep validation of every price entry's shape here").
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
    """
    try:
        config = load_pricing_config(pricing_config_path)
    except FileNotFoundError:
        config = {"anthropic": {}, "providers": {}}

    litellm_catalog = await _fetch_litellm_catalog()
    openrouter_models = await _fetch_openrouter_models()

    return _build_diff(config, litellm_catalog, openrouter_models)
