"""
Pricing config loading, price lookup, and cost math for FCC Dashboard.

Pricing is keyed by (provider, model) pair, not model alone — the same
model can be free via one provider and paid via another (e.g. GLM 5.2 free
on NVIDIA NIM, paid via OpenRouter). The config is a plain JSON file, human-
editable, matching this schema:

{
  "anthropic": {"claude-opus-5": {input_per_million, output_per_million}, ...},
  "providers": {"<provider>": {"<model>": {input_per_million, output_per_million,
                                            currency, last_updated, source}}}
}

A (provider, model) pair missing from "providers" is genuinely unknown —
distinct from a pair that's present with a price of 0.0 (a real free tier).
Lookup functions return None for "not found"; they never guess or
substitute a default price.
"""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


def is_priceable(row: sqlite3.Row) -> bool:
    """Whether a `requests` row carries everything `compute_savings` needs.

    Only `status = 'completed'` rows are ever candidates for cost math
    (pending/error rows count toward request totals but never toward cost).
    Beyond that, `compute_savings` takes non-Optional `provider`,
    `downstream_model`, `gateway_model`, `input_tokens`, `output_tokens`
    arguments -- it isn't designed to receive `None` for any of them, so
    this check runs *before* calling it, not inside a try/except around it.
    A NULL `gateway_model` is exactly the Phase 2 orphan-row case (an
    ingest that never resolved a gateway tier); NULL `provider` or
    `downstream_model` are the same kind of "we don't know this row's
    pricing identity" situation. All of these are "unpriced", never "free".

    Shared between `routes_stats.py` (aggregate savings) and
    `routes_requests.py` (per-row savings on the raw listing) -- both need
    the exact same "can this row be priced at all" answer.
    """
    return row["status"] == "completed" and all(
        row[col] is not None
        for col in (
            "input_tokens",
            "output_tokens",
            "gateway_model",
            "downstream_model",
            "provider",
        )
    )


def load_pricing_config(path: Path) -> dict:
    """Load and parse the pricing config JSON file at `path`."""
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_price_entry(entry: dict, *, context: str) -> dict:
    """Confirm a pricing config entry has numeric input/output rates.

    Raises ValueError naming the offending entry if a rate key is missing
    or non-numeric — this turns a malformed config edit (or a future
    `PUT /pricing` write) into a clear error instead of an opaque KeyError
    surfacing later inside `compute_cost`.
    """
    for key in ("input_per_million", "output_per_million"):
        if key not in entry:
            raise ValueError(f"pricing entry for {context} is missing {key!r}")
        if not isinstance(entry[key], (int, float)):
            raise ValueError(f"pricing entry for {context} has non-numeric {key!r}: {entry[key]!r}")
    return entry


def lookup_price(config: dict, provider: str, model: str) -> dict | None:
    """Look up the price entry for a (provider, model) pair.

    Returns None if the pair isn't in the config — this is a genuinely
    different case from a configured price of 0.0 (a real free tier), and
    callers must not conflate the two.

    Raises ValueError if the entry is found but malformed (missing or
    non-numeric rate keys).
    """
    entry = config.get("providers", {}).get(provider, {}).get(model)
    if entry is None:
        return None
    return _validate_price_entry(entry, context=f"({provider!r}, {model!r})")


def lookup_anthropic_price(config: dict, tier: str) -> dict | None:
    """Look up the Anthropic price for a gateway tier.

    `tier` is the full gateway model id as it appears in the log's
    `gateway_model` field -- `claude-opus-5`, `claude-haiku-4-5-20251001`, and
    so on. The authoritative list is `routes_pricing.REQUIRED_ANTHROPIC_TIERS`;
    do not hardcode a short-name list against it. Doing exactly that is what
    silently broke the price-refresh write path once the tiers were renamed
    from `opus`/`sonnet`/`haiku` to their full ids.

    Returns None if the tier isn't configured.

    Raises ValueError if the entry is found but malformed (missing or
    non-numeric rate keys).
    """
    entry = config.get("anthropic", {}).get(tier)
    if entry is None:
        return None
    return _validate_price_entry(entry, context=f"anthropic tier {tier!r}")


def compute_cost(price: dict, *, input_tokens: int, output_tokens: int) -> float:
    """Compute cost in the price's currency: tokens/1,000,000 * price-per-million,
    summed for input and output tokens.
    """
    return (input_tokens / 1_000_000) * price["input_per_million"] + (
        output_tokens / 1_000_000
    ) * price["output_per_million"]


@dataclass(frozen=True)
class SavingsResult:
    """Result of the per-request savings calculation.

    `unknown=True` means the (provider, downstream_model) pair has no
    configured price — actual_cost/equivalent_cost/savings are all None in
    that case, never substituted with 0. A genuinely-configured $0 price
    (a real free tier) is `unknown=False` with `actual_cost=0.0`.
    """

    actual_cost: float | None
    equivalent_cost: float | None
    savings: float | None
    unknown: bool


def compute_savings(
    config: dict,
    *,
    provider: str,
    downstream_model: str,
    gateway_model: str,
    input_tokens: int,
    output_tokens: int,
) -> SavingsResult:
    """Compute the savings formula for one request.

    actual_cost = tokens x price of the real (provider, downstream_model) pair FCC routed to.
    equivalent_cost = same tokens x Anthropic price of the gateway_model tier FCC intercepted.
    savings = equivalent_cost - actual_cost.

    Returns a SavingsResult with unknown=True (all costs None) if the actual
    provider/model pair isn't configured — never assumed free.

    Raises ValueError if `gateway_model` isn't a configured Anthropic tier —
    that's a real configuration error (every FCC-supported tier must be
    priced), not a "some provider is missing" case.
    """
    actual_price = lookup_price(config, provider, downstream_model)
    if actual_price is None:
        return SavingsResult(
            actual_cost=None, equivalent_cost=None, savings=None, unknown=True
        )

    anthropic_price = lookup_anthropic_price(config, gateway_model)
    if anthropic_price is None:
        raise ValueError(f"no Anthropic price configured for tier {gateway_model!r}")

    actual_cost = compute_cost(
        actual_price, input_tokens=input_tokens, output_tokens=output_tokens
    )
    equivalent_cost = compute_cost(
        anthropic_price, input_tokens=input_tokens, output_tokens=output_tokens
    )
    return SavingsResult(
        actual_cost=actual_cost,
        equivalent_cost=equivalent_cost,
        savings=equivalent_cost - actual_cost,
        unknown=False,
    )
