"""
`GET /stats` -- aggregate request counts, token totals, and the dashboard's
core "money saved" number for a named time range.

Two genuinely different aggregation passes run over the same fetched rows:
`_aggregate_costs` (feeding `by_provider`) answers a money/savings question,
so it only ever looks at priced, `status = 'completed'` rows -- an unpriced
or pending/error row contributes nothing to it. `_aggregate_volume` (feeding
`volume_by_provider` and `volume_by_model`, added for the frontend's Usage
page) answers a usage/volume question instead: it counts every row in range
regardless of status or whether pricing exists for it. They are kept as two
separate functions on purpose -- don't merge them, and don't make one call
the other -- so a future change to one's filtering logic can't silently leak
into the other's numbers.

Follows the conventions `routes_status.py` and `routes_requests.py`
established for this phase: `get_db` (and here also
`get_pricing_config_path`) come from `dependencies.py`, never from `api.py`
(avoids a circular import -- see `dependencies.py`'s docstring); the
response shape is a Pydantic model, not a bare dict; the handler is a plain
`def` (pure sync SQLite + JSON-file work), which FastAPI runs in a
threadpool automatically.

This is the first route to wire Phase 1's `datetime_utils.resolve_range_boundaries`
and `pricing.compute_savings` into the API, and it is deliberately careful
about two rules from the plan's Global Constraints:

1. Never assume free. A row only ever contributes to `total_savings` if
   `compute_savings` actually priced it (`unknown=False`). Every other
   completed row -- missing tokens, a NULL `gateway_model` (the orphan-row
   case Phase 2 can produce), or a `(provider, downstream_model)` pair with
   no configured price -- is counted in `unpriced_request_count` instead,
   never silently folded into the sum as if its savings were $0.

2. Never crash on missing data. A NULL `gateway_model` is caught by this
   module *before* calling `compute_savings` (which requires a non-Optional
   `str` and isn't designed to receive `None`) and treated as unpriced. This
   is deliberately different from the case `compute_savings` itself is
   designed to raise `ValueError` for: a real, non-NULL `gateway_model`
   value that isn't one of the configured Anthropic tiers. That's a genuine
   pricing-config gap (every FCC-supported tier is supposed to be priced),
   not "we don't know this row's tier at all" -- so it's allowed to
   propagate as a 500 rather than being swallowed like the orphan-row case.

Similarly, a pricing config file that doesn't exist yet at
`get_pricing_config_path()` is treated as "we have never priced anything,
ever": `total_savings` comes back `null` (not `0.0`), which is a materially
different fact from "we priced everything and it genuinely summed to zero".
This route never creates the pricing file -- it's read-only; Task 4's
`PUT /pricing` owns writing it.
"""

import json
import sqlite3
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .datetime_utils import resolve_range_boundaries
from .dependencies import get_db, get_pricing_config_path
from .pricing import compute_savings, load_pricing_config

router = APIRouter()


class RangeName(str, Enum):
    today = "today"
    last_7_days = "last_7_days"
    last_30_days = "last_30_days"
    all_time = "all_time"


class ByProviderStats(BaseModel):
    provider: str
    request_count: int
    savings: float


class ByProviderVolume(BaseModel):
    provider: str
    request_count: int
    input_tokens: int
    output_tokens: int
    estimated_count: int


class ByModelVolume(BaseModel):
    provider: str
    model: str
    request_count: int
    input_tokens: int
    output_tokens: int
    estimated_count: int


class StatsResponse(BaseModel):
    range: str
    range_start: str
    range_end: str
    total_requests: int
    completed_requests: int
    error_requests: int
    pending_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_savings: float | None
    unpriced_request_count: int
    by_provider: list[ByProviderStats]
    volume_by_provider: list[ByProviderVolume]
    volume_by_model: list[ByModelVolume]


def _fetch_rows_in_range(
    db: sqlite3.Connection, start: str, end: str
) -> list[sqlite3.Row]:
    """All `requests` rows with `occurred_at` in `[start, end]` (inclusive
    both ends, per DATE-TIME's documented convention -- `resolve_range_boundaries`
    already returns boundaries meant to be used this way).
    """
    return db.execute(
        "SELECT * FROM requests WHERE occurred_at BETWEEN ? AND ?",
        (start, end),
    ).fetchall()


