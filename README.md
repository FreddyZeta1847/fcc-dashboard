# fcc-dashboard

A monitoring and analytics dashboard for [free-claude-code](https://github.com/Alishahryar1/free-claude-code)
(FCC), a proxy tool that routes Claude Code requests to third-party model
providers. This dashboard reads FCC's own log file and calls FCC's own HTTP
API to show live status, usage, and cost data — it is a separate, standalone
tool that never modifies FCC or its installation. Data on screen updates on
a background ~5 second polling interval, not instantly — a new FCC request
can take up to a few seconds to show up.

FCC itself must already be installed separately; this dashboard does not
install or manage FCC's installation. The only thing it does to FCC's
process is start and stop the `fcc-server` process once FCC is already
present on the machine.

### Process control

Starting FCC from the dashboard launches it as a real, fully detached
background process — it keeps running even after you close the dashboard
or stop its own backend. Use the dashboard's Stop control (or your own
OS's process tools) to actually stop it.

On Windows, stopping FCC through the dashboard is always a hard kill —
`fcc-server` gets no chance to shut down gracefully or flush its own state
before being terminated.

Development and manual testing so far has been done against FCC v5.14.3.
Other FCC versions have not been tested.

## Setup

Backend (from `backend/`):

```bash
uv sync
```

Frontend (from `frontend/`):

```bash
npm install
```

## Development mode

Development mode runs two processes in two terminals: the backend API
server and the Vite dev server. The Vite dev server proxies API calls to
the backend, so both must be running for the dashboard to work.

Terminal 1 — backend (from `backend/`):

```bash
uv run fcc-dashboard-server
```

This binds to `127.0.0.1:8000`.

Terminal 2 — frontend (from `frontend/`):

```bash
npm run dev
```

This starts the Vite dev server on `127.0.0.1:5173`. Open that address in
a browser during development.

## Production / single-process mode

For a single-process setup, build the frontend first, then start the
backend, in that order. The backend serves both the API and the built
frontend from one process on one port, but it only decides whether it has
a build to serve once, at its own startup — a backend that's already
running will not pick up a build that finishes after it started. If you
rebuild the frontend while the backend is already running, restart the
backend afterward.

Build the frontend (from `frontend/`):

```bash
npm run build
```

This produces `frontend/dist/`.

Start the backend (from `backend/`):

```bash
uv run fcc-dashboard-server
```

Open `http://127.0.0.1:8000` — the backend serves the API and the built
frontend together on that one port.

## Data locations

The backend stores its data and reads FCC's log from the following
locations. Each has an environment variable to override the default.

| Variable | Default | What it is |
|---|---|---|
| `FCC_DASHBOARD_DB_PATH` | `~/.fcc-dashboard/fcc_dashboard.db` | This dashboard's own SQLite database (collected history). |
| `FCC_DASHBOARD_PRICING_PATH` | `~/.fcc-dashboard/pricing.json` | This dashboard's editable pricing/cost config. |
| `FCC_LOG_PATH` | `~/.fcc/logs/server.log` | FCC's own log file — this is FCC's data, not this dashboard's, read-only. |
| `FCC_DASHBOARD_STATIC_DIR` | `frontend/dist` (relative to the repo root) | Where the backend looks for the built frontend in single-process mode. Only needs overriding if the backend is run from a location where that relative path doesn't resolve correctly. |

## Security

The backend binds to `127.0.0.1` only. This is hardcoded in `serve()` in
`backend/src/fcc_dashboard/__main__.py`, not just a convention, so the API
is never reachable from the network, regardless of how it's started.
