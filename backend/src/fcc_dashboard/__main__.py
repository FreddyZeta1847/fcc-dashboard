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

Runnable via `uv run fcc-dashboard-server` (see `backend/pyproject.toml`'s
`[project.scripts]` entry, which points at `serve` below) after `uv sync`,
or directly as `python -m fcc_dashboard`.
"""

import uvicorn

from fcc_dashboard.api import app


def serve() -> None:
    """Start the API server, bound to loopback-only per the security model."""
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    serve()
