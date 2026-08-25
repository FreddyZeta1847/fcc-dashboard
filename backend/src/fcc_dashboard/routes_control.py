"""
`POST /control/start` -- launch FCC's own gateway server if it isn't running.

Step order, per BACKEND--process-control (all four steps happen on every
call, in this order, no matter which branch below eventually fires):

1. **Flush the collector first** (`poll_once`). Even a `start` call can
   race with an FCC instance that was already running and producing log
   lines before this request arrived -- e.g. dashboard restarted, FCC kept
   running, user then hits "start" out of habit. Draining whatever is
   already on disk before we decide anything keeps `requests` from losing
   those rows to a later truncation/rotation the collector wouldn't be able
   to make sense of retroactively. This call is unconditional: it happens
   before health is even checked, so there is no branch that can skip it.
2. **Check live health** via `routes_status._check_fcc_health()` -- the
   same authoritative reachability probe `GET /status` uses, reused rather
   than duplicated. Deliberately called as `routes_status._check_fcc_health()`
   (through the module object, not imported as a bare name into this
   module's namespace): the test suite patches
   `routes_status._check_fcc_health` in place, and only a call that looks
   the name up on the `routes_status` module *at call time* will observe
   that patch -- a bare `from .routes_status import _check_fcc_health`
   would instead bind this module's own copy of the name at import time,
   before any monkeypatch had a chance to run.
3. **Already up -> no-op.** Returns `"already_running"` with whatever PID
   `process_state` currently has on file (or `null` if none -- FCC can be
   "up" without us having ever launched it ourselves, e.g. the user started
   it by hand outside the dashboard). Nothing is launched in this branch.
4. **Not up -> try to launch.** `find_fcc_server_executable()` /
   `launch_detached()` are imported as bare names (`from .process_control
   import find_fcc_server_executable, launch_detached`) rather than
   accessed via a `process_control.` prefix, matching the pattern Task 1
   established: the test suite patches these two names directly on
   `routes_control` (`monkeypatch.setattr(routes_control,
   "find_fcc_server_executable", ...)`), which only works if the handler
   body resolves the bare name from this module's own globals at call
   time -- exactly what a plain function-body reference does. `None` from
   `find_fcc_server_executable()` means FCC isn't installed on this
   machine -- a normal, expected outcome for a user who hasn't set it up
   yet, not a server error, so it's still a `200` (`"executable_not_found"`,
   `pid: null`). Otherwise `launch_detached()` starts it and its PID plus
   the current timestamp (`now_utc_iso8601`, Phase 1) are persisted into
   `process_state` so a later call can find it again.

`async def` because step 2 awaits `_check_fcc_health()`, matching
`routes_status.py`'s handler.

`POST /control/stop` -- stop the FCC server process this backend is tracking,
if any. Same flush-before-action guarantee as start: `poll_once` is the
first, unconditional statement, before the persisted PID is even read, for
the identical reason (draining whatever's already on disk before any
decision is made). After that:

1. Read the persisted PID from `process_state` (`_persisted_pid`, shared
   with `start_fcc`). If it's `NULL`, or `is_process_alive(pid)` says the
   PID isn't actually alive (stale bookkeeping -- e.g. the process crashed,
   or was killed outside the dashboard), there is nothing to stop: clear
   `process_state` back to `NULL`/`NULL` (nothing left to track either way)
   and return `"not_running"` with `pid: null`.
2. Otherwise call `terminate_process(pid)`, then clear `process_state` the
   same way, and return `"stopped"` with the PID that was just stopped.

`is_process_alive` / `terminate_process` are imported as bare names from
`.process_control`, matching the `find_fcc_server_executable` /
`launch_detached` pattern above -- the test suite patches them directly on
`routes_control` and relies on the handler resolving the bare name from
this module's own globals at call time.

Plain `def`, not `async def`: unlike start, stop never awaits anything --
it doesn't call `_check_fcc_health()`, and `poll_once`/`terminate_process`
are both synchronous.
"""

import sqlite3
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import routes_status
from .collector import poll_once
from .datetime_utils import now_utc_iso8601
from .dependencies import get_db, get_fcc_log_path
from .process_control import (
    find_fcc_server_executable,
    is_process_alive,
    launch_detached,
    terminate_process,
)

router = APIRouter()


class ControlResponse(BaseModel):
    action: Literal["started", "already_running", "executable_not_found"]
    pid: int | None


class StopResponse(BaseModel):
    action: Literal["stopped", "not_running"]
    pid: int | None


def _persisted_pid(db: sqlite3.Connection) -> int | None:
    """Whatever PID `process_state` currently has on file, or `None`."""
    row = db.execute("SELECT pid FROM process_state").fetchone()
    return row["pid"] if row is not None else None


async def _is_fcc_up() -> bool:
    """Same reachability check `GET /status` uses -- see module docstring
    for why this must be a `routes_status.` attribute access, not a bare
    imported name.
    """
    try:
        health_response = await routes_status._check_fcc_health()
        return health_response.status_code == 200
    except httpx.HTTPError:
        return False


@router.post("/control/start", response_model=ControlResponse)
async def start_fcc(
    db: sqlite3.Connection = Depends(get_db),
    fcc_log_path: Path = Depends(get_fcc_log_path),
) -> ControlResponse:
    poll_once(db, fcc_log_path)

    if await _is_fcc_up():
        return ControlResponse(action="already_running", pid=_persisted_pid(db))

    executable = find_fcc_server_executable()
    if executable is None:
        return ControlResponse(action="executable_not_found", pid=None)

    pid = launch_detached(executable)
    db.execute(
        "UPDATE process_state SET pid = ?, started_at = ? WHERE id = 1",
        (pid, now_utc_iso8601()),
    )
    db.commit()

    return ControlResponse(action="started", pid=pid)


def _clear_process_state(db: sqlite3.Connection) -> None:
    """Reset `process_state` back to its untracked baseline (`pid` and
    `started_at` both `NULL`). Called whenever `/control/stop` concludes
    there is nothing left to track -- whether because it just stopped the
    process itself, or because the persisted PID was already stale.
    """
    db.execute(
        "UPDATE process_state SET pid = NULL, started_at = NULL WHERE id = 1"
    )
    db.commit()


@router.post("/control/stop", response_model=StopResponse)
def stop_fcc(
    db: sqlite3.Connection = Depends(get_db),
    fcc_log_path: Path = Depends(get_fcc_log_path),
) -> StopResponse:
    poll_once(db, fcc_log_path)

    pid = _persisted_pid(db)
    if pid is None or not is_process_alive(pid):
        _clear_process_state(db)
        return StopResponse(action="not_running", pid=None)

    terminate_process(pid)
    _clear_process_state(db)
    return StopResponse(action="stopped", pid=pid)
