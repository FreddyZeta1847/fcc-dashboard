"""
`GET /requests` -- paginated, filterable listing of ingested gateway requests.

This is the dashboard's main table view: every row the collector has
written to the `requests` table (Phase 2/Task 3), most recent first, with
optional exact-match filters on `status` and `provider` and offset-based
pagination.

Follows the same conventions `routes_status.py` established for this phase:

- `get_db` comes from `dependencies.py`, never from `api.py` (see that
  module's docstring for why -- avoids a circular import).
- The response shape is a Pydantic model (`RequestsListResponse`) passed to
  `response_model=`, not a bare dict, so FastAPI's OpenAPI schema documents
  the real shape.
- The handler is a plain `def`, not `async def`: it does no `await`ing of
  its own (pure sync SQLite work), and FastAPI runs sync handlers in a
  threadpool automatically. `init_db`'s `check_same_thread=False` + WAL
  mode already makes concurrent sync access from that threadpool safe.

Each result row is returned as a plain `dict[str, Any]` (via `dict(row)` on
the `sqlite3.Row`) rather than a fully-typed Pydantic model of every
`requests` column -- the column set already lives in `db.py`'s schema and
duplicating it here as a second Pydantic model would just be two places
that could drift out of sync. `total`/`limit`/`offset`, the fields the
frontend actually depends on for pagination math, are still fully typed.

Filtering and pagination are always done with `?` bind parameters -- never
by interpolating `limit`/`offset`/`status`/`provider` into the SQL string
-- so there is no SQL-injection surface here. `status` is additionally
closed to an `Enum` of the three known values, so FastAPI/Pydantic reject
anything else with a 422 before the query ever runs.

`actual_cost`/`equivalent_cost`/`savings` are real columns on the `requests`
table, but the collector never writes them -- they're always NULL on disk.
This route fills them in live, on every read, the same way `routes_stats.py`
computes `total_savings`: by loading the current pricing config and calling
`pricing.compute_savings` per row (via the same `is_priceable` gate
`routes_stats.py` uses). Live-computing here rather than persisting a value
at ingest time is deliberate -- a price edited in Settings should be
reflected on every row retroactively, not frozen to whatever price was
configured when the row was first collected. A row whose `gateway_model` is
a real, non-NULL, non-configured Anthropic tier still raises `ValueError`
out of `compute_savings`, same as `routes_stats.py` -- see that module's
docstring for why that's intentional.
"""

import json
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .dependencies import get_db, get_pricing_config_path
from .pricing import compute_savings, is_priceable, load_pricing_config

router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class RequestStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    error = "error"


class RequestsListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    results: list[dict[str, Any]]


def _build_filters(
    status: RequestStatus | None, provider: str | None
) -> tuple[str, list[Any]]:
    """Build a `WHERE` clause (or `""`) plus its matching bind parameters.

    Both filters are exact-match and optional; either, both, or neither may
    be present. Values are always passed as bind parameters, never
    interpolated into the SQL text.
    """
    clauses = []
    params: list[Any] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status.value)
    if provider is not None:
        clauses.append("provider = ?")
        params.append(provider)

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _priced_row(row: sqlite3.Row, pricing_config: dict) -> dict[str, Any]:
    """`dict(row)` with `actual_cost`/`equivalent_cost`/`savings` filled in
    live wherever `is_priceable` allows it -- see this module's docstring.
    Rows that aren't priceable, or are priceable but genuinely unconfigured
    (`compute_savings` returns `unknown=True`), keep the DB's NULL values.
    """
    result = dict(row)
    if not is_priceable(row):
        return result

    savings_result = compute_savings(
        pricing_config,
        provider=row["provider"],
        downstream_model=row["downstream_model"],
        gateway_model=row["gateway_model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
    )
    if savings_result.unknown:
        return result

    result["actual_cost"] = savings_result.actual_cost
    result["equivalent_cost"] = savings_result.equivalent_cost
    result["savings"] = savings_result.savings
    return result


@router.get("/requests", response_model=RequestsListResponse)
def list_requests(
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    status: RequestStatus | None = None,
    provider: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
    pricing_config_path: Path = Depends(get_pricing_config_path),
) -> RequestsListResponse:
    # Clamp rather than reject: SQLite treats a negative LIMIT as "no
    # limit" and a negative OFFSET as 0, so an out-of-range value here
    # isn't a SQL-injection risk (it's still bound as a parameter) but
    # could silently defeat the MAX_LIMIT cap or return the whole table.
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)

    where_clause, params = _build_filters(status, provider)

    total = db.execute(
        f"SELECT COUNT(*) FROM requests{where_clause}", params
    ).fetchone()[0]

    rows = db.execute(
        f"SELECT * FROM requests{where_clause} "
        "ORDER BY occurred_at DESC, rowid DESC "
        "LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()

    try:
        pricing_config = load_pricing_config(pricing_config_path)
    except (FileNotFoundError, json.JSONDecodeError):
        # Same "no usable pricing data yet" treatment as routes_stats.py:
        # every row just comes back unpriced rather than erroring a
        # read-only listing endpoint.
        pricing_config = {}

    return RequestsListResponse(
        total=total,
        limit=limit,
        offset=offset,
        results=[_priced_row(row, pricing_config) for row in rows],
    )
