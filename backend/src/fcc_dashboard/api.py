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
  Immediately after `init_db`, it also runs `_reconcile_process_state`:
  if `process_state` has a non-NULL PID left over from a previous session
  but that PID no longer looks like `fcc-server` (per
  `process_control.is_tracked_fcc_process` -- the machine may have
  rebooted and the OS reused the PID for something else entirely), the
  stale row is cleared before any request has a chance to act on it. This
  is what makes the "start FCC, reboot, click Stop" PID-reuse hazard
  structurally impossible rather than merely unlikely: `stop_fcc`'s own
  identity check would also catch it, but reconciling at startup means a
  wrong PID never sits around waiting to be misread as "ours" in the
  first place.
  After that, `lifespan` starts `collector.run_collector_loop` as a
  background `asyncio.create_task` -- this is what actually schedules
  `poll_once` (Phase 2) to run at all: before this, `poll_once` only ever
  ran as a side effect of `POST /control/start`/`/control/stop`'s
  flush-before-action step, so the dashboard showed nothing new during
  ordinary browsing unless a user happened to click Start or Stop. The
  loop's own first action is the poll itself (not a sleep), which is what
  gives every startup its "catch-up read" of whatever FCC logged while
  the dashboard was down -- see `collector.run_collector_loop`'s
  docstring. Using `asyncio.create_task` (not `await`-ing it directly)
  is what lets it run concurrently with request handling on the same
  event loop, since `poll_once` runs off-thread via `run_in_threadpool`
  inside the loop and never blocks it for long. On shutdown, the `finally`
  block cancels this task and awaits it (suppressing the
  `asyncio.CancelledError` that produces) BEFORE closing
  `app.state.db` -- in that order, deliberately: the loop shares that same
  connection, so closing the DB first could let an in-flight
  `poll_once` call hit a closed-connection error instead of just being
  cleanly cancelled.
- The dependency-provider functions routes use (`Depends(get_db)`, etc.)
  to reach shared resources without touching `app.state` directly. These
  actually live in `dependencies.py` -- a leaf module with no import from
  this file, so route modules can import them without risking a circular
  import against `api.py`. This module re-exports them (`get_db`,
  `get_pricing_config_path`, `get_fcc_log_path`) so `from fcc_dashboard.api
  import app, get_db` -- what every existing test does -- keeps working
  unchanged: it's the same function object either way, so
  `app.dependency_overrides[get_db]` matches regardless of which module a
  caller imported `get_db` from.

Routers (one per feature area -- `routes_status`, `routes_requests`,
`routes_stats`, `routes_pricing`, `routes_db`, `routes_control` here) are
imported and included normally, at the top of this file, since
`dependencies.py` being import-order-independent means there's no longer a
reason to delay it.
"""

import asyncio
import contextlib
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from . import (
    collector,
    routes_control,
    routes_db,
    routes_pricing,
    routes_requests,
    routes_stats,
    routes_status,
)
from .db import init_db
from .dependencies import (  # noqa: F401 (re-exported)
    get_db,
    get_fcc_log_path,
    get_pricing_config_path,
)
from .process_control import is_tracked_fcc_process

DEFAULT_DB_PATH = Path.home() / ".fcc-dashboard" / "fcc_dashboard.db"


def _resolve_db_path() -> Path:
    """Resolve the DB path at call time, not import time.

    Checks the `FCC_DASHBOARD_DB_PATH` environment variable first. This
    seam exists so a test that uses `with TestClient(app) as client:` (the
    idiomatic FastAPI form, which actually runs `lifespan`) can point the
    app at a throwaway file instead of silently creating
    `~/.fcc-dashboard/fcc_dashboard.db` on whoever's machine runs the
    tests. `tests/test_api.py` exercises the real `lifespan` path using
    this seam (via `with TestClient(app) as client:`), so any future
    change here should keep that test green.
    `get_pricing_config_path` in `dependencies.py` (Task 3) should
    follow this same env-var-override pattern for its own default path
    (e.g. `FCC_DASHBOARD_PRICING_PATH`) for the same reason.
    """
    override = os.environ.get("FCC_DASHBOARD_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


def _reconcile_process_state(db: sqlite3.Connection) -> None:
    """Clear a stale/untrustworthy persisted PID at startup.

    `process_state.pid` survives across our own restarts (and across a
    full machine reboot) by design -- that's how `/control/stop` finds a
    process it started in a previous session. But a reboot is exactly the
    scenario where a persisted PID becomes dangerous: the OS is free to
    reuse that PID number for a completely different process, and nothing
    else in this codebase reconciles the persisted value against reality
    before a request could act on it.

    Run once, right after `init_db`, before the app starts serving
    requests: if a PID is on file and `is_tracked_fcc_process` can't
    confirm it's still plausibly `fcc-server`, the row is reset to
    `NULL`/`NULL` -- the same "nothing to track" baseline
    `routes_control._clear_process_state` uses. This mirrors that
    function's logic rather than importing it, to keep `api.py` free of a
    dependency on the routes layer (route modules already depend on
    `dependencies.py`/`db.py`, not the reverse).
    """
    row = db.execute("SELECT pid FROM process_state WHERE id = 1").fetchone()
    pid = row["pid"] if row is not None else None
    if pid is not None and not is_tracked_fcc_process(pid):
        db.execute(
            "UPDATE process_state SET pid = NULL, started_at = NULL WHERE id = 1"
        )
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the on-disk DB on startup, start the background collector loop,
    then reverse both cleanly on shutdown -- see the module docstring's
    `lifespan` section for why the collector task is cancelled before
    `app.state.db.close()`, not after.
    """
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    app.state.db = init_db(db_path)
    _reconcile_process_state(app.state.db)
    collector_task = asyncio.create_task(collector.run_collector_loop(app.state.db))
    try:
        yield
    finally:
        collector_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await collector_task
        app.state.db.close()


app = FastAPI(title="FCC Dashboard API", lifespan=lifespan)

app.include_router(routes_status.router)
app.include_router(routes_requests.router)
app.include_router(routes_stats.router)
app.include_router(routes_pricing.router)
app.include_router(routes_db.router)
app.include_router(routes_control.router)
