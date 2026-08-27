"""
Port selection for the FCC Dashboard backend.

`serve()` in `__main__.py` used to hardcode port 8000 and die if anything
already held it. The failure was opaque: uvicorn calls `sys.exit()` internally
when the bind fails (see `uvicorn/server.py`'s `startup()`), so `uvicorn.run()`
raises nothing a caller could catch and turn into a useful message. The only
place to be helpful is *before* that call -- which is what this module is for.

It answers three questions, in order:

1. Is the wanted port free?   -- `is_port_free()`, a real bind attempt.
2. If not, who is holding it? -- `describe_port_holder()`, via `psutil`.
3. Where should we go instead? -- `find_free_port()`, a bounded scan.

Naming the holder matters as much as the fallback. The common case is an
*orphaned dashboard server from an earlier session*; silently sliding to the
next port would leave that stale process running and serving the old build, and
the user would have no hint they were testing the wrong thing. So when the
holder is one of our own servers, `format_conflict_notice()` says so loudly and
prints the command to stop it.

Everything here binds loopback only, matching the security model documented in
`__main__.py` and `BACKEND--security.md`: the port is negotiable, the host is not.
"""

from __future__ import annotations

import os
import socket
import sys
from dataclasses import dataclass
from datetime import datetime

import psutil

#: The port we prefer, and the base of the fallback scan.
DEFAULT_PORT = 8000

#: How many ports to try, counting from the one first requested. Ten keeps the
#: scan well clear of 8082, which is FCC's own port (see `routes_status.py`).
PORT_SCAN_SPAN = 10

#: Set this to pin an exact port. An explicit choice disables the fallback scan.
PORT_ENV_VAR = "FCC_DASHBOARD_PORT"

#: Loopback only, never 0.0.0.0 -- see the module docstring.
LOOPBACK_HOST = "127.0.0.1"

#: Substrings that identify one of *our* server processes. The console script is
#: `fcc-dashboard-server`; running via `python -m fcc_dashboard` shows the
#: underscored package name instead, so both spellings count.
_OWN_SERVER_MARKERS = ("fcc-dashboard-server", "fcc_dashboard")

#: psutil raises these when a process dies mid-inspection or belongs to another
#: user. Every lookup below is best-effort: a missing detail degrades the
#: message, it never breaks startup.
_PSUTIL_LOOKUP_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
    ValueError,
)


class NoFreePortError(RuntimeError):
    """Every port in the scanned range was occupied."""


@dataclass(frozen=True)
class PortHolder:
    """What little we could learn about the process holding a port."""

    pid: int
    name: str
    started_at: datetime | None
    is_own_server: bool


