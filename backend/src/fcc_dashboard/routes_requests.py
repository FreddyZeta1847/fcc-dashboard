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
"""

import sqlite3
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .dependencies import get_db

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


@router.get("/requests", response_model=RequestsListResponse)
def list_requests(
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    status: RequestStatus | None = None,
    provider: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
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

    return RequestsListResponse(
        total=total,
        limit=limit,
        offset=offset,
        results=[dict(row) for row in rows],
    )
