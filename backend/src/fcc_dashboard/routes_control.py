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
   Run via `run_in_threadpool` (not called directly) because `poll_once` is
   fully synchronous file I/O + SQLite work -- calling it inline here would
   block the whole event loop for the duration of a large catch-up read,
   stalling every other concurrent request this async handler shares a loop
   with. `stop_fcc` below doesn't need this treatment since it's already a
   plain (threadpool-dispatched) `def`.
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
   it by hand outside the dashboard). If a PID *is* on file, it's only
   returned once `is_tracked_fcc_process` has vouched for it -- otherwise
   the health check says something is up, but we can't say which PID it
   is, so `null` is returned rather than an unverified guess. Nothing is
   launched in this branch.
4. **Not up, but a PID is on file -> resolve it before launching.** The
   health check just said "down," yet `process_state` has a non-NULL PID
   left over from earlier. Two different things can cause that, and they
   get different handling: if `is_tracked_fcc_process` confirms the PID
   is still a live `fcc-server`, it's a health-check-vs-persisted-state
   race -- trust the PID, return `"already_running"` with it, and launch
   nothing. Otherwise it's a stale, dead PID (a crashed `fcc-server`, or
   one a prior `"stop_failed"` response deliberately preserved for a
   retry) -- `process_state` is cleared back to `NULL`/`NULL` (the same
   reset `stop_fcc`'s `_clear_process_state` uses) before falling through
   to step 5. This step exists specifically so a stale non-NULL PID can
   never be mistaken, at step 5, for "a concurrent request beat us": that
   conditional write only matches a genuinely `NULL` row, so without this
   step a stale PID would make it look like a concurrent winner, causing
   the process about to be launched to be killed the instant it starts --
   see `_start_lock` below for the actual concurrent case this protects.
5. **Genuinely nothing on file -> try to launch.**
   `find_fcc_server_executable()` / `launch_detached()` are imported as
   bare names (`from .process_control import find_fcc_server_executable,
   launch_detached`) rather than accessed via a `process_control.` prefix,
   matching the pattern Task 1 established: the test suite patches these
   two names directly on `routes_control` (`monkeypatch.setattr(
   routes_control, "find_fcc_server_executable", ...)`), which only works
   if the handler body resolves the bare name from this module's own
   globals at call time -- exactly what a plain function-body reference
   does. `None` from `find_fcc_server_executable()` means FCC isn't
   installed on this machine -- a normal, expected outcome for a user who
   hasn't set it up yet, not a server error, so it's still a `200`
   (`"executable_not_found"`, `pid: null`). A `launch_detached()` call
   that raises `OSError` (e.g. the executable vanished between the lookup
   and the launch, or isn't actually executable) is caught and reported
   as `"launch_failed"`, `pid: null`, also `200` -- not an opaque 500.
   Otherwise `launch_detached()` starts it and its PID plus the current
   timestamp (`now_utc_iso8601`, Phase 1) are persisted into
   `process_state` via a conditional `UPDATE ... WHERE id = 1 AND pid IS
   NULL` so a later call can find it again -- see `_start_lock` below for
   why that conditional write exists.

`async def` because step 2 awaits `_check_fcc_health()`, matching
`routes_status.py`'s handler.

A module-level `asyncio.Lock` (`_start_lock`) is held across this handler's
entire body. Without it, two concurrent `POST /control/start` requests can
both `await` at step 1/2, both observe "not running," and both launch a
process -- only one PID gets persisted, orphaning the other. The lock
serializes the whole check-then-launch sequence so only one request at a
time can be mid-flight through it. The conditional persist
(`WHERE id = 1 AND pid IS NULL`) is defense in depth on top of the lock,
not a replacement for it: if the write still finds a PID already present
(shouldn't happen with the lock, but the contract doesn't rely on that),
the process we just launched is terminated to avoid leaving it orphaned,
and `"already_running"` is returned with the PID that beat us to it. Step
4 above is what makes this a correct signal to act on: it guarantees the
row is genuinely `NULL` by the time this write runs (a stale PID was
already cleared there), so a `rowcount == 0` here can only mean the one
case it's meant to catch -- a second request's write landing in between
-- never a leftover stale PID.

Note: `_start_lock` does NOT cover a concurrent start-vs-stop race. `start`
runs on the asyncio event loop; `stop` is a plain `def` and therefore runs
in Starlette's threadpool -- two different execution contexts, so one
`asyncio.Lock` can't serialize both. This gap is accepted as benign: the
worst case is `stop` clearing the PID `start` just persisted (or vice
versa in timing), which degrades to a "lost tracking" case -- a PID that
existed but is no longer recorded -- not a wrong-process kill. That
degraded case is exactly what `is_tracked_fcc_process` and the startup
reconciliation step in `api.py`'s `lifespan` already exist to make safe:
neither ever acts on a PID without first confirming it's still plausibly
`fcc-server`.

`POST /control/stop` -- stop the FCC server process this backend is tracking,
if any. Same flush-before-action guarantee as start: `poll_once` is the
first, unconditional statement, before the persisted PID is even read, for
the identical reason (draining whatever's already on disk before any
decision is made). After that:

1. Read the persisted PID from `process_state` (`_persisted_pid`, shared
   with `start_fcc`). If it's `NULL`, or `is_tracked_fcc_process(pid)` says
   the PID isn't alive *or* isn't actually `fcc-server` any more (stale
   bookkeeping -- the process crashed, was killed outside the dashboard, or
   -- the critical case -- the OS reused this PID for an unrelated process
   after a reboot), there is nothing safe to stop: clear `process_state`
   back to `NULL`/`NULL` (nothing left to track either way) and return
   `"not_running"` with `pid: null`. This is deliberate: an alive-but-wrong
   process is treated identically to "not running," never terminated. This
   also covers the case where FCC genuinely is running but wasn't started
   by this dashboard (a PID we never persisted, or a since-reused one) --
   the safety behavior and the "we don't own this instance" behavior are
   the same code path on purpose.
2. Otherwise call `terminate_process(pid)`. If it returns `False` (the OS
   couldn't be confirmed to have actually killed it), `process_state` is
   left untouched -- the PID stays tracked so a retry remains possible --
   and `"stop_failed"` is returned rather than silently reporting success
   on a process that might still be running. Only once `terminate_process`
   confirms the stop does `process_state` get cleared and `"stopped"`
   returned with the PID that was just stopped.

`is_tracked_fcc_process` / `terminate_process` are imported as bare names
from `.process_control`, matching the `find_fcc_server_executable` /
`launch_detached` pattern above -- the test suite patches them directly on
`routes_control` and relies on the handler resolving the bare name from
this module's own globals at call time.

Plain `def`, not `async def`: unlike start, stop never awaits anything --
it doesn't call `_check_fcc_health()`, and `poll_once`/`terminate_process`
are both synchronous.

Both routes sit behind `reject_cross_site_requests`, applied at the router
level (`APIRouter(dependencies=[...])`) so it can never be forgotten on a
future third endpoint added to this router. See that function's own
docstring for why: a "CORS simple request" (a same-origin-looking POST with
no custom headers) needs no preflight, so any webpage the user has open in
another tab could otherwise silently trigger start/stop against this
locally-running backend.
"""

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import routes_status
from .collector import poll_once
from .datetime_utils import now_utc_iso8601
from .dependencies import get_db, get_fcc_log_path
from .process_control import (
    find_fcc_server_executable,
    is_tracked_fcc_process,
    launch_detached,
    terminate_process,
)

logger = logging.getLogger(__name__)


def reject_cross_site_requests(request: Request) -> None:
    """Reject requests whose Sec-Fetch-Site header indicates they originated
    from a different site than this API -- defends the process-control
    endpoints against a malicious page silently POSTing to them while the
    user has this dashboard's backend running locally. Non-browser clients
    (curl, the dashboard's own frontend dev server) send no such header and
    pass through unaffected.
    """
    site = request.headers.get("sec-fetch-site")
    if site not in (None, "same-origin", "none"):
        raise HTTPException(status_code=403, detail="cross-site request rejected")


router = APIRouter(dependencies=[Depends(reject_cross_site_requests)])

# Serializes start_fcc's entire check-then-launch body against concurrent
# `POST /control/start` calls -- see module docstring for why, and for the
# accepted start-vs-stop gap this lock does NOT cover.
_start_lock = asyncio.Lock()


class ControlResponse(BaseModel):
    action: Literal[
        "started", "already_running", "executable_not_found", "launch_failed"
    ]
    pid: int | None


class StopResponse(BaseModel):
    action: Literal["stopped", "not_running", "stop_failed"]
    pid: int | None


def _persisted_pid(db: sqlite3.Connection) -> int | None:
    """Whatever PID `process_state` currently has on file, or `None`."""
    row = db.execute("SELECT pid FROM process_state WHERE id = 1").fetchone()
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
    async with _start_lock:
        await run_in_threadpool(poll_once, db, fcc_log_path)

        if await _is_fcc_up():
            pid = _persisted_pid(db)
            if pid is not None and not is_tracked_fcc_process(pid):
                pid = None
            return ControlResponse(action="already_running", pid=pid)

        stale_pid = _persisted_pid(db)
        if stale_pid is not None:
            if is_tracked_fcc_process(stale_pid):
                # Health check just said "down" but the persisted PID
                # still checks out as a live fcc-server -- a
                # health-check-vs-persisted-state race. Trust the PID
                # rather than launching a second instance.
                return ControlResponse(action="already_running", pid=stale_pid)
            # Dead PID left behind by a crash, or by a stop_failed retry
            # that deliberately preserved it -- not the "a concurrent
            # request beat us" case the conditional UPDATE below exists
            # for. Clear it now so that check stays a correct
            # compare-and-swap against a genuinely NULL row instead of
            # misreading this stale PID as a concurrent winner and
            # self-killing the process launched below.
            _clear_process_state(db)

        executable = find_fcc_server_executable()
        if executable is None:
            return ControlResponse(action="executable_not_found", pid=None)

        try:
            pid = launch_detached(executable)
        except OSError as exc:
            logger.warning("Failed to launch %s: %s", executable, exc)
            return ControlResponse(action="launch_failed", pid=None)

        cursor = db.execute(
            "UPDATE process_state SET pid = ?, started_at = ? "
            "WHERE id = 1 AND pid IS NULL",
            (pid, now_utc_iso8601()),
        )
        db.commit()

        if cursor.rowcount == 0:
            # Defense in depth (the lock above should make this
            # unreachable in practice): someone else's PID is already
            # persisted, so don't orphan the process we just launched.
            terminate_process(pid)
            return ControlResponse(
                action="already_running", pid=_persisted_pid(db)
            )

        return ControlResponse(action="started", pid=pid)


def _clear_process_state(db: sqlite3.Connection) -> None:
    """Reset `process_state` back to its untracked baseline (`pid` and
    `started_at` both `NULL`). Called whenever `/control/stop` concludes
    there is nothing left to track -- whether because it just stopped the
    process itself, or because the persisted PID was already stale or
    unverifiable -- and also by `start_fcc` when it finds a stale,
    untracked PID on file that needs clearing before it can launch (see
    step 4 in the module docstring).
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
    if pid is None or not is_tracked_fcc_process(pid):
        _clear_process_state(db)
        return StopResponse(action="not_running", pid=None)

    if not terminate_process(pid):
        # Termination could not be confirmed -- keep the PID tracked so a
        # retry is possible, rather than reporting a false "stopped" and
        # losing the ability to act on this process again.
        return StopResponse(action="stop_failed", pid=pid)

    _clear_process_state(db)
    return StopResponse(action="stopped", pid=pid)
