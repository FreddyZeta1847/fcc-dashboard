# Phase 4 — Process Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the dashboard control over FCC's `fcc-server` process — start it as a detached process (survives the dashboard exiting), stop it, and use `/health` as the authoritative "is it running" signal rather than trusting a stored PID alone. Wire this into `POST /control/start` / `POST /control/stop`, deferred from Phase 3.

**Architecture:** A new `process_control.py` module holds pure process-management primitives (find the executable, launch detached, check liveness, terminate) — no FastAPI, no DB, fully unit-testable against a real (but harmless) dummy subprocess. A new `routes_control.py` orchestrates: flush the collector, check current status, act, persist/clear a new `process_state` DB table. This mirrors Phase 2/3's layering (pure logic module + thin route module).

**Tech Stack:** `psutil` (new runtime dependency — the standard, cross-platform way to check process liveness and terminate an arbitrary PID; Python's stdlib `os.kill`/signals don't behave consistently for this across Windows/POSIX). `shutil.which` (stdlib) to locate `fcc-server` on PATH rather than guessing an install path.

**Spec:** `vault-fcc-dashboard/plans/PHASE-4-PROCESS-CONTROL.md`, `vault-fcc-dashboard/features/BACKEND/BACKEND--process-control.md`, `BACKEND--api.md`, `BACKEND--collector.md`.

## Global Constraints

