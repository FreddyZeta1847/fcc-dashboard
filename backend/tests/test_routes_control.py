"""Tests for POST /control/start and POST /control/stop."""

from pathlib import Path

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
        routes_control,
        "find_fcc_server_executable",
        lambda: Path("/fake/fcc-server"),
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


def test_start_with_stale_untracked_pid_clears_it_and_launches_successfully(
    client_and_db, monkeypatch
):
    """Finding A: a stale, non-NULL PID on file (a crashed fcc-server, or
    one left behind by a stop_failed retry) must not be mistaken for "a
    concurrent request beat us" -- that misreading terminates the process
    just launched and reports a dead PID as already_running, forever. The
    conditional `WHERE pid IS NULL` write only matches a genuinely NULL
    row, so a stale non-NULL PID must be cleared (once confirmed untracked
    via is_tracked_fcc_process) before that write is even attempted."""
    client, db = client_and_db
    db.execute(
        "UPDATE process_state SET pid = ?, started_at = ?",
        (1001, "2026-08-25T00:00:00.000Z"),
    )
    db.commit()

    import fcc_dashboard.routes_control as routes_control

    _patch_health(monkeypatch, raise_error=True)
    monkeypatch.setattr(routes_control, "is_tracked_fcc_process", lambda pid: False)
    monkeypatch.setattr(
        routes_control,
        "find_fcc_server_executable",
        lambda: Path("/fake/fcc-server"),
    )
    monkeypatch.setattr(routes_control, "launch_detached", lambda executable: 2002)

    terminate_calls = []
    monkeypatch.setattr(
        routes_control,
        "terminate_process",
        lambda pid, **kwargs: terminate_calls.append(pid) or True,
    )

    response = client.post("/control/start")

    assert response.status_code == 200
    assert response.json() == {"action": "started", "pid": 2002}
    assert terminate_calls == []

    row = db.execute("SELECT pid FROM process_state").fetchone()
    assert row["pid"] == 2002


def test_stop_when_not_running(client_and_db):
    client, _db = client_and_db
    response = client.post("/control/stop")
    assert response.status_code == 200
    assert response.json()["action"] == "not_running"


def test_stop_terminates_and_clears_state(client_and_db, monkeypatch):
    client, db = client_and_db
    db.execute(
        "UPDATE process_state SET pid = ?, started_at = ?",
        (54321, "2026-08-25T00:00:00.000Z"),
    )
    db.commit()

    import fcc_dashboard.routes_control as routes_control

    monkeypatch.setattr(routes_control, "is_tracked_fcc_process", lambda pid: True)
    terminate_calls = []
    monkeypatch.setattr(
        routes_control,
        "terminate_process",
        lambda pid, **kwargs: terminate_calls.append(pid) or True,
    )

    response = client.post("/control/stop")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "stopped"
    assert body["pid"] == 54321
    assert terminate_calls == [54321]

    row = db.execute("SELECT pid, started_at FROM process_state").fetchone()
    assert row["pid"] is None
    assert row["started_at"] is None


def test_stop_with_stale_pid_clears_state_without_terminating(client_and_db, monkeypatch):
    client, db = client_and_db
    db.execute(
        "UPDATE process_state SET pid = ?, started_at = ?",
        (99999, "2026-08-25T00:00:00.000Z"),
    )
    db.commit()

    import fcc_dashboard.routes_control as routes_control

    monkeypatch.setattr(routes_control, "is_tracked_fcc_process", lambda pid: False)

    response = client.post("/control/stop")

    body = response.json()
    assert body["action"] == "not_running"

    row = db.execute("SELECT pid FROM process_state").fetchone()
    assert row["pid"] is None


def test_stop_refuses_to_terminate_untracked_process(client_and_db, monkeypatch):
    """CRITICAL: if the persisted PID is alive but is NOT recognized as our
    fcc-server process (e.g. the OS reused the PID for something else after
    a reboot), stop must NEVER call terminate_process on it -- it must
    instead treat this exactly like "not running": clear process_state and
    report not_running, leaving the unrelated process untouched."""
    client, db = client_and_db
    db.execute(
        "UPDATE process_state SET pid = ?, started_at = ?",
        (13579, "2026-08-25T00:00:00.000Z"),
    )
    db.commit()

    import fcc_dashboard.routes_control as routes_control

    monkeypatch.setattr(routes_control, "is_tracked_fcc_process", lambda pid: False)
    terminate_calls = []
    monkeypatch.setattr(
        routes_control,
        "terminate_process",
        lambda pid, **kwargs: terminate_calls.append(pid) or True,
    )

    response = client.post("/control/stop")

    body = response.json()
    assert body["action"] == "not_running"
    assert body["pid"] is None
    assert terminate_calls == []

    row = db.execute("SELECT pid, started_at FROM process_state").fetchone()
    assert row["pid"] is None
    assert row["started_at"] is None


