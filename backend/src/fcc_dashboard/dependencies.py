"""
FastAPI dependency-provider functions for FCC Dashboard.

A deliberate leaf module: nothing here imports from `api.py` (or from any
route module), so any of them can safely import from here in any order --
including before `fcc_dashboard.api` has been imported at all. This is the
fix for a circular-import trap the original version of this app had:
`api.py` used to define `get_db` itself and route modules imported it
straight from `api.py`, which only worked because every real entry point
(tests, uvicorn) happened to import `fcc_dashboard.api` first. If anything
ever imported a route module before `fcc_dashboard.api`, that would break
with `ImportError: cannot import name ... from partially initialized
module`. Putting the dependency providers in their own leaf module removes
the ordering requirement entirely.

`api.py` re-exports `get_db` (and any other dependency here) from this
module, so `from fcc_dashboard.api import app, get_db` -- what every
existing test does -- keeps working unchanged: it's the same function
object, so `app.dependency_overrides[get_db] = ...` still matches whether
callers import `get_db` from `api` or from here.
"""

import sqlite3
from pathlib import Path

from fastapi import Request

DEFAULT_PRICING_CONFIG_PATH = Path.home() / ".fcc-dashboard" / "pricing.json"


def get_db(request: Request) -> sqlite3.Connection:
    """Dependency: the app's SQLite connection.

    Reads `request.app.state.db`, populated by `api.py`'s `lifespan` on
    startup for real usage. Tests bypass this body entirely via
    `app.dependency_overrides[get_db] = lambda: test_db`.
    """
    return request.app.state.db


def get_pricing_config_path() -> Path:
    """Dependency: where the pricing config JSON lives on disk.

    Stub for Task 3, which will read pricing data through this. Returns
    the default `~/.fcc-dashboard/pricing.json` path for now. Task 3
    should follow the same env-var-override convention `api._resolve_db_path`
    established for the DB path (e.g. an `FCC_DASHBOARD_PRICING_PATH`
    override), so tests can point this at a fixture file without touching
    the real user's home directory -- see `api.py`'s `_resolve_db_path` for
    the pattern to copy.
    """
    return DEFAULT_PRICING_CONFIG_PATH
