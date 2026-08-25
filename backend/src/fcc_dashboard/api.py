"""
FastAPI application entrypoint for FCC Dashboard.

Defines the `app` object every route module attaches to and every test's
`TestClient` imports (see BACKEND--architecture: this file is the seam
Phase 3's later tasks and Phase 4/5 all build on). Owns two things:

- The `lifespan` context manager: on startup it opens the real on-disk
  SQLite database (via `init_db`, Phase 2) at
  `~/.fcc-dashboard/fcc_dashboard.db` -- creating the parent directory if
  it doesn't exist yet -- and stores the connection on `app.state.db`. On
  shutdown it closes that connection.
- The `get_db` dependency: routes depend on this (`Depends(get_db)`) to
  reach the DB connection rather than touching `app.state` directly. In
  production it just returns `request.app.state.db` (set by `lifespan`
  above). In tests it is never actually called -- tests replace it
  wholesale with `app.dependency_overrides[get_db] = lambda: test_db`, so
  each test gets its own isolated `:memory:` connection without the app
  ever starting up for real. This is the dependency-injection pattern
  every later task's routes (and their tests) should reuse rather than
  inventing a new one.

Routers (one per feature area -- `routes_status` here, more added by later
tasks) are included at the *bottom* of this file, after `get_db` is
defined, and imported there rather than at the top. This is deliberate:
`routes_status.py` imports `get_db` from this module to use as a route
dependency, so if this module imported `routes_status` before `get_db`
existed, the two modules would deadlock on each other (a circular import).
Defining `get_db` first and only then importing the router sidesteps that.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from .db import init_db

DEFAULT_DB_PATH = Path.home() / ".fcc-dashboard" / "fcc_dashboard.db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the on-disk DB on startup; close it on shutdown."""
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    app.state.db = init_db(DEFAULT_DB_PATH)
    try:
        yield
    finally:
        app.state.db.close()


app = FastAPI(title="FCC Dashboard API", lifespan=lifespan)


def get_db(request: Request):
    """Dependency: the app's SQLite connection.

    Reads `request.app.state.db`, populated by `lifespan` on startup for
    real usage. Tests bypass this body entirely via
    `app.dependency_overrides[get_db] = lambda: test_db`.
    """
    return request.app.state.db


# Imported here, not at module top -- see the module docstring for why
# (avoids a circular import with routes_status.py, which needs `get_db`
# above to already exist on this module).
from .routes_status import router as status_router  # noqa: E402

app.include_router(status_router)
