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
from .process_control import find_fcc_server_executable, launch_detached

router = APIRouter()


class ControlResponse(BaseModel):
    action: Literal["started", "already_running", "executable_not_found"]
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
