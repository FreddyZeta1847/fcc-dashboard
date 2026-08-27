"""
Server entrypoint for FCC Dashboard's backend.

This is the one place in the codebase that actually calls `uvicorn.run(...)`.
`BACKEND--security.md` documents binding to `127.0.0.1` only, never
`0.0.0.0`, as "enforced at startup, not just convention" -- `serve()` below
is that enforcement: it hardcodes `host="127.0.0.1"` so the API is
unreachable from the network by construction, regardless of what any future
caller passes or forgets to pass.

Port 8000 is used deliberately, not FCC's own port: FCC itself listens on
`127.0.0.1:8082` (see `routes_status.py`'s health check), so this dashboard
backend needed its own free port to avoid colliding with it.

8000 is the preferred port, not a fixed one. If something already holds it,
`ports.resolve_port()` names the holder and steps to the next free port in
8001-8009 rather than failing to start -- most often the holder turns out to be
an orphaned dashboard server from an earlier session, which is worth saying out
loud so a stale build is never mistaken for the current one. Set
`FCC_DASHBOARD_PORT` to pin an exact port and skip the fallback entirely.
Note that only the *port* moves: the loopback host below stays hardcoded.

Runnable via `uv run fcc-dashboard-server` (see `backend/pyproject.toml`'s
`[project.scripts]` entry, which points at `serve` below) after `uv sync`,
or directly as `python -m fcc_dashboard`.
"""

import sys

import uvicorn

from fcc_dashboard.api import app
from fcc_dashboard.ports import NoFreePortError, resolve_port


def serve() -> None:
    """Start the API server, bound to loopback-only per the security model."""
    try:
        port, notice = resolve_port()
    except (NoFreePortError, ValueError) as exc:
        # A bad FCC_DASHBOARD_PORT or a fully occupied range. Both are the
        # user's to fix, so report plainly instead of dumping a traceback.
        print(f"fcc-dashboard: {exc}", file=sys.stderr)
        raise SystemExit(1) from None

    if notice:
        print(notice, file=sys.stderr)

    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    serve()