def is_port_free(port: int, host: str = LOOPBACK_HOST) -> bool:
    """True if `port` can be bound on `host` right now.

    Deliberately does NOT set `SO_REUSEADDR`. On Windows that option lets a
    socket bind a port another socket is *already* bound to, so setting it here
    would make an occupied port probe as free -- the exact opposite of what this
    function is for. Python's default socket leaves it off; keep it that way.

    On POSIX the reverse, milder inaccuracy exists: asyncio *does* set
    `SO_REUSEADDR`, so a port sitting in `TIME_WAIT` probes as busy even though
    uvicorn could have bound it. The cost is one needless step to the next port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(
    start: int = DEFAULT_PORT,
    span: int = PORT_SCAN_SPAN,
    host: str = LOOPBACK_HOST,
) -> int:
    """First free port in `[start, start + span)`.

    Bounded on purpose: if the whole range is taken, something is wrong enough
    that failing loudly beats scanning on into unrelated services' ports.
    """
    for port in range(start, start + span):
        if is_port_free(port, host):
            return port
    raise NoFreePortError(
        f"No free port in range {start}-{start + span - 1}. "
        f"Close whatever is holding them, or set {PORT_ENV_VAR} "
        "to a specific port."
    )


def _listening_pid(port: int) -> int | None:
    """PID of the process listening on `port`, or None if it cannot be told.

    Address is not filtered: a listener on `0.0.0.0:<port>` blocks
    `127.0.0.1:<port>` just as effectively as a loopback one, and both are
    equally worth reporting.
    """
    try:
        connections = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, PermissionError, OSError):
        # Enumerating sockets needs elevation on some platforms (notably
        # macOS). Not fatal -- we just cannot name the holder.
        return None

    for conn in connections:
        if conn.status != psutil.CONN_LISTEN or conn.pid is None:
            continue
        if conn.laddr and conn.laddr.port == port:
            return conn.pid
    return None


def _has_own_server_marker(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in _OWN_SERVER_MARKERS)


def _looks_like_own_server(process: psutil.Process) -> bool:
    """True if `process` looks like another instance of this dashboard server.

    Mirrors the cascading probe in `process_control.is_tracked_fcc_process()`:
    check the process name, then the executable path, then the full command
    line, because on Windows the console-script shim and the interpreter carry
    the marker in different places. Each step is independent -- a permission
    error on one does not stop the next from answering.
    """
    try:
        if _has_own_server_marker(process.name()):
            return True
    except _PSUTIL_LOOKUP_ERRORS:
        pass

    try:
        if _has_own_server_marker(process.exe()):
            return True
    except _PSUTIL_LOOKUP_ERRORS:
        pass

    try:
        if any(_has_own_server_marker(arg) for arg in process.cmdline()):
            return True
    except _PSUTIL_LOOKUP_ERRORS:
        pass

    return False


def _process_name(process: psutil.Process) -> str:
    try:
        return process.name() or "unknown process"
    except _PSUTIL_LOOKUP_ERRORS:
        return "unknown process"


def _process_started_at(process: psutil.Process) -> datetime | None:
    try:
        return datetime.fromtimestamp(process.create_time())
    except (OSError, OverflowError, *_PSUTIL_LOOKUP_ERRORS):
        return None


def describe_port_holder(port: int) -> PortHolder | None:
    """Best-effort description of whoever holds `port`, or None if unknowable."""
    pid = _listening_pid(port)
    if pid is None:
        return None

    try:
        process = psutil.Process(pid)
    except _PSUTIL_LOOKUP_ERRORS:
        # It exited between the socket scan and here.
        return None

    return PortHolder(
        pid=pid,
        name=_process_name(process),
        started_at=_process_started_at(process),
        is_own_server=_looks_like_own_server(process),
    )


def _kill_hint(pid: int) -> str:
    if sys.platform.startswith("win"):
        return f"taskkill /PID {pid} /F"
    return f"kill {pid}"


def _holder_identity(holder: PortHolder) -> str:
    if holder.started_at is None:
        return f"PID {holder.pid}"
    return f"PID {holder.pid}, started {holder.started_at:%Y-%m-%d %H:%M}"


def format_conflict_notice(
    holder: PortHolder | None, requested: int, chosen: int
) -> str:
    """The message shown when `requested` was busy and we moved to `chosen`.

    Three shapes, because the right reaction differs. Our own stale server is
    worth alarm and a stop command -- it is probably serving an older build. An
    unrelated program is not our business, so it gets one plain line and no
    advice about killing a process we do not own.
    """
    lines: list[str] = []

    if holder is None:
        lines.append(f"!  Port {requested} is in use (owner could not be identified)")
    elif holder.is_own_server:
        lines.append(f"!  Port {requested} is taken by an OLDER fcc-dashboard server")
        lines.append(f"   ({_holder_identity(holder)})")
        lines.append(f"   Stop it with:  {_kill_hint(holder.pid)}")
        lines.append("")
    else:
        lines.append(
            f"!  Port {requested} is in use by {holder.name} (PID {holder.pid})"
        )

    lines.append(f"-> Starting on port {chosen} instead")
    lines.append(f"   http://localhost:{chosen}")
    return "\n".join(lines)


def _parse_port_override(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        raise ValueError(f"{PORT_ENV_VAR} must be a number, got {raw!r}.") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"{PORT_ENV_VAR} must be between 1 and 65535, got {port}.")
    return port


def resolve_port() -> tuple[int, str | None]:
    """Pick the port to serve on, plus a notice to print if we had to move.

    Returns `(port, notice)` where `notice` is None on the quiet common path.
    An explicit `FCC_DASHBOARD_PORT` is taken at face value and never falls back
    -- if you named a port, a silent switch to a different one would be a worse
    surprise than failing to start.
    """
    override = os.environ.get(PORT_ENV_VAR, "").strip()
    if override:
        return _parse_port_override(override), None

    if is_port_free(DEFAULT_PORT):
        return DEFAULT_PORT, None

    holder = describe_port_holder(DEFAULT_PORT)
    chosen = find_free_port(DEFAULT_PORT + 1, PORT_SCAN_SPAN - 1)
    return chosen, format_conflict_notice(holder, DEFAULT_PORT, chosen)