- `fcc-server` must be launched detached — its lifetime must NOT be tied to our backend process (confirmed user requirement, locked earlier in this project). On Windows this means `subprocess.Popen` with `creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP`; on POSIX, `start_new_session=True`. Branch on `sys.platform`.
- `/health` (reusing `routes_status.py`'s existing `_check_fcc_health` helper — do not duplicate this logic) is the authoritative "is FCC running" signal. The persisted PID is used only for the "stop" action, never alone to answer "is it up."
- **Flush-before-restart**: both `start` and `stop` must call the collector's `poll_once` (Phase 2) against the current DB connection and FCC's log path BEFORE taking any process action — this is the safeguard against the one accepted data-loss edge case (start->stop->start-again before the dashboard ever reads in between).
- FCC's log path is a fixed, well-known location (`~/.fcc/logs/server.log`, per this project's own investigation of FCC's source, documented in `current-task.md`) — expose it via a new `get_fcc_log_path` dependency in `dependencies.py`, following the existing `FCC_DASHBOARD_DB_PATH`/`FCC_DASHBOARD_PRICING_PATH` env-var-override-at-call-time convention (env var: `FCC_LOG_PATH`).
- `find_fcc_server_executable` uses `shutil.which("fcc-server")` — never a hardcoded install path (this varies across OSes/users' `uv tool` install locations).
- Starting when already running (per `/health`) is a graceful no-op, not an error — return the current state, don't double-launch.
- Stopping when not running (no persisted PID, or PID persisted but not alive) is a graceful no-op, not an error.
- Route-level tests mock the process-management primitives (`find_fcc_server_executable`/`launch_detached`/`terminate_process`/`_check_fcc_health`) — they test orchestration logic, not real process spawning. Task 1's own tests are the ones that verify the primitives work against a real (dummy, harmless) subprocess.

---

### Task 1: Process management primitives and `process_state` schema

**Files:**
- Modify: `backend/src/fcc_dashboard/db.py` (add `process_state` table)
- Create: `backend/src/fcc_dashboard/process_control.py`
- Test: `backend/tests/test_db.py` (add process_state tests)
- Test: `backend/tests/test_process_control.py`

**Interfaces:**
- Consumes: `psutil` (new dependency — `uv add psutil`).
- Produces: `find_fcc_server_executable() -> Path | None`, `launch_detached(executable: Path) -> int` (returns the new process's PID), `is_process_alive(pid: int) -> bool`, `terminate_process(pid: int, timeout: float = 5.0) -> bool` (returns True if the process is confirmed stopped, whether it exited gracefully or had to be force-killed; True also if it wasn't running to begin with). `process_state` table: single-row (like `collector_state`), columns `pid INTEGER`, `started_at TEXT` (nullable — NULL means "nothing started by us is currently tracked").

**Contract:**
- `find_fcc_server_executable()`: thin wrapper around `shutil.which("fcc-server")`, returning a `Path` if found, `None` if not on PATH. Must not raise.
- `launch_detached(executable)`: starts `executable` as a fully detached process (no stdin/stdout/stderr pipes held open by our process — redirect to `subprocess.DEVNULL` so it doesn't block on an unread pipe buffer once we exit) and returns its PID immediately, without waiting for it to do anything. Must use the platform-specific detachment flags described in Global Constraints.
- `is_process_alive(pid)`: `True` if a process with that PID currently exists and is running, `False` otherwise (including if the PID doesn't exist, or exists but is a *different* process than the one we started — since PIDs get reused after a reboot, per BACKEND--process-control's own stated caveat; this function only answers "does a process with this PID exist right now," the caller is responsible for treating this as advisory, not authoritative, per the Global Constraints rule that `/health` is authoritative). Must not raise on an invalid/nonexistent PID.
- `terminate_process(pid, timeout=5.0)`: if the PID isn't alive, return `True` immediately (already stopped). Otherwise send a graceful terminate signal, wait up to `timeout` seconds, and if still alive after that, force-kill it. Returns `True` once confirmed stopped (by either method), `False` only if a stop attempt was made and the process is somehow still alive afterward (should be rare/impossible with a force-kill, but the contract allows for a `False` return rather than raising, since an OS-level termination failure shouldn't crash the caller).
- `process_state` table: `init_db` creates it if missing (idempotent, same singleton-row pattern as `collector_state` — one row, `pid` and `started_at` both start `NULL`).

**Clarifying note (added in the Phase 4 final-review fix wave):** the `is_process_alive` bullet above is self-contradictory as written — it first says `False` covers "exists but is a *different* process than the one we started," then immediately says the function "only answers 'does a process with this PID exist right now.'" Those can't both be true: a reused PID belongs to a real, running process, so an existence-only check returns `True` for it, not `False`. The second half is the accurate contract — `is_process_alive` never was, and still isn't, identity-aware. The caller-side identity check the first half gestured at but never assigned to anyone is `is_tracked_fcc_process(pid)`, added to `process_control.py` in the final-review fix wave: it additionally checks the process's name before anything is allowed to treat a PID as "ours" for the purpose of terminating it or vouching for it in a response.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_db.py`:
```python
def test_init_db_creates_process_state_table_with_one_default_row():
    conn = init_db(":memory:")
    rows = conn.execute("SELECT * FROM process_state").fetchall()
    assert len(rows) == 1
    assert rows[0]["pid"] is None
    assert rows[0]["started_at"] is None
```

`backend/tests/test_process_control.py`:
```python
"""Unit tests for backend.fcc_dashboard.process_control.

These tests launch a real, short-lived, harmless dummy subprocess (a
`python -c "..."` sleep) to verify the detached-launch/liveness/terminate
primitives actually work on this OS -- not FCC itself, which may not be
installed on the machine running the test suite.
"""

import sys
import time

from fcc_dashboard.process_control import (
    find_fcc_server_executable,
    is_process_alive,
    launch_detached,
    terminate_process,
)


def _dummy_executable_args(sleep_seconds: float) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({sleep_seconds})"]


def test_find_fcc_server_executable_returns_none_when_not_on_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert find_fcc_server_executable() is None


def test_find_fcc_server_executable_returns_path_when_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/fcc-server")
    result = find_fcc_server_executable()
    assert result is not None
    assert "fcc-server" in str(result)


def test_launch_detached_starts_a_real_process_and_returns_its_pid():
    pid = launch_detached_for_test(_dummy_executable_args(5))
    try:
        assert is_process_alive(pid)
    finally:
        terminate_process(pid)


def test_is_process_alive_false_for_nonexistent_pid():
    # A PID astronomically unlikely to be in use.
    assert is_process_alive(999_999) is False


def test_terminate_process_stops_a_running_process():
    pid = launch_detached_for_test(_dummy_executable_args(30))
    assert is_process_alive(pid)

    result = terminate_process(pid, timeout=5.0)

    assert result is True
    assert is_process_alive(pid) is False


def test_terminate_process_on_already_stopped_pid_returns_true():
    pid = launch_detached_for_test(_dummy_executable_args(0.1))
    time.sleep(0.5)  # let it exit naturally
    assert is_process_alive(pid) is False

    result = terminate_process(pid, timeout=5.0)

    assert result is True
```

Note: `launch_detached` takes a `Path` to an executable with no argument list (matching `fcc-server`'s own invocation, which needs no args). Since these tests need to launch a Python interpreter WITH arguments (`-c "..."`) for a controllable dummy process, add a small test-only helper in the test file itself:
```python
import subprocess
from pathlib import Path

from fcc_dashboard import process_control


def launch_detached_for_test(args: list[str]) -> int:
    """Test helper: launch a subprocess with arguments, using the same
    detachment approach as launch_detached, for testing against a
    controllable dummy command instead of the no-args fcc-server contract.
    """
    return process_control._launch_detached_args(args)
```
This means `launch_detached(executable: Path) -> int` in `process_control.py` should internally delegate to a slightly more general `_launch_detached_args(args: list[str]) -> int` helper (`launch_detached` calls it with `[str(executable)]`) — write it this way so the test helper above can reuse the real detachment logic instead of reimplementing it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_process_control.py tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fcc_dashboard.process_control'`

- [ ] **Step 3: Write the implementation**

Add the `process_state` table to `backend/src/fcc_dashboard/db.py` (same singleton-row pattern as `collector_state` — `CREATE TABLE IF NOT EXISTS process_state (id INTEGER PRIMARY KEY CHECK (id = 1), pid INTEGER, started_at TEXT)`, seeded with one row on creation via `INSERT OR IGNORE`).

Write `backend/src/fcc_dashboard/process_control.py` to satisfy the contract and pass every test. `uv add psutil` first. Use `psutil.Process(pid)` + `.terminate()` + `.wait(timeout)` + (on `psutil.TimeoutExpired`) `.kill()` for `terminate_process`; catch `psutil.NoSuchProcess` in `is_process_alive` and return `False`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_process_control.py tests/test_db.py -v`
Expected: all pass (7 new process_control tests + 1 new db test).

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/process_control.py backend/src/fcc_dashboard/db.py backend/tests/test_process_control.py backend/tests/test_db.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(backend): add process management primitives and process_state schema"
```

---

### Task 2: `POST /control/start`

**Files:**
- Create: `backend/src/fcc_dashboard/routes_control.py`
- Modify: `backend/src/fcc_dashboard/api.py` (include the new router)
- Modify: `backend/src/fcc_dashboard/dependencies.py` (add `get_fcc_log_path`)
- Test: `backend/tests/test_routes_control.py`

**Interfaces:**
- Consumes: `get_db`, new `get_fcc_log_path` (Task 1's `process_control` module functions, `routes_status._check_fcc_health`, Phase 2's `collector.poll_once`).
- Produces: `POST /control/start` route.

**Contract:**
- Response shape: `{"action": "started" | "already_running" | "executable_not_found", "pid": int | null}`.
- Step order: (1) call `poll_once(db, fcc_log_path)` first (the flush-before-restart safeguard — even for `start`, in case FCC was already running and generating logs before this call), (2) check current health via `_check_fcc_health()`, (3) if already up (`200` response), return `{"action": "already_running", "pid": <persisted pid if any, else null>}` without launching anything, (4) if not up, call `find_fcc_server_executable()` — if `None`, return `{"action": "executable_not_found", "pid": null}` with HTTP 200 (this is a normal, expected outcome for a user who hasn't installed FCC yet, not a server error), (5) otherwise `launch_detached(executable)`, persist the returned PID + current timestamp (via `now_utc_iso8601` from Phase 1) into `process_state`, return `{"action": "started", "pid": <new pid>}`.
- `async def` handler (needed for the `await _check_fcc_health()` call, matching `routes_status.py`'s pattern).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_routes_control.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_routes_control.py -v`
Expected: FAIL (404 / import error)

- [ ] **Step 3: Write the implementation**

Add `get_fcc_log_path` to `backend/src/fcc_dashboard/dependencies.py`, following the exact pattern of `get_pricing_config_path` (env var `FCC_LOG_PATH`, default `Path.home() / ".fcc" / "logs" / "server.log"`, resolved at call time). Write `backend/src/fcc_dashboard/routes_control.py` with the `POST /control/start` handler per the contract, importing `find_fcc_server_executable`/`launch_detached` from `process_control` (import them as module attributes, e.g. `from fcc_dashboard import process_control` then call `process_control.find_fcc_server_executable()`, OR `from fcc_dashboard.process_control import find_fcc_server_executable, launch_detached` at module level — match whichever style the test's `monkeypatch.setattr(routes_control, "find_fcc_server_executable", ...)` expects: since the test patches `routes_control.find_fcc_server_executable` directly, import these as bare names into `routes_control`'s namespace, not accessed via a `process_control.` prefix in the handler body). Include the router in `api.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_routes_control.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/routes_control.py backend/src/fcc_dashboard/api.py backend/src/fcc_dashboard/dependencies.py backend/tests/test_routes_control.py
git commit -m "feat(backend): add POST /control/start"
```

---

### Task 3: `POST /control/stop`

**Files:**
- Modify: `backend/src/fcc_dashboard/routes_control.py` (add the stop handler)
- Modify: `backend/tests/test_routes_control.py` (add tests)

**Interfaces:**
- Consumes: same as Task 2, plus `is_process_alive`/`terminate_process` from `process_control`.
- Produces: `POST /control/stop` route.

**Contract:**
- Response shape: `{"action": "stopped" | "not_running", "pid": int | null}`.
- Step order: (1) flush via `poll_once` (same safeguard as start), (2) read the persisted `pid` from `process_state` — if `NULL` or `is_process_alive(pid)` is `False`, clear `process_state` (set `pid`/`started_at` back to `NULL` — nothing to track anymore either way) and return `{"action": "not_running", "pid": null}`, (3) otherwise `terminate_process(pid)`, clear `process_state`, return `{"action": "stopped", "pid": <the pid that was stopped>}`.
- Plain `def` is fine here UNLESS the flush step or health check needs async — since `poll_once` is sync and this handler doesn't need `_check_fcc_health`, this can be a plain `def` (confirm this against Task 2's actual signature choice; if Task 2 made `routes_control.py`'s module share an event loop concern, keep consistent, but by contract `stop` doesn't need to await anything).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_routes_control.py`:
```python
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

    monkeypatch.setattr(routes_control, "is_process_alive", lambda pid: True)
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

    monkeypatch.setattr(routes_control, "is_process_alive", lambda pid: False)

    response = client.post("/control/stop")

    body = response.json()
    assert body["action"] == "not_running"

    row = db.execute("SELECT pid FROM process_state").fetchone()
    assert row["pid"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_routes_control.py -v -k stop`
Expected: FAIL (404 / AttributeError for the missing route)

- [ ] **Step 3: Write the implementation**

Add the `POST /control/stop` handler to `routes_control.py` per the contract.

- [ ] **Step 4: Run tests to verify they pass, then run the full suite**

Run: `cd backend && uv run pytest tests/test_routes_control.py -v`
Expected: 7 passed (4 from Task 2 + 3 new).

Run: `cd backend && uv run pytest -v`
Expected: all tests across the whole backend pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/routes_control.py backend/tests/test_routes_control.py
git commit -m "feat(backend): add POST /control/stop"
```

## Self-Review Notes

- Spec coverage: PHASE-4-PROCESS-CONTROL.md's three bullets (detached launch/PID/health, flush-before-restart, both control endpoints) are each covered.
- No placeholders: every task has real, complete test code. Contracts + tests style continues from Phases 2-3.
- Type consistency: `launch_detached(executable: Path) -> int` and its test-only `_launch_detached_args` helper share the same underlying detachment logic (Task 1's contract explicitly requires this, to avoid the tests exercising different code than production). `terminate_process`/`is_process_alive` signatures match between Task 1's definitions and Task 3's route-level mocks.
- The "always flush before acting" rule applies to BOTH start and stop, not just stop-then-restart — Task 2's test explicitly checks this for start too, closing a gap the vault's prose (framed around "restart") could be read narrowly.
