"""
Single-process static file serving for FCC Dashboard.

Lets one backend process serve both the API and the built frontend on one
port, replacing the dev-time Vite-proxy split every prior phase relied on.
`get_static_dir` resolves the frontend build directory (env-var-overridable
via `FCC_DASHBOARD_STATIC_DIR`, matching `dependencies.py`'s established
pattern for `FCC_DASHBOARD_DB_PATH` etc.), defaulting to `frontend/dist`
relative to the repo root. `mount_static_files` mounts that directory onto
`app` at `/` with `html=True` (so `/` serves `index.html` and unknown
sub-paths fall back to it, which is what lets a client-side router handle
deep links) -- but only if the directory actually exists. A dev machine
that hasn't run `npm run build` yet must still be able to run the backend
normally, so a missing directory is a silent no-op, never a crash.

`api.py` calls `mount_static_files(app)` with no arguments as the LAST
call after every `app.include_router(...)`, so this catch-all mount only
ever serves paths nothing else matched -- never shadowing a real API
route. The `static_dir` parameter exists so tests can mount a fresh,
isolated `FastAPI()` instance against a fake temp build without touching
the real module-level `app` singleton, which mounts once at import time.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def get_static_dir() -> Path:
    override = os.environ.get("FCC_DASHBOARD_STATIC_DIR")
    return Path(override) if override else DEFAULT_STATIC_DIR


def mount_static_files(app: FastAPI, static_dir: Path | None = None) -> None:
    directory = static_dir if static_dir is not None else get_static_dir()
    if directory.is_dir():
        app.mount("/", StaticFiles(directory=directory, html=True), name="static")