def _is_priceable(row: sqlite3.Row) -> bool:
    """Whether a row carries everything `compute_savings` needs.

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


def _aggregate_costs(
    rows: list[sqlite3.Row], pricing_config: dict
) -> tuple[float, int, list[ByProviderStats]]:
    """Sum savings and tally unpriced rows across `rows`, given a loaded
    pricing config.

    Returns `(total_savings, unpriced_request_count, by_provider)`.
    `total_savings` only ever accumulates rows `compute_savings` actually
    priced (`unknown=False`); everything else -- unpriceable per
    `_is_priceable`, or priceable but genuinely unconfigured
    (`unknown=True`) -- increments `unpriced_request_count` instead.

    A row whose `gateway_model` is a real, non-NULL, non-configured
    Anthropic tier makes `compute_savings` raise `ValueError`. That's
    deliberately not caught here: it's a genuine pricing-config gap (every
    FCC-supported tier is supposed to be priced), distinct from the
    "we don't know this row's tier at all" case `_is_priceable` already
    screens out, and the plan's rules call for that distinction to surface
    loudly rather than being swallowed alongside orphan rows.
    """
    total_savings = 0.0
    unpriced_request_count = 0
    by_provider: dict[str, dict[str, float | int]] = {}

    for row in rows:
        if row["status"] != "completed":
            continue
        if not _is_priceable(row):
            unpriced_request_count += 1
            continue

        result = compute_savings(
            pricing_config,
            provider=row["provider"],
            downstream_model=row["downstream_model"],
            gateway_model=row["gateway_model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
        )
        if result.unknown:
            unpriced_request_count += 1
            continue

        total_savings += result.savings
        bucket = by_provider.setdefault(
            row["provider"], {"request_count": 0, "savings": 0.0}
        )
        bucket["request_count"] += 1
        bucket["savings"] += result.savings

    by_provider_list = [
        ByProviderStats(
            provider=provider,
            request_count=int(stats["request_count"]),
            savings=float(stats["savings"]),
        )
        for provider, stats in sorted(by_provider.items())
    ]
    return total_savings, unpriced_request_count, by_provider_list


def _aggregate_volume(
    rows: list[sqlite3.Row],
) -> tuple[list[ByProviderVolume], list[ByModelVolume]]:
    """Count ALL rows in range by provider and by (provider, model), regardless
    of `status` or pricing.

    This is the usage/volume answer, deliberately distinct from
    `_aggregate_costs`' by_provider (the money/savings answer): a row with an
    unpriced downstream model, or a pending/error status, still counts here.
    A row is only dropped from a breakdown when the column that breakdown
    groups by is itself NULL (no `provider` -> excluded from both; a real
    `provider` but NULL `downstream_model` -> counted in the provider
    breakdown only, not the model one).
    """
    by_provider: dict[str, dict[str, int]] = {}
    by_model: dict[tuple[str, str], dict[str, int]] = {}

    for row in rows:
        provider = row["provider"]
        downstream_model = row["downstream_model"]
        input_tokens = row["input_tokens"]
        output_tokens = row["output_tokens"]
        is_estimated = bool(row["occurred_at_is_estimated"])

        if provider is not None:
            bucket = by_provider.setdefault(
                provider,
                {"request_count": 0, "input_tokens": 0, "output_tokens": 0, "estimated_count": 0},
            )
            bucket["request_count"] += 1
            if input_tokens is not None:
                bucket["input_tokens"] += input_tokens
            if output_tokens is not None:
                bucket["output_tokens"] += output_tokens
            if is_estimated:
                bucket["estimated_count"] += 1

        if provider is not None and downstream_model is not None:
            model_bucket = by_model.setdefault(
                (provider, downstream_model),
                {"request_count": 0, "input_tokens": 0, "output_tokens": 0, "estimated_count": 0},
            )
            model_bucket["request_count"] += 1
            if input_tokens is not None:
                model_bucket["input_tokens"] += input_tokens
            if output_tokens is not None:
                model_bucket["output_tokens"] += output_tokens
            if is_estimated:
                model_bucket["estimated_count"] += 1

    volume_by_provider = [
        ByProviderVolume(
            provider=provider,
            request_count=stats["request_count"],
            input_tokens=stats["input_tokens"],
            output_tokens=stats["output_tokens"],
            estimated_count=stats["estimated_count"],
        )
        for provider, stats in sorted(by_provider.items())
    ]
    volume_by_model = [
        ByModelVolume(
            provider=provider,
            model=model,
            request_count=stats["request_count"],
            input_tokens=stats["input_tokens"],
            output_tokens=stats["output_tokens"],
            estimated_count=stats["estimated_count"],
        )
        for (provider, model), stats in sorted(by_model.items())
    ]
    return volume_by_provider, volume_by_model


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    range_name: RangeName = Query(RangeName.last_7_days, alias="range"),
    db: sqlite3.Connection = Depends(get_db),
    pricing_config_path: Path = Depends(get_pricing_config_path),
) -> StatsResponse:
    start, end = resolve_range_boundaries(range_name.value)
    rows = _fetch_rows_in_range(db, start, end)

    completed_requests = sum(1 for row in rows if row["status"] == "completed")
    error_requests = sum(1 for row in rows if row["status"] == "error")
    pending_requests = sum(1 for row in rows if row["status"] == "pending")
    total_input_tokens = sum(
        row["input_tokens"] for row in rows if row["input_tokens"] is not None
    )
    total_output_tokens = sum(
        row["output_tokens"] for row in rows if row["output_tokens"] is not None
    )
    volume_by_provider, volume_by_model = _aggregate_volume(rows)

    try:
        pricing_config = load_pricing_config(pricing_config_path)
    except (FileNotFoundError, json.JSONDecodeError):
        # No pricing config has ever been written, or the file that exists
        # is corrupt (invalid JSON, e.g. a broken hand-edit). Both cases
        # are functionally the same for this read-only endpoint: "we have
        # no usable pricing data" -- a null total_savings, not a 0.0 one --
        # and every completed row is unpriced by definition. This endpoint
        # is read-only: it never creates or repairs the pricing file itself.
        return StatsResponse(
            range=range_name.value,
            range_start=start,
            range_end=end,
            total_requests=len(rows),
            completed_requests=completed_requests,
            error_requests=error_requests,
            pending_requests=pending_requests,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_savings=None,
            unpriced_request_count=completed_requests,
            by_provider=[],
            volume_by_provider=volume_by_provider,
            volume_by_model=volume_by_model,
        )

    total_savings, unpriced_request_count, by_provider = _aggregate_costs(
        rows, pricing_config
    )

    return StatsResponse(
        range=range_name.value,
        range_start=start,
        range_end=end,
        total_requests=len(rows),
        completed_requests=completed_requests,
        error_requests=error_requests,
        pending_requests=pending_requests,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_savings=total_savings,
        unpriced_request_count=unpriced_request_count,
        by_provider=by_provider,
        volume_by_provider=volume_by_provider,
        volume_by_model=volume_by_model,
    )
