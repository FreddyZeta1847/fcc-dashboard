# Phase 1 — Core Utilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build DATE-TIME and PRICING-ENGINE as pure Python modules with unit tests — no FastAPI, no SQLite, no collector. Every downstream layer (collector, API, frontend) depends on these for correct timestamps and correct money math.

**Architecture:** Two independent modules in the `fcc_dashboard` package: `datetime_utils.py` (timestamp parsing/normalization/range-boundary resolution) and `pricing.py` (pricing config loading, price lookup, savings formula). Both are pure functions operating on plain values (strings, dicts, datetimes) — no I/O beyond `pricing.load_pricing_config`'s file read, no framework dependency, fully testable in isolation.

**Tech Stack:** Python stdlib — `datetime`, `zoneinfo`, `json`, `pathlib`, `dataclasses` — plus two small runtime dependencies added mid-phase to make `zoneinfo` actually DST-correct in production: `tzdata` (Windows has no built-in IANA timezone database) and `tzlocal` (resolves the host's IANA zone *name*, which `zoneinfo` needs for correct historical-date arithmetic — the stdlib alone only exposes the *current* UTC offset). See the final whole-branch review's Critical finding and DATE-TIME--technologies.md for why this matters.

**Spec:** `vault-fcc-dashboard/plans/PHASE-1-CORE-UTILITIES.md` (scope), `vault-fcc-dashboard/features/DATE-TIME/DATE-TIME--architecture.md` + `--technologies.md` + `--resilience.md`, `vault-fcc-dashboard/features/PRICING-ENGINE/PRICING-ENGINE--architecture.md` + `--technologies.md` + `--resilience.md` (all locked decisions this plan implements).

## Global Constraints

- Storage timestamp format: ISO-8601 text, UTC, millisecond precision, `Z` suffix — e.g. `2026-08-24T14:30:00.123Z`. Every stored/formatted timestamp in this codebase uses this exact format (per DATE-TIME--technologies, referenced by PRICING-ENGINE's `last_updated` field too).
- DATE-TIME's parsing function must fail loudly (raise) on a malformed timestamp — never silently misinterpret or default to "now" itself. (The "keep the row with a fallback + flag" policy is the *caller's* responsibility, in Phase 2's collector — not this module's job. This module's contract is: parse correctly, or raise clearly.)
- No timezone parameter exposed to production callers for range-boundary resolution — the backend always reads the host machine's local timezone (per DATE-TIME--architecture). Test-only override parameters are fine (never wired to any API surface).
- PRICING-ENGINE: unknown (provider, model) pairs are never assumed free — must be distinguishable from a genuinely-configured $0 price.
- Ranges supported by `resolve_range_boundaries` in this phase: `"today"`, `"last_7_days"`, `"last_30_days"`, `"all_time"`. (Not specified at this exact granularity in the vault — this is a Phase 1 implementation ruling, documented here; extensible later without breaking the function's contract.)

---

### Task 1: DATE-TIME — timestamp parsing and UTC normalization

**Files:**
- Create: `backend/src/fcc_dashboard/datetime_utils.py`
- Test: `backend/tests/test_datetime_utils.py`

**Interfaces:**
- Consumes: nothing (first task, stdlib only).
- Produces: `parse_fcc_timestamp(raw: str) -> datetime`, `to_utc_iso8601(dt: datetime) -> str`, `now_utc_iso8601() -> str`. These three are consumed by Task 2 (not directly) and by Phase 2's collector later.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_datetime_utils.py`:
```python
"""Unit tests for backend.fcc_dashboard.datetime_utils."""

from datetime import datetime, timezone

import pytest

from fcc_dashboard.datetime_utils import (
    now_utc_iso8601,
    parse_fcc_timestamp,
    to_utc_iso8601,
)


def test_parse_fcc_timestamp_with_offset():
    dt = parse_fcc_timestamp("2026-07-16 13:55:49.563956+02:00")
    assert dt.year == 2026
    assert dt.month == 7
    assert dt.day == 16
    assert dt.hour == 13
    assert dt.minute == 55
    assert dt.second == 49
    assert dt.utcoffset().total_seconds() == 2 * 3600


def test_parse_fcc_timestamp_rejects_malformed_input():
    with pytest.raises(ValueError):
        parse_fcc_timestamp("not a timestamp")


def test_parse_fcc_timestamp_rejects_empty_string():
    with pytest.raises(ValueError):
        parse_fcc_timestamp("")


def test_to_utc_iso8601_converts_offset_to_utc_with_z_suffix():
    dt = datetime(2026, 7, 16, 13, 55, 49, 563000, tzinfo=timezone.utc)
    # 13:55:49 UTC+2 == 11:55:49 UTC
    from datetime import timedelta

    dt_plus_2 = dt.replace(tzinfo=timezone(timedelta(hours=2)))
    result = to_utc_iso8601(dt_plus_2)
    assert result == "2026-07-16T11:55:49.563Z"


def test_to_utc_iso8601_rejects_naive_datetime():
    naive = datetime(2026, 7, 16, 13, 55, 49)
    with pytest.raises(ValueError):
        to_utc_iso8601(naive)


def test_now_utc_iso8601_format():
    result = now_utc_iso8601()
    # Format check: YYYY-MM-DDTHH:MM:SS.mmmZ (24 chars exactly)
    assert len(result) == 24
    assert result[10] == "T"
    assert result.endswith("Z")
    # Round-trips through parse_fcc_timestamp without raising
    parsed = parse_fcc_timestamp(result.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_datetime_utils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fcc_dashboard.datetime_utils'`

- [ ] **Step 3: Write the implementation**

`backend/src/fcc_dashboard/datetime_utils.py`:
```python
"""
Timestamp parsing and UTC normalization for FCC Dashboard.

FCC writes log timestamps as ISO-8601 with a UTC offset (e.g.
"2026-07-16 13:55:49.563956+02:00"). This module parses that format,
normalizes any aware datetime to this project's canonical storage format
(UTC, millisecond precision, "Z" suffix — e.g. "2026-08-24T14:30:00.123Z"),
and provides the current instant in that same format.

Parsing fails loudly (raises ValueError) on malformed input — it never
guesses or silently substitutes the current time. Callers that need a
fallback-on-failure policy (e.g. the log collector, Phase 2) implement
that themselves by catching the exception; this module's contract stops
at "parse correctly, or raise clearly."
"""

from datetime import datetime, timezone


def parse_fcc_timestamp(raw: str) -> datetime:
    """Parse FCC's log timestamp format into an aware datetime.

    Raises ValueError if `raw` is not a valid ISO-8601 timestamp.
    """
    return datetime.fromisoformat(raw)


def to_utc_iso8601(dt: datetime) -> str:
    """Normalize an aware datetime to this project's canonical UTC storage format.

    Format: "YYYY-MM-DDTHH:MM:SS.mmmZ" (millisecond precision, "Z" suffix).
    Raises ValueError if `dt` is naive (no timezone info) — every timestamp
    this module handles must already be aware.
    """
    if dt.tzinfo is None:
        raise ValueError("to_utc_iso8601 requires an aware datetime")
    utc_dt = dt.astimezone(timezone.utc)
    millis = utc_dt.microsecond // 1000
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{millis:03d}Z"


def now_utc_iso8601() -> str:
    """Current instant, UTC, in this project's canonical storage format.

    Used for `ingested_at` and as the fallback `occurred_at` value when a
    log line's own timestamp can't be parsed (the collector's policy,
    Phase 2 — this function just supplies "now" in the right format).
    """
    return to_utc_iso8601(datetime.now(timezone.utc))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_datetime_utils.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/datetime_utils.py backend/tests/test_datetime_utils.py
git commit -m "feat(backend): add DATE-TIME timestamp parsing and UTC normalization"
```

---

### Task 2: DATE-TIME — local-timezone range boundary resolution

**Files:**
- Modify: `backend/src/fcc_dashboard/datetime_utils.py` (add `resolve_range_boundaries`)
- Modify: `backend/tests/test_datetime_utils.py` (add tests)

**Interfaces:**
- Consumes: `to_utc_iso8601` from Task 1 (same file).
- Produces: `resolve_range_boundaries(range_name: str, *, local_tz: str | None = None, now: datetime | None = None) -> tuple[str, str]` — returns `(start_utc_iso8601, end_utc_iso8601)`. Consumed later by Phase 3's `/stats` API endpoint. `local_tz` and `now` are test-only overrides (never wired to any production/API caller — production always uses the real host timezone and the real current time).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_datetime_utils.py`:
```python
from zoneinfo import ZoneInfo

from fcc_dashboard.datetime_utils import resolve_range_boundaries


def test_resolve_range_boundaries_today():
    # Fixed "now": 2026-08-24 15:30:00 in Europe/Rome (UTC+2 in August, DST)
    fixed_now = datetime(2026, 8, 24, 15, 30, 0, tzinfo=ZoneInfo("Europe/Rome"))
    start, end = resolve_range_boundaries("today", local_tz="Europe/Rome", now=fixed_now)
    # Local midnight 2026-08-24 00:00:00+02:00 -> UTC 2026-08-23T22:00:00.000Z
    assert start == "2026-08-23T22:00:00.000Z"
    # End is "now" itself, normalized to UTC
    assert end == "2026-08-24T13:30:00.000Z"


def test_resolve_range_boundaries_last_7_days():
    fixed_now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=ZoneInfo("Europe/Rome"))
    start, end = resolve_range_boundaries("last_7_days", local_tz="Europe/Rome", now=fixed_now)
    # 7 days back from local midnight of "today"
    assert start == "2026-08-16T22:00:00.000Z"
    assert end == "2026-08-24T10:00:00.000Z"


def test_resolve_range_boundaries_last_30_days():
    fixed_now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=ZoneInfo("Europe/Rome"))
    start, end = resolve_range_boundaries("last_30_days", local_tz="Europe/Rome", now=fixed_now)
    assert start == "2026-07-25T22:00:00.000Z"
    assert end == "2026-08-24T10:00:00.000Z"


def test_resolve_range_boundaries_all_time():
    fixed_now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=ZoneInfo("Europe/Rome"))
    start, end = resolve_range_boundaries("all_time", local_tz="Europe/Rome", now=fixed_now)
    # "all_time" start is a fixed epoch far in the past (project inception),
    # not computed relative to now.
    assert start == "1970-01-01T00:00:00.000Z"
    assert end == "2026-08-24T10:00:00.000Z"


def test_resolve_range_boundaries_rejects_unknown_range():
    with pytest.raises(ValueError):
        resolve_range_boundaries("last_fortnight")


def test_resolve_range_boundaries_uses_real_local_time_by_default():
    # No overrides: must not raise, must return two valid ISO-8601 UTC strings
    # where start <= end.
    start, end = resolve_range_boundaries("today")
    assert start <= end
    assert start.endswith("Z")
    assert end.endswith("Z")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_datetime_utils.py -v -k resolve_range`
Expected: FAIL with `ImportError: cannot import name 'resolve_range_boundaries'`

- [ ] **Step 3: Write the implementation**

Add to `backend/src/fcc_dashboard/datetime_utils.py` (after the existing imports, change the import line, and append the new function):
```python
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
```
(replace the existing `from datetime import datetime, timezone` line with the one above, and add the `zoneinfo` import)

```python
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def resolve_range_boundaries(
    range_name: str,
    *,
    local_tz: str | None = None,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Resolve a named range into (start, end) UTC ISO-8601 boundaries.

    Boundaries are computed in the host machine's local timezone (DST-correct,
    via zoneinfo) so "today"/"last_7_days"/etc. mean what a human on this
    machine expects "today" to mean — then converted to UTC for querying.

    Supported range_name values: "today", "last_7_days", "last_30_days",
    "all_time".

    `local_tz` and `now` exist for deterministic testing only. Production
    callers must never pass them — the backend always uses the real host
    timezone and the real current time (per DATE-TIME--architecture: no
    timezone parameter is ever exposed to the frontend or API).

    Raises ValueError for an unrecognized range_name.
    """
    tz = ZoneInfo(local_tz) if local_tz is not None else datetime.now().astimezone().tzinfo
    current = now if now is not None else datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)

    local_midnight_today = current.astimezone(tz).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    if range_name == "today":
        start_local = local_midnight_today
    elif range_name == "last_7_days":
        start_local = local_midnight_today - timedelta(days=7)
    elif range_name == "last_30_days":
        start_local = local_midnight_today - timedelta(days=30)
    elif range_name == "all_time":
        return (to_utc_iso8601(_EPOCH), to_utc_iso8601(current))
    else:
        raise ValueError(f"unrecognized range_name: {range_name!r}")

    return (to_utc_iso8601(start_local), to_utc_iso8601(current))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_datetime_utils.py -v`
Expected: 12 passed (6 from Task 1 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/datetime_utils.py backend/tests/test_datetime_utils.py
git commit -m "feat(backend): add DATE-TIME local-timezone range boundary resolution"
```

---

### Task 3: PRICING-ENGINE — config loading and price lookup

**Files:**
- Create: `backend/src/fcc_dashboard/pricing.py`
- Test: `backend/tests/test_pricing.py`

**Interfaces:**
- Consumes: nothing (stdlib `json`/`pathlib` only).
- Produces: `load_pricing_config(path: Path) -> dict`, `lookup_price(config: dict, provider: str, model: str) -> dict | None`, `lookup_anthropic_price(config: dict, tier: str) -> dict | None`, `compute_cost(price: dict, input_tokens: int, output_tokens: int) -> float`. Consumed by Task 4 (same module) and Phase 3's API later.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_pricing.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_pricing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fcc_dashboard.pricing'`

- [ ] **Step 3: Write the implementation**

`backend/src/fcc_dashboard/pricing.py`:
```python
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
```

Note: the test file calls `compute_cost(price, input_tokens=..., output_tokens=...)` with keyword arguments — match that signature exactly (keyword-only `input_tokens`/`output_tokens` after `price`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_pricing.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/pricing.py backend/tests/test_pricing.py
git commit -m "feat(backend): add PRICING-ENGINE config loading and price lookup"
```

---

### Task 4: PRICING-ENGINE — savings formula

**Files:**
- Modify: `backend/src/fcc_dashboard/pricing.py` (add `SavingsResult`, `compute_savings`)
- Modify: `backend/tests/test_pricing.py` (add tests)

**Interfaces:**
- Consumes: `lookup_price`, `lookup_anthropic_price`, `compute_cost` from Task 3 (same file).
- Produces: `SavingsResult` (frozen dataclass: `actual_cost: float | None`, `equivalent_cost: float | None`, `savings: float | None`, `unknown: bool`), `compute_savings(config, *, provider, downstream_model, gateway_model, input_tokens, output_tokens) -> SavingsResult`. Consumed by Phase 3's API (`/stats`, `/requests` cost fields) and Phase 2's collector (per-row cost computation).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_pricing.py`:
```python
from fcc_dashboard.pricing import SavingsResult, compute_savings


def test_compute_savings_known_pair():
    result = compute_savings(
        SAMPLE_CONFIG,
        provider="openrouter",
        downstream_model="glm-4",
        gateway_model="sonnet",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    # actual: openrouter glm-4 = $0.5 + $1.5 = $2.0
    # equivalent: anthropic sonnet = $3.0 + $15.0 = $18.0
    assert result == SavingsResult(
        actual_cost=2.0, equivalent_cost=18.0, savings=16.0, unknown=False
    )


def test_compute_savings_free_provider_is_not_unknown():
    # A genuinely-configured $0 price is NOT the same as "unknown" — this is
    # the core distinction PRICING-ENGINE--architecture requires.
    result = compute_savings(
        SAMPLE_CONFIG,
        provider="nvidia_nim",
        downstream_model="glm-4",
        gateway_model="sonnet",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert result.unknown is False
    assert result.actual_cost == 0.0
    assert result.equivalent_cost == 18.0
    assert result.savings == 18.0


def test_compute_savings_unknown_pair_never_assumed_free():
    result = compute_savings(
        SAMPLE_CONFIG,
        provider="some_new_provider",
        downstream_model="some_new_model",
        gateway_model="sonnet",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert result.unknown is True
    assert result.actual_cost is None
    assert result.equivalent_cost is None
    assert result.savings is None


def test_compute_savings_raises_on_unconfigured_gateway_tier():
    with pytest.raises(ValueError):
        compute_savings(
            SAMPLE_CONFIG,
            provider="nvidia_nim",
            downstream_model="glm-4",
            gateway_model="nonexistent_tier",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_pricing.py -v -k compute_savings`
Expected: FAIL with `ImportError: cannot import name 'SavingsResult'`

- [ ] **Step 3: Write the implementation**

Add to `backend/src/fcc_dashboard/pricing.py` (add the `dataclasses` import at the top alongside the existing imports, then append at the end of the file):
```python
from dataclasses import dataclass
```

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_pricing.py -v`
Expected: 13 passed (9 from Task 3 + 4 new).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && uv run pytest -v`
Expected: 26 passed (1 placeholder + 12 datetime_utils + 13 pricing), output pristine (no warnings).

- [ ] **Step 6: Commit**

```bash
git add backend/src/fcc_dashboard/pricing.py backend/tests/test_pricing.py
git commit -m "feat(backend): add PRICING-ENGINE savings formula"
```

## Self-Review Notes

- Spec coverage: PHASE-1-CORE-UTILITIES.md's two bullets (DATE-TIME functions, PRICING-ENGINE functions) are each covered by two tasks; "Verifiable" (unit tests pass in isolation, no DB/server/network) is satisfied — every test in this plan uses only stdlib, `tmp_path`, and in-memory dicts.
- No placeholders: every step has real, complete code — no "TBD"/"add appropriate X".
- Type consistency: `compute_cost`'s keyword-only signature (`input_tokens`, `output_tokens`) is used identically in Task 3's tests, Task 4's tests, and Task 4's `compute_savings` implementation. `SavingsResult` field names (`actual_cost`, `equivalent_cost`, `savings`, `unknown`) match between its definition and every test that constructs/compares it.
- Range names ("today", "last_7_days", "last_30_days", "all_time") are a Phase 1 ruling (not specified at this granularity in the vault) — documented in Global Constraints, easy to extend later without breaking the function's contract (unrecognized names raise ValueError, so adding a new one is additive).
