"""
Tests for `fcc_dashboard.api` itself -- the real startup path and the
assembled route set.

Every other test file in this suite bypasses `lifespan` entirely via
`app.dependency_overrides[get_db] = lambda: test_db`, so `_resolve_db_path`,
`init_db` against a real on-disk file, and the lifespan startup/shutdown
code in `api.py` are never actually exercised anywhere else. This file
closes that gap: it points the env-var override seams at a `tmp_path` file
and uses `TestClient` as a context manager (`with TestClient(app) as
client:`), which is what actually runs FastAPI's lifespan, unlike
instantiating `TestClient(app)` directly.
"""

import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

from fcc_dashboard.api import app
from fcc_dashboard.db import init_db


class _SimulatedShutdownDrainFailure(RuntimeError):
    """Stand-in for Finding 2's residual case: the collector's shielded
    in-flight poll itself fails while being drained during shutdown, so
    `run_collector_loop`'s own `except asyncio.CancelledError: await
    poll_future` line re-raises the poll's exception instead of
    `CancelledError`."""


def test_lifespan_starts_real_db_and_serves_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("FCC_DASHBOARD_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("FCC_DASHBOARD_PRICING_PATH", str(tmp_path / "pricing.json"))

    with TestClient(app) as client:
        response = client.get("/db/tables")

    assert response.status_code == 200
    assert set(response.json()["tables"]) == {
        "requests", "collector_state", "process_state",
    }
    assert (tmp_path / "test.db").exists()


def test_lifespan_reconciles_untracked_pid_at_startup(tmp_path, monkeypatch):
    """A PID persisted by a previous session that no longer looks like
    fcc-server (here, simulated by a PID that simply doesn't exist -- the
    same "astronomically unlikely" convention test_process_control.py
    uses) must be cleared by the startup reconciliation step in
    `lifespan`, before any request could ever act on it."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("FCC_DASHBOARD_DB_PATH", str(db_path))
    monkeypatch.setenv("FCC_DASHBOARD_PRICING_PATH", str(tmp_path / "pricing.json"))

    seed_db = init_db(db_path)
    seed_db.execute(
        "UPDATE process_state SET pid = ?, started_at = ?",
        (999_999, "2026-08-25T00:00:00.000Z"),
    )
    seed_db.commit()
    seed_db.close()

    with TestClient(app):
        pass

    check_conn = sqlite3.connect(db_path)
    check_conn.row_factory = sqlite3.Row
    row = check_conn.execute(
        "SELECT pid, started_at FROM process_state"
    ).fetchone()
    check_conn.close()

    assert row["pid"] is None
    assert row["started_at"] is None


def test_lifespan_leaves_tracked_pid_untouched_at_startup(tmp_path, monkeypatch):
    """Finding B / positive path: the sibling of
    test_lifespan_reconciles_untracked_pid_at_startup above. A PID that
    is_tracked_fcc_process confirms is still fcc-server must survive
    lifespan startup unchanged -- nothing currently proves the "good PID"
    side of _reconcile_process_state, only the "bad PID gets cleared"
    side."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("FCC_DASHBOARD_DB_PATH", str(db_path))
    monkeypatch.setenv("FCC_DASHBOARD_PRICING_PATH", str(tmp_path / "pricing.json"))

    seed_db = init_db(db_path)
    seed_db.execute(
        "UPDATE process_state SET pid = ?, started_at = ?",
        (13579, "2026-08-25T00:00:00.000Z"),
    )
    seed_db.commit()
    seed_db.close()

    import fcc_dashboard.api as api

    monkeypatch.setattr(api, "is_tracked_fcc_process", lambda pid: True)

    with TestClient(app):
        pass

    check_conn = sqlite3.connect(db_path)
    check_conn.row_factory = sqlite3.Row
    row = check_conn.execute(
        "SELECT pid, started_at FROM process_state"
    ).fetchone()
    check_conn.close()

    assert row["pid"] == 13579
    assert row["started_at"] == "2026-08-25T00:00:00.000Z"


def test_lifespan_starts_and_cancels_the_collector_loop(monkeypatch, tmp_path):
    calls = []

    async def fake_run_collector_loop(db, interval=5.0):
        try:
            while True:
                calls.append(1)
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            calls.append("cancelled")
            raise

    import fcc_dashboard.api as api

    monkeypatch.setattr(api.collector, "run_collector_loop", fake_run_collector_loop)
    monkeypatch.setenv("FCC_DASHBOARD_DB_PATH", str(tmp_path / "test.db"))

    with TestClient(app) as client:
        response = client.get("/status")
        assert response.status_code == 200

    # By the time the `with` block exits, lifespan's shutdown path has
    # run -- the loop must have been cancelled, not left dangling.
    assert "cancelled" in calls
    assert len(calls) >= 2  # proves the fake loop actually ran at least once before cancellation


def test_lifespan_closes_db_even_when_collector_task_fails_during_shutdown_drain(
    monkeypatch, tmp_path
):
    # Finding 2 (final review): if the collector task ends with a
    # non-CancelledError exception during shutdown (the residual case
    # documented in collector.run_collector_loop's docstring -- the
    # shielded in-flight poll itself fails while being drained), that
    # exception must not skip `app.state.db.close()`. Otherwise the SQLite
    # connection (and its WAL/SHM files) leak.
    async def fake_run_collector_loop_that_fails_on_drain(db, interval=5.0):
        try:
            while True:
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            raise _SimulatedShutdownDrainFailure(
                "simulated poll failure during shutdown drain"
            )

    import fcc_dashboard.api as api

    monkeypatch.setattr(
        api.collector, "run_collector_loop", fake_run_collector_loop_that_fails_on_drain
    )
    monkeypatch.setenv("FCC_DASHBOARD_DB_PATH", str(tmp_path / "test.db"))

    with pytest.raises(_SimulatedShutdownDrainFailure):
        with TestClient(app) as client:
            response = client.get("/status")
            assert response.status_code == 200

    # The DB connection must have been closed despite the propagating
    # exception -- attempting to use it now must fail as "closed", not
    # succeed (which would mean it leaked open).
    with pytest.raises(sqlite3.ProgrammingError):
        app.state.db.execute("SELECT 1")


def test_openapi_route_set_is_complete():
    paths = set(app.openapi()["paths"])
    assert paths == {
        "/status",
        "/requests",
        "/stats",
        "/pricing",
        "/pricing/refresh",
        "/db/tables",
        "/db/tables/{name}",
        "/control/start",
        "/control/stop",
        "/fcc/catalog",
    }
