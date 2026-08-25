"""
`GET /db/tables` and `GET /db/tables/{name}` -- raw table browser for debugging.

This is a debug/admin surface, not a semantic API: it lets a developer poke
at whatever tables actually exist in the SQLite database (`requests`,
`collector_state`, and any future table `db.py`'s schema adds) without
writing a new endpoint for each one. Two endpoints:

- `GET /db/tables` lists the real table names, read live from SQLite's own
  `sqlite_master` catalog rather than a hardcoded list -- so this stays
  correct if the schema grows -- filtering out SQLite's own internal
  `sqlite_%` tables.
- `GET /db/tables/{name}` returns a paginated raw row dump of one table:
  rows as plain arrays (not objects) in `columns`' order, since this is a
  debug view of the table's actual physical shape, not a curated response
  model.

Security-critical part: `{name}` is a free-text path parameter and SQLite
cannot bind table/column names with `?` placeholders (`?` only works for
*values*). Interpolating `name` straight into a query string would be a
classic SQL-injection hole. The fix used here, `_validate_table_name`: look
up the real table list from `sqlite_master` first (the same query
`list_tables` uses), and only proceed if `name` is an *exact* match against
that known-safe set. An unknown name -- including one that looks like an
injection attempt, e.g. `requests; DROP TABLE requests;--` -- never reaches
the row query at all; it's rejected as 404 before any SQL referencing it is
built. `LIMIT`/`OFFSET` are still ordinary values, so those keep using `?`
bind parameters same as `routes_requests.py`.

Follows the same conventions as `routes_requests.py`: `get_db` from
`dependencies.py`, a Pydantic `response_model`, plain `def` handlers (no
`await`ing, sync SQLite work runs fine in FastAPI's threadpool).

One deliberate exception to "pure raw dump": for the `requests` table only,
`actual_cost`/`equivalent_cost`/`savings` are overlaid with the same
live-computed values `routes_requests.py` returns (via the shared
`pricing.is_priceable`/`pricing.compute_savings`), instead of the columns'
real on-disk NULLs -- so this page and the Overview page's Recent Requests
feed always agree on the same number for the same request. Every other
table (`collector_state`, `process_state`, and any future table) still goes
through the fully generic path with no per-table special-casing.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .dependencies import get_db, get_pricing_config_path
from .pricing import compute_savings, is_priceable, load_pricing_config

router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_LIST_USER_TABLES_SQL = (
    "SELECT name FROM sqlite_master "
    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
)


class TablesListResponse(BaseModel):
    tables: list[str]


class TableRowsResponse(BaseModel):
    table: str
    total: int
    limit: int
    offset: int
    columns: list[str]
    rows: list[list[Any]]


def _list_user_tables(db: sqlite3.Connection) -> list[str]:
    """Return the real, non-internal table names from `sqlite_master`."""
    rows = db.execute(_LIST_USER_TABLES_SQL).fetchall()
    return [row["name"] for row in rows]


def _validate_table_name(db: sqlite3.Connection, name: str) -> str:
    """Confirm `name` is an exact match against the real table list.

    This is the only thing that makes it safe to later drop `name` into a
    query string: it never reaches that point unless it is byte-for-byte
    equal to a name SQLite itself reports as an existing table. Anything
    else -- a typo, an empty string, or an injection payload like
    `requests; DROP TABLE requests;--` -- fails the membership check here
    and is rejected with 404 before any query referencing it is built, so
    it is never parsed as SQL.
    """
    real_tables = _list_user_tables(db)
    if name not in real_tables:
        raise HTTPException(status_code=404, detail=f"Table '{name}' not found")
    return name


@router.get("/db/tables", response_model=TablesListResponse)
def list_tables(db: sqlite3.Connection = Depends(get_db)) -> TablesListResponse:
    return TablesListResponse(tables=_list_user_tables(db))


def _overlay_requests_savings(
    columns: list[str], raw_rows: list[sqlite3.Row], pricing_config: dict
) -> list[list[Any]]:
    """For the `requests` table only: replace the `actual_cost`/
    `equivalent_cost`/`savings` positions in each row with the live-computed
    values `routes_requests.py` returns, wherever `is_priceable` allows it.
    Rows that aren't priceable (or are priceable but genuinely unconfigured)
    keep the real on-disk NULL for those three columns, same as
    `routes_requests.py`.
    """
    cost_column_index = {
        name: columns.index(name)
        for name in ("actual_cost", "equivalent_cost", "savings")
    }
    rows: list[list[Any]] = []
    for row in raw_rows:
        row_list = list(row)
        if is_priceable(row):
            result = compute_savings(
                pricing_config,
                provider=row["provider"],
                downstream_model=row["downstream_model"],
                gateway_model=row["gateway_model"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
            )
            if not result.unknown:
                row_list[cost_column_index["actual_cost"]] = result.actual_cost
                row_list[cost_column_index["equivalent_cost"]] = result.equivalent_cost
                row_list[cost_column_index["savings"]] = result.savings
        rows.append(row_list)
    return rows


@router.get("/db/tables/{name}", response_model=TableRowsResponse)
def get_table_rows(
    name: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: sqlite3.Connection = Depends(get_db),
    pricing_config_path: Path = Depends(get_pricing_config_path),
) -> TableRowsResponse:
    validated_name = _validate_table_name(db, name)

    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)

    # `validated_name` is only ever a string sqlite_master itself reported
    # as an existing table (checked above), so it is safe to interpolate
    # here -- it cannot carry attacker-controlled SQL. LIMIT/OFFSET are
    # ordinary values and still use `?` bind parameters.
    total = db.execute(f'SELECT COUNT(*) FROM "{validated_name}"').fetchone()[0]

    # `requests` orders most-recent-first (matching `routes_requests.py`'s
    # own `/requests` ordering) since that's the column anyone browsing
    # live traffic actually cares about seeing first. Every other table
    # keeps the original `rowid` (insertion) order -- they're small
    # bookkeeping tables (`collector_state`, `process_state`) with no
    # equivalent "most recent" concept worth special-casing for.
    order_by = (
        "occurred_at DESC, rowid DESC" if validated_name == "requests" else "rowid"
    )
    cursor = db.execute(
        f'SELECT * FROM "{validated_name}" ORDER BY {order_by} LIMIT ? OFFSET ?',
        [limit, offset],
    )
    columns = [description[0] for description in cursor.description]
    raw_rows = cursor.fetchall()

    if validated_name == "requests":
        try:
            pricing_config = load_pricing_config(pricing_config_path)
        except (FileNotFoundError, json.JSONDecodeError):
            pricing_config = {}
        rows = _overlay_requests_savings(columns, raw_rows, pricing_config)
    else:
        rows = [list(row) for row in raw_rows]

    return TableRowsResponse(
        table=validated_name,
        total=total,
        limit=limit,
        offset=offset,
        columns=columns,
        rows=rows,
    )
