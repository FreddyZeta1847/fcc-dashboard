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

import os
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

    Used by `routes_stats.py` (Task 3, read-only) and `routes_pricing.py`
    (Task 4, read/write). Checks the `FCC_DASHBOARD_PRICING_PATH`
    environment variable first, mirroring `api._resolve_db_path`'s
    override seam for the DB path -- so a test can point this at a fixture
    file (or a `tmp_path` file that deliberately doesn't exist, to exercise
    the "no pricing config yet" case) instead of touching the real user's
    `~/.fcc-dashboard/pricing.json`. Falls back to
    `DEFAULT_PRICING_CONFIG_PATH` when the variable isn't set. Resolved at
    call time (not import time) for the same reason `_resolve_db_path` is.
    """
    override = os.environ.get("FCC_DASHBOARD_PRICING_PATH")
    return Path(override) if override else DEFAULT_PRICING_CONFIG_PATH
