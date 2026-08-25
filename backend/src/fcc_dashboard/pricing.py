"""
Pricing config loading, price lookup, and cost math for FCC Dashboard.

Pricing is keyed by (provider, model) pair, not model alone — the same
model can be free via one provider and paid via another (e.g. GLM 5.2 free
on NVIDIA NIM, paid via OpenRouter). The config is a plain JSON file, human-
editable, matching this schema:

{
  "anthropic": {"opus": {input_per_million, output_per_million}, "sonnet": {...}, "haiku": {...}},
  "providers": {"<provider>": {"<model>": {input_per_million, output_per_million,
                                            currency, last_updated, source}}}
}

A (provider, model) pair missing from "providers" is genuinely unknown —
distinct from a pair that's present with a price of 0.0 (a real free tier).
Lookup functions return None for "not found"; they never guess or
substitute a default price.
"""

import json
from pathlib import Path


def load_pricing_config(path: Path) -> dict:
    """Load and parse the pricing config JSON file at `path`."""
    return json.loads(path.read_text(encoding="utf-8"))


def lookup_price(config: dict, provider: str, model: str) -> dict | None:
    """Look up the price entry for a (provider, model) pair.

    Returns None if the pair isn't in the config — this is a genuinely
    different case from a configured price of 0.0 (a real free tier), and
    callers must not conflate the two.
    """
    return config.get("providers", {}).get(provider, {}).get(model)


def lookup_anthropic_price(config: dict, tier: str) -> dict | None:
    """Look up the Anthropic price for a gateway tier ('opus'/'sonnet'/'haiku').

    Returns None if the tier isn't configured.
    """
    return config.get("anthropic", {}).get(tier)


def compute_cost(price: dict, *, input_tokens: int, output_tokens: int) -> float:
    """Compute cost in the price's currency: tokens/1,000,000 * price-per-million,
    summed for input and output tokens.
    """
    return (input_tokens / 1_000_000) * price["input_per_million"] + (
        output_tokens / 1_000_000
    ) * price["output_per_million"]
