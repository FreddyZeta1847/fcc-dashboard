"""Tests for POST /control/start and POST /control/stop."""

import pytest
from fastapi.testclient import TestClient

from fcc_dashboard.api import app, get_db, get_fcc_log_path
from fcc_dashboard.db import init_db


@pytest.fixture
def client_and_db(tmp_path):
    test_db = init_db(":memory:")
    log_path = tmp_path / "server.log"
    log_path.write_text("", encoding="utf-8")
    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_fcc_log_path] = lambda: log_path
    yield TestClient(app), test_db
    app.dependency_overrides.clear()


def _patch_health(monkeypatch, status_code=None, raise_error=False):
    import fcc_dashboard.routes_status as routes_status
    import httpx

    async def fake_check(*args, **kwargs):
        if raise_error:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(status_code)

    monkeypatch.setattr(routes_status, "_check_fcc_health", fake_check)


def test_start_when_already_running_is_a_noop(client_and_db, monkeypatch):
    client, _db = client_and_db
    _patch_health(monkeypatch, status_code=200)

    response = client.post("/control/start")

    assert response.status_code == 200
    assert response.json()["action"] == "already_running"


def test_start_when_executable_not_found(client_and_db, monkeypatch):
    client, _db = client_and_db
    _patch_health(monkeypatch, raise_error=True)

    import fcc_dashboard.routes_control as routes_control

    monkeypatch.setattr(routes_control, "find_fcc_server_executable", lambda: None)

    response = client.post("/control/start")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "executable_not_found"
    assert body["pid"] is None


def test_start_launches_and_persists_pid(client_and_db, monkeypatch):
    client, db = client_and_db
    _patch_health(monkeypatch, raise_error=True)

    import fcc_dashboard.routes_control as routes_control

    monkeypatch.setattr(
        routes_control, "find_fcc_server_executable", lambda: "/fake/fcc-server"
    )
    monkeypatch.setattr(routes_control, "launch_detached", lambda executable: 12345)

    response = client.post("/control/start")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "started"
    assert body["pid"] == 12345

    row = db.execute("SELECT pid FROM process_state").fetchone()
    assert row["pid"] == 12345


def test_start_flushes_collector_before_acting(client_and_db, monkeypatch, tmp_path):
    """The flush step must run even on a start call -- verify poll_once
    actually gets invoked by checking collector_state changes."""
    client, db = client_and_db
    _patch_health(monkeypatch, raise_error=True)

    import fcc_dashboard.routes_control as routes_control

    monkeypatch.setattr(routes_control, "find_fcc_server_executable", lambda: None)

    before = db.execute("SELECT last_run_at FROM collector_state").fetchone()
    assert before["last_run_at"] is None

    client.post("/control/start")

    after = db.execute("SELECT last_run_at FROM collector_state").fetchone()
    assert after["last_run_at"] is not None
