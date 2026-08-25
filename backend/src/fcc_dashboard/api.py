"""
FastAPI application entrypoint for FCC Dashboard.

Defines the `app` object every route module attaches to and every test's
`TestClient` imports (see BACKEND--architecture: this file is the seam
Phase 3's later tasks and Phase 4/5 all build on). Owns two things:

- The `lifespan` context manager: on startup it opens the real on-disk
  SQLite database (via `init_db`, Phase 2) at the path resolved by
  `_resolve_db_path()` (normally `~/.fcc-dashboard/fcc_dashboard.db`,
  creating the parent directory if it doesn't exist yet) and stores the
  connection on `app.state.db`. On shutdown it closes that connection.
- The dependency-provider functions routes use (`Depends(get_db)`, etc.)
  to reach shared resources without touching `app.state` directly. These
  actually live in `dependencies.py` -- a leaf module with no import from
  this file, so route modules can import them without risking a circular
  import against `api.py`. This module re-exports them (`get_db`,
  `get_pricing_config_path`) so `from fcc_dashboard.api import app, get_db`
  -- what every existing test does -- keeps working unchanged: it's the
  same function object either way, so `app.dependency_overrides[get_db]`
  matches regardless of which module a caller imported `get_db` from.

Routers (one per feature area -- `routes_status`, `routes_requests`,
`routes_stats` here, more added by later tasks) are imported and included
normally, at the top of this file, since
`dependencies.py` being import-order-independent means there's no longer a
reason to delay it.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from . import routes_requests, routes_stats, routes_status
from .db import init_db
from .dependencies import get_db, get_pricing_config_path  # noqa: F401 (re-exported)

DEFAULT_DB_PATH = Path.home() / ".fcc-dashboard" / "fcc_dashboard.db"


def _resolve_db_path() -> Path:
    """Resolve the DB path at call time, not import time.

    Checks the `FCC_DASHBOARD_DB_PATH` environment variable first. This
    seam exists so a test that uses `with TestClient(app) as client:` (the
    idiomatic FastAPI form, which actually runs `lifespan`) can point the
    app at a throwaway file instead of silently creating
    `~/.fcc-dashboard/fcc_dashboard.db` on whoever's machine runs the
    tests. No current test exercises the `lifespan` path at all, but the
    seam is here so the next one that does can use it without editing this
    file. `get_pricing_config_path` in `dependencies.py` (Task 3) should
    follow this same env-var-override pattern for its own default path
    (e.g. `FCC_DASHBOARD_PRICING_PATH`) for the same reason.
    """
    override = os.environ.get("FCC_DASHBOARD_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the on-disk DB on startup; close it on shutdown."""
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    app.state.db = init_db(db_path)
    try:
        yield
    finally:
        app.state.db.close()


app = FastAPI(title="FCC Dashboard API", lifespan=lifespan)

app.include_router(routes_status.router)
app.include_router(routes_requests.router)
app.include_router(routes_stats.router)
