"""
Process management primitives for FCC Dashboard's process control feature.

This module owns the low-level, OS-facing half of BACKEND--process-control:
finding the `fcc-server` executable on PATH, launching it as a detached
background process (one that keeps running after our own process exits, and
that doesn't hold a pipe open back to us), checking whether a given PID is
currently alive, and stopping a PID gracefully (falling back to a force-kill
if it doesn't cooperate). `db.py`'s `process_state` table is the bookkeeping
half: it remembers which PID (if any) *we* started, across our own restarts.

None of the functions here raise on the "not found" / "already gone" cases
they're specifically designed to handle -- callers (the routes layer) can
treat a `None` or `False` return as the normal, expected outcome rather than
writing exception handlers for routine states.

Important caveat, called out in BACKEND--process-control: `is_process_alive`
only answers "does a process with this PID exist right now" -- it has no way
to confirm that PID is *still* the FCC server we launched, since the OS
reuses PIDs after a reboot. This module's return values are therefore
advisory, not authoritative; the routes layer treats an actual `/health`
probe against the running server as the source of truth for "is FCC really
up," and only uses `process_state` / `is_process_alive` to decide whether a
process even exists to check.

`launch_detached(executable)` and the test-only-facing `_launch_detached_args
(args)` share one code path deliberately: `launch_detached` is just
`_launch_detached_args([str(executable)])`. `fcc-server` itself takes no
arguments, but the test suite needs to launch a controllable dummy process
(a `python -c "..."` sleep, which does take arguments) to exercise the real
launch/liveness/terminate primitives without depending on `fcc-server` being
installed on the machine running the tests. Splitting the argument list out
means the tests exercise the exact same detachment flags/behavior that
`launch_detached` uses in production, instead of a second implementation
that could quietly drift from it.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import psutil


def find_fcc_server_executable() -> Path | None:
    """Look up the `fcc-server` executable on PATH.

    Thin wrapper around `shutil.which`. Returns `None` (never raises) if
    `fcc-server` isn't found on PATH.
    """
    found = shutil.which("fcc-server")
    if found is None:
        return None
    return Path(found)


def _launch_detached_args(args: list[str]) -> int:
    """Launch `args` as a fully detached background process; return its PID.

    "Detached" means two things, both required so the child survives and
    behaves correctly after our own process exits:

    - No inherited stdin/stdout/stderr pipes. We redirect all three to
      `subprocess.DEVNULL` rather than leaving them open back to us --
      an unread pipe has a limited OS buffer, and once we exit (and stop
      reading it) a chatty child can block forever trying to write to a
      full pipe that nobody drains anymore.
    - No dependency on our process/console for its lifetime or signals.
      The platform-specific flags below detach the child from our console
      (Windows) or session (POSIX) so it keeps running independently of us
      and isn't killed or signaled just because we exit.

    Windows: `DETACHED_PROCESS` starts the child with no console of its
    own (it doesn't inherit or attach to ours), and `CREATE_NEW_PROCESS_GROUP`
    puts it in its own process group so console control signals (e.g.
    Ctrl+C) delivered to our process group don't also reach the child.

    POSIX: `start_new_session=True` is the equivalent -- it calls `setsid()`
    for the child, giving it a new session (and process group) detached from
    our controlling terminal, so it isn't sent SIGHUP/SIGINT along with us.

    Returns the child's PID immediately; does not wait for the child to do
    anything.
    """
    popen_kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }

    if sys.platform == "win32":
        popen_kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(args, **popen_kwargs)
    return process.pid


def launch_detached(executable: Path) -> int:
    """Launch `executable` (no arguments) as a detached process; return its PID.

    `fcc-server` takes no arguments, so this is just `_launch_detached_args`
    called with a single-element argument list. See `_launch_detached_args`
    for the detachment behavior.
    """
    return _launch_detached_args([str(executable)])


def is_process_alive(pid: int) -> bool:
    """Return whether a process with `pid` currently exists and is running.

    Advisory only -- see this module's docstring for the PID-reuse caveat.
    Never raises: an invalid, negative, or nonexistent PID simply yields
    `False`.
    """
    try:
        return psutil.Process(pid).is_running()
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return False


def terminate_process(pid: int, timeout: float = 5.0) -> bool:
    """Stop the process at `pid`, gracefully first, forcibly if needed.

    - If `pid` isn't alive already, returns `True` immediately -- there is
      nothing to stop.
    - Otherwise sends a graceful terminate signal (`SIGTERM` on POSIX,
      `TerminateProcess` via `psutil` on Windows) and waits up to `timeout`
      seconds for the process to exit on its own.
    - If it's still alive after that, force-kills it (`SIGKILL` / Windows
      equivalent) and waits up to `timeout` seconds more for the kill to
      take effect.

    Returns `True` once the process is confirmed stopped, by either method.
    Returns `False` only if a stop was attempted and the process is
    somehow still alive afterward -- this should be rare-to-impossible
    given the force-kill fallback, but the contract allows for a `False`
    return here rather than raising, since an OS-level termination failure
    shouldn't crash the caller.
    """
    if not is_process_alive(pid):
        return True

    try:
        process = psutil.Process(pid)
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except psutil.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=timeout)
            except psutil.TimeoutExpired:
                pass
    except psutil.NoSuchProcess:
        return True

    return not is_process_alive(pid)
