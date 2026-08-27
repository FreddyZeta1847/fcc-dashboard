"""
`GET /fcc/catalog` -- what FCC currently has configured, for the pricing picker.

Thin wrapper over `fcc_admin.fetch_fcc_catalog()`, plus one thing that module
cannot do on its own: cross-check the provider log tags against the values
actually observed in our own `requests` table.

That cross-check is the safety net for this whole feature. The `log_tag` we
hand the UI comes from a table in `fcc_admin` that mirrors constants inside
FCC's source, and FCC does not expose those over HTTP. If an FCC upgrade
changes one, the picker would keep emitting a stale string and every price
written through it would silently never match. Reporting the providers we have
genuinely seen in the log lets the UI show that drift instead of hiding it.

`observed_providers` is descriptive, never authoritative: a provider absent
from it may simply not have served traffic yet, which is the normal state for a
freshly configured model. So it is exposed as data for the UI to compare
against, and nothing here rejects, rewrites, or filters a provider because of
it.

Always returns HTTP 200. FCC being stopped is an ordinary state for this app --
it can stop FCC itself via `/control/stop` -- and the client's response to that
is to fall back to manual entry, not to handle an error status.
"""

import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .dependencies import get_db
from .fcc_admin import FccProvider, fetch_fcc_catalog

router = APIRouter()

_DISTINCT_PROVIDERS_SQL = """
SELECT DISTINCT provider
FROM requests
WHERE provider IS NOT NULL AND provider != ''
"""


class FccCatalogResponse(BaseModel):
    """FCC's configured providers, plus what we have actually seen in the log.

    `available=False` means FCC could not be reached; `providers` is empty and
    `error` says why. It is not an error condition -- see the module docstring.
    """

    available: bool
    providers: list[FccProvider]
    observed_providers: list[str]
    error: str | None


def _observed_providers(db: sqlite3.Connection) -> list[str]:
    """Distinct non-empty `provider` values already stored in `requests`."""
    rows = db.execute(_DISTINCT_PROVIDERS_SQL).fetchall()
    return sorted(str(row[0]) for row in rows)


@router.get("/fcc/catalog", response_model=FccCatalogResponse)
async def get_fcc_catalog(
    db: sqlite3.Connection = Depends(get_db),
) -> FccCatalogResponse:
    """Providers and models FCC has configured, for the pricing editor."""
    catalog = await fetch_fcc_catalog()
    return FccCatalogResponse(
        available=catalog.available,
        providers=catalog.providers,
        observed_providers=_observed_providers(db),
        error=catalog.error,
    )
