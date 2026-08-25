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

import sqlite3

from fastapi.testclient import TestClient

from fcc_dashboard.api import app
from fcc_dashboard.db import init_db


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
    }
