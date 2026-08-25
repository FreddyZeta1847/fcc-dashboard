"""
`GET /status` -- FCC gateway reachability plus per-provider error status.

Two independent pieces of information, both best-effort and both meant to
degrade gracefully rather than 500:

1. `fcc_status`: whether FCC's own gateway process answers its `/health`
   endpoint. This is a live network check, not a DB read, so it's isolated
   in `_check_fcc_health()` -- a plain module-level `async def` that does
   the actual `httpx` call. Keeping it a bare function (rather than e.g. a
   method closing over a client instance) is what lets tests intercept it
   with `monkeypatch.setattr(routes_status, "_check_fcc_health", ...)`: the
   route handler below calls `_check_fcc_health()` by name at request time,
   so whatever monkeypatch has bound that name to on the module is what
   runs -- a closure that had captured the original function at import
   time would not be patchable this way.

2. `providers`: per distinct provider, the status implied by its most
   recent `error`-status row in `requests`. This is a DB read, so it goes
   through the `get_db` dependency from `dependencies.py` like every other
   route in this app will. Imported from `dependencies.py`, not `api.py`,
   so this module never depends on `api.py` at all -- see
   `dependencies.py`'s docstring for why that matters.

Status classification is the project-wide locked rule (see
BACKEND--architecture / phase-3-api plan): `http_status` 401/403 ->
"stale_key", 429 -> "rate_limited", a 5xx status or no `http_status` at all
(a timeout/connection-level failure, which never got a response to read a
status off of) -> "down". Anything else -> "ok" (reachable in principle,
though in practice every provider this endpoint reports on has *some*
error row, since providers with none aren't listed at all).

The response shape is enforced with Pydantic models (`ProviderStatus`,
`StatusResponse`) rather than returned as a bare dict, so FastAPI's
generated OpenAPI schema documents the real shape and `Literal` closes the
status vocabulary at the response boundary. This is meant to set the
convention for this phase's other routes, not just this one.
"""

import sqlite3
from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .dependencies import get_db

router = APIRouter()

FCC_HEALTH_URL = "http://localhost:8082/health"
FCC_HEALTH_TIMEOUT = 2.0

_STALE_KEY_HTTP_STATUSES = {401, 403}
_RATE_LIMITED_HTTP_STATUSES = {429}


class ProviderStatus(BaseModel):
    provider: str
    status: Literal["ok", "stale_key", "rate_limited", "down"]
    last_error_at: str | None
    http_status: int | None


class StatusResponse(BaseModel):
    fcc_status: Literal["up", "down"]
    providers: list[ProviderStatus]


async def _check_fcc_health() -> httpx.Response:
    """Hit FCC's own `/health` endpoint. May raise an httpx exception
    (timeout, connection error, ...) -- the caller is responsible for
    treating that as "down" rather than letting it become a 500.
    """
    async with httpx.AsyncClient(timeout=FCC_HEALTH_TIMEOUT) as client:
        return await client.get(FCC_HEALTH_URL)


def _classify_provider_status(http_status: int | None) -> str:
    """Locked classification rule -- see module docstring."""
    if http_status in _STALE_KEY_HTTP_STATUSES:
        return "stale_key"
    if http_status in _RATE_LIMITED_HTTP_STATUSES:
        return "rate_limited"
    if http_status is None or 500 <= http_status < 600:
        return "down"
    return "ok"


def _latest_error_per_provider(db: sqlite3.Connection) -> list[ProviderStatus]:
    """One entry per distinct provider with at least one `error` row, using
    that provider's most recent `error` row to classify its current
    status. Providers with zero error rows are omitted entirely. Safe
    against an empty `requests` table (returns `[]`).

    Uses `ROW_NUMBER() OVER (PARTITION BY provider ORDER BY occurred_at
    DESC, rowid DESC)` rather than a `MAX(occurred_at)` self-join, so ties
    (two error rows for the same provider sharing an identical
    `occurred_at` timestamp) resolve deterministically to the
    higher-`rowid` row -- SQLite's own insertion-order tiebreaker -- instead
    of an arbitrary row, which a bare `GROUP BY` would allow.
    """
    rows = db.execute(
        """
        SELECT provider, http_status, occurred_at FROM (
            SELECT provider, http_status, occurred_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY provider
                       ORDER BY occurred_at DESC, rowid DESC
                   ) AS rn
            FROM requests
            WHERE status = 'error' AND provider IS NOT NULL
        )
        WHERE rn = 1
        ORDER BY provider
        """
    ).fetchall()

    return [
        ProviderStatus(
            provider=row["provider"],
            status=_classify_provider_status(row["http_status"]),
            last_error_at=row["occurred_at"],
            http_status=row["http_status"],
        )
        for row in rows
    ]


@router.get("/status", response_model=StatusResponse)
async def get_status(db: sqlite3.Connection = Depends(get_db)) -> StatusResponse:
    try:
        health_response = await _check_fcc_health()
        fcc_status = "up" if health_response.status_code == 200 else "down"
    except httpx.HTTPError:
        fcc_status = "down"

    return StatusResponse(
        fcc_status=fcc_status,
        providers=_latest_error_per_provider(db),
    )