def test_start_already_running_returns_null_pid_for_untracked_process(
    client_and_db, monkeypatch
):
    """If /health says FCC is up but the persisted PID doesn't check out as
    fcc-server (is_tracked_fcc_process is False), start must not vouch for
    that PID -- it should report already_running with pid: null."""
    client, db = client_and_db
    db.execute(
        "UPDATE process_state SET pid = ?, started_at = ?",
        (24680, "2026-08-25T00:00:00.000Z"),
    )
    db.commit()

    import fcc_dashboard.routes_control as routes_control

    _patch_health(monkeypatch, status_code=200)
    monkeypatch.setattr(routes_control, "is_tracked_fcc_process", lambda pid: False)

    response = client.post("/control/start")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "already_running"
    assert body["pid"] is None


def test_start_already_running_returns_pid_when_tracked(client_and_db, monkeypatch):
    client, db = client_and_db
    db.execute(
        "UPDATE process_state SET pid = ?, started_at = ?",
        (24680, "2026-08-25T00:00:00.000Z"),
    )
    db.commit()

    import fcc_dashboard.routes_control as routes_control

    _patch_health(monkeypatch, status_code=200)
    monkeypatch.setattr(routes_control, "is_tracked_fcc_process", lambda pid: True)

    response = client.post("/control/start")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "already_running"
    assert body["pid"] == 24680


def test_stop_returns_stop_failed_and_keeps_pid_when_terminate_fails(
    client_and_db, monkeypatch
):
    client, db = client_and_db
    db.execute(
        "UPDATE process_state SET pid = ?, started_at = ?",
        (11111, "2026-08-25T00:00:00.000Z"),
    )
    db.commit()

    import fcc_dashboard.routes_control as routes_control

    monkeypatch.setattr(routes_control, "is_tracked_fcc_process", lambda pid: True)
    monkeypatch.setattr(routes_control, "terminate_process", lambda pid, **kw: False)

    response = client.post("/control/stop")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "stop_failed"
    assert body["pid"] == 11111

    row = db.execute("SELECT pid FROM process_state").fetchone()
    assert row["pid"] == 11111


def test_start_launch_failed_when_launch_detached_raises_oserror(
    client_and_db, monkeypatch
):
    client, _db = client_and_db
    _patch_health(monkeypatch, raise_error=True)

    import fcc_dashboard.routes_control as routes_control

    monkeypatch.setattr(
        routes_control,
        "find_fcc_server_executable",
        lambda: Path("/fake/fcc-server"),
    )

    def _raise_oserror(executable):
        raise OSError("executable is not executable")

    monkeypatch.setattr(routes_control, "launch_detached", _raise_oserror)

    response = client.post("/control/start")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "launch_failed"
    assert body["pid"] is None


def test_control_endpoints_reject_cross_site_request(client_and_db):
    client, _db = client_and_db

    response = client.post(
        "/control/start", headers={"Sec-Fetch-Site": "cross-site"}
    )
    assert response.status_code == 403

    response = client.post(
        "/control/stop", headers={"Sec-Fetch-Site": "cross-site"}
    )
    assert response.status_code == 403


def test_control_endpoints_allow_same_origin_and_missing_header(
    client_and_db, monkeypatch
):
    client, _db = client_and_db
    _patch_health(monkeypatch, raise_error=True)

    import fcc_dashboard.routes_control as routes_control

    monkeypatch.setattr(routes_control, "find_fcc_server_executable", lambda: None)

    response = client.post(
        "/control/start", headers={"Sec-Fetch-Site": "same-origin"}
    )
    assert response.status_code == 200

    response = client.post("/control/stop")
    assert response.status_code == 200


def test_full_start_stop_start_lifecycle(client_and_db, monkeypatch):
    client, db = client_and_db
    import fcc_dashboard.routes_control as routes_control

    launched = []
    monkeypatch.setattr(
        routes_control,
        "find_fcc_server_executable",
        lambda: Path("/fake/fcc-server"),
    )
    monkeypatch.setattr(
        routes_control,
        "launch_detached",
        lambda e: launched.append(e) or (1000 + len(launched)),
    )
    monkeypatch.setattr(routes_control, "is_tracked_fcc_process", lambda pid: True)
    monkeypatch.setattr(routes_control, "terminate_process", lambda pid, **kw: True)

    _patch_health(monkeypatch, raise_error=True)
    response1 = client.post("/control/start")
    assert response1.json() == {"action": "started", "pid": 1001}

    response2 = client.post("/control/stop")
    assert response2.json() == {"action": "stopped", "pid": 1001}
    row = db.execute("SELECT pid, started_at FROM process_state").fetchone()
    assert row["pid"] is None and row["started_at"] is None

    response3 = client.post("/control/start")
    assert response3.json() == {"action": "started", "pid": 1002}
    assert len(launched) == 2
