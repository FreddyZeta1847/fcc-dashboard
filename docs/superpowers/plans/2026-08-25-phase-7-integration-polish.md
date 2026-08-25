# Phase 7 — Integration & Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The vault's last planned phase — bring backend and frontend
together into a single-process production setup, and do a final
realistic end-to-end pass. Task 1 fixes a real, load-bearing gap found
while scoping this phase (see below) before the rest of the phase can
mean anything.

**Architecture:** Task 1 wires in the collector's background polling
loop — designed since Phase 2, never actually scheduled anywhere. Task 2
adds single-process static file serving (FastAPI serves the frontend's
built assets, replacing the dev-time Vite-proxy split every prior phase
has relied on). Task 3 is a top-level README. Task 4 is a real,
end-to-end smoke test of the finished single-process setup.

**Tech Stack:** Same as every prior phase — no new dependencies planned
(FastAPI already ships `starlette.staticfiles.StaticFiles`).

**Spec:** `vault-fcc-dashboard/plans/PHASE-7-INTEGRATION-POLISH.md`
(scope), `vault-fcc-dashboard/features/BACKEND/BACKEND--collector.md`
(already updated to describe the background loop this plan implements —
read it before Task 1), `BACKEND--technologies.md`,
`vault-fcc-dashboard/features/FRONTEND/FRONTEND--architecture.md` (the
dev-vs-production diagram this plan makes real for the first time),
`vault-fcc-dashboard/Contracts/registry.md` (REG-001, the poll interval).

## Scope note (found gap, fixed here — not a Phase 7 "nice to have")

While scoping this phase, `poll_once` (the collector's core read/upsert
function, built in Phase 2) was found to have **zero callers anywhere
except `routes_control.py`'s start/stop flush-before-action step** — no
background loop, no startup catch-up read, despite both being explicitly
part of the original `BACKEND--collector` design ("runs continuously in
the background... also runs a one-shot catch-up read on backend
startup"). Concretely: right now, `GET /requests`/`GET /stats` never see
new data unless a user happens to click Start or Stop on the Settings
page. This silently breaks the whole project's core "live dashboard"
premise for the normal browsing flow. `db.py`'s own docstring already
anticipated this ("the collector's background polling potentially
sharing this connection") — the WAL + `busy_timeout` groundwork for it
was already there, just never used. Task 1 fixes this. It is a
correctness fix, not scope creep — Task 4's own smoke test cannot
meaningfully pass without it (data would never appear in the running app
without a manual Start/Stop toggle).

## Global Constraints

- **The background collector loop must be safely cancellable.** `lifespan`'s
  shutdown path must cancel the loop's task and await its cancellation
  before closing the DB connection — an uncancelled task still holding a
  reference to a closed connection is a real bug class, not a
  hypothetical one.
- **`poll_once` runs via `run_in_threadpool` on every tick**, matching
  the pattern `routes_control.py`'s async `start_fcc` handler already
  established for calling this same sync, blocking function — never
  called directly inside the async loop body.
- **The poll interval is a parameter, not a hardcoded literal inside the
  loop function** — `run_collector_loop(db, interval: float =
  POLL_INTERVAL_SECONDS)` — specifically so tests can pass a tiny
  interval instead of waiting on the real 5-second value.
- **No new test dependency.** This backend has no `pytest-asyncio`
  installed and this plan doesn't add it — an async scenario test drives
  itself via a plain `def test_...():` function calling `asyncio.run(...)`
  internally, not an `async def test_...():` function (which would need
  a pytest-asyncio plugin to even be collected).
- **Static file serving must never break the app when no frontend build
  exists.** A dev machine that hasn't run `npm run build` yet must still
  be able to run the backend and hit its API routes normally — static
  mounting is conditional on the directory actually existing, not
  assumed.
- **The static mount is registered LAST, after every `app.include_router(...)`
  call**, so it only ever catches requests nothing else matched — this is
  what lets the API surface and the static frontend coexist on one port
  without collision.
- **Relative-URL / same-origin properties established in Phases 5-6b
  must still hold under single-process serving.** In production, frontend
  and backend are now genuinely the same origin (one process, one port)
  — a STRONGER guarantee than dev's Vite-proxy simulation, not a weaker
  one. Task 4's smoke test must actually verify `/control/*` still works
  under this new serving mode, not just assume it does because it worked
  in dev.

---

### Task 1: Backend — continuous background collector loop + startup catch-up read

**Files:**
- Modify: `backend/src/fcc_dashboard/collector.py`
- Modify: `backend/src/fcc_dashboard/api.py`
- Test: `backend/tests/test_collector.py` (extend the existing file)
- Test: `backend/tests/test_api.py` (extend the existing file)

**Interfaces:**
- Consumes: `poll_once(conn, log_path)` (existing, Phase 2),
  `dependencies.get_fcc_log_path()` (existing, Phase 3/4).
- Produces: `collector.run_collector_loop(db: sqlite3.Connection,
  interval: float = POLL_INTERVAL_SECONDS) -> None` — an `async def`
  coroutine intended to be wrapped in `asyncio.create_task(...)` by
  `api.py`'s `lifespan`. Also `collector.POLL_INTERVAL_SECONDS: float =
  5.0` (REG-001).

- [ ] **Step 1: Write the failing collector-loop test**

Append to `backend/tests/test_collector.py` (read the existing file
first for its exact import/fixture style — likely an in-memory
`init_db(":memory:")` and a `tmp_path`-based log file, matching
`poll_once`'s own existing tests):

```python
import asyncio
import contextlib


def test_run_collector_loop_polls_immediately_and_again_after_interval(monkeypatch, tmp_path):
    call_count = 0

    def fake_poll_once(conn, log_path):
        nonlocal call_count
        call_count += 1
        return 0

    monkeypatch.setattr(collector, "poll_once", fake_poll_once)
    monkeypatch.setattr(collector, "get_fcc_log_path", lambda: tmp_path / "server.log")

    db = init_db(":memory:")

    async def run():
        task = asyncio.create_task(collector.run_collector_loop(db, interval=0.01))
        await asyncio.sleep(0.035)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())

    # At interval=0.01s over ~0.035s: one immediate call plus at least
    # two more ticks -- assert loosely (>= 2) to avoid timing flakiness,
    # but this must be strictly more than 1 to prove the loop actually
    # re-polls on a timer, not just once at startup.
    assert call_count >= 2


def test_run_collector_loop_can_be_cancelled_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "poll_once", lambda conn, log_path: 0)
    monkeypatch.setattr(collector, "get_fcc_log_path", lambda: tmp_path / "server.log")
    db = init_db(":memory:")

    async def run():
        task = asyncio.create_task(collector.run_collector_loop(db, interval=0.01))
        await asyncio.sleep(0.02)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert task.cancelled() or task.done()

    asyncio.run(run())
```

(Adjust imports at the top of the file — `import collector` or
`from fcc_dashboard import collector`, matching whatever import style
the rest of the file already uses; `monkeypatch.setattr(collector,
"poll_once", ...)` requires `poll_once` to be called as
`collector.poll_once(...)` — i.e. accessed as a module attribute inside
`run_collector_loop`, not imported as a bare name into that function's
enclosing scope, the same reasoning `routes_status.py`'s
`_check_fcc_health` pattern already established elsewhere in this
codebase for exactly this kind of test-patchability. Same reasoning
applies to `get_fcc_log_path` — call it as
`dependencies.get_fcc_log_path()` or however the module is imported, not
as a bare name, so the monkeypatch above actually takes effect.)

Run: `uv run pytest tests/test_collector.py -v` (from `backend/`) —
expect FAIL (`run_collector_loop` doesn't exist).

- [ ] **Step 2: Implement `run_collector_loop`**

Add to `backend/src/fcc_dashboard/collector.py`:

```python
POLL_INTERVAL_SECONDS = 5.0  # REG-001
```

And an `async def run_collector_loop(db: sqlite3.Connection, interval:
float = POLL_INTERVAL_SECONDS) -> None` that: resolves the current FCC
log path fresh on EVERY iteration (via `dependencies.get_fcc_log_path()`,
called as a module attribute per Step 1's note — resolving it once
outside the loop would go stale if the env var override ever changed
mid-run, and costs nothing to re-check); runs `poll_once` via
`starlette.concurrency.run_in_threadpool` (import it) so a slow catch-up
read never blocks the event loop; then `await asyncio.sleep(interval)`;
repeats forever. The very FIRST thing the loop body does on entry is the
poll call — NOT the sleep — so the "one-shot catch-up read on startup"
requirement is satisfied by construction (the loop's first iteration
IS the catch-up read, not a separate code path). No explicit
`try/except` around the poll call is needed beyond what `poll_once`
itself already guarantees (per its own docstring/tests from Phase 2, it
doesn't raise on malformed lines or truncation) — but DO let
`asyncio.CancelledError` propagate normally on `await asyncio.sleep(...)`
(don't catch it inside the loop) so `task.cancel()` from `lifespan`'s
shutdown actually stops the loop rather than being silently swallowed
and retried.

Run: `uv run pytest tests/test_collector.py -v` — expect PASS.

- [ ] **Step 3: Write the failing lifespan-wiring test**

Append to `backend/tests/test_api.py` (read the existing file first for
its `TestClient(app)` / `app.dependency_overrides` patterns):

```python
def test_lifespan_starts_and_cancels_the_collector_loop(monkeypatch, tmp_path):
    calls = []

    async def fake_run_collector_loop(db, interval=5.0):
        try:
            while True:
                calls.append(1)
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            calls.append("cancelled")
            raise

    monkeypatch.setattr(api.collector, "run_collector_loop", fake_run_collector_loop)
    monkeypatch.setenv("FCC_DASHBOARD_DB_PATH", str(tmp_path / "test.db"))

    with TestClient(app) as client:
        response = client.get("/status")
        assert response.status_code == 200

    # By the time the `with` block exits, lifespan's shutdown path has
    # run -- the loop must have been cancelled, not left dangling.
    assert "cancelled" in calls
    assert len(calls) >= 2  # proves the fake loop actually ran at least once before cancellation
```

(This test patches `api.collector.run_collector_loop` — meaning `api.py`
must import the `collector` module itself, e.g. `from . import collector`,
and call `collector.run_collector_loop(...)`, not `from .collector import
run_collector_loop` as a bare name — same module-attribute-access
reasoning as Step 1, needed here so this test's monkeypatch actually
takes effect on the real app's lifespan.)

Run: `uv run pytest tests/test_api.py -v` — expect FAIL (nothing calls
`collector.run_collector_loop` from `lifespan` yet).

- [ ] **Step 4: Wire the loop into `api.py`'s `lifespan`**

Modify `lifespan` in `backend/src/fcc_dashboard/api.py`: after
`_reconcile_process_state(app.state.db)`, start the loop as a background
task: `collector_task = asyncio.create_task(collector.run_collector_loop(app.state.db))`.
In the `finally` block (after `yield`, before `app.state.db.close()`),
cancel and await it cleanly:

```python
collector_task.cancel()
with contextlib.suppress(asyncio.CancelledError):
    await collector_task
```

Import `collector` as a module (`from . import collector`, per Step 3's
requirement), and `asyncio`/`contextlib` as needed. Update the module's
header comment to document this new startup/shutdown behavior — it's
exactly the kind of non-obvious "why" this project's header-comment
convention exists for (a future reader seeing `asyncio.create_task` in a
`lifespan` needs to know why it's safe and why it's cancelled where it
is).

Run: `uv run pytest tests/test_api.py -v` — expect PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `uv run pytest` (from `backend/`) — expect all tests (139 existing
+ 3 new) to PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/src/fcc_dashboard/collector.py backend/src/fcc_dashboard/api.py backend/tests/test_collector.py backend/tests/test_api.py
git commit -m "feat(backend): schedule the collector's background poll loop (was never wired in)"
```

---

### Task 2: Backend — single-process static file serving

**Files:**
- Create: `backend/src/fcc_dashboard/static.py`
- Modify: `backend/src/fcc_dashboard/api.py`
- Test: `backend/tests/test_static.py`

**Interfaces:**
- Produces: `static.get_static_dir() -> Path` (env-var-overridable,
  matching `dependencies.py`'s established pattern for `FCC_DASHBOARD_DB_PATH`
  etc.) and `static.mount_static_files(app: FastAPI) -> None`.
- Consumes: nothing new. `api.py` calls `mount_static_files(app)` once,
  after every `app.include_router(...)` call.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_static.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fcc_dashboard.static import get_static_dir, mount_static_files


def test_get_static_dir_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FCC_DASHBOARD_STATIC_DIR", str(tmp_path))
    assert get_static_dir() == tmp_path


def test_get_static_dir_defaults_to_frontend_dist_relative_to_repo(monkeypatch):
    monkeypatch.delenv("FCC_DASHBOARD_STATIC_DIR", raising=False)
    result = get_static_dir()
    assert result.parts[-2:] == ("frontend", "dist")


def _make_fake_build(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>fake dashboard</body></html>", encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('fake')", encoding="utf-8")
    return dist


def test_mount_static_files_serves_index_at_root(tmp_path):
    dist = _make_fake_build(tmp_path)
    app = FastAPI()
    mount_static_files(app, static_dir=dist)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert "fake dashboard" in response.text


def test_mount_static_files_serves_assets(tmp_path):
    dist = _make_fake_build(tmp_path)
    app = FastAPI()
    mount_static_files(app, static_dir=dist)
    client = TestClient(app)

    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_mount_static_files_is_a_noop_when_directory_does_not_exist(tmp_path):
    missing = tmp_path / "does-not-exist"
    app = FastAPI()
    mount_static_files(app, static_dir=missing)
    client = TestClient(app)

    # No crash at mount time, and no route was added for "/" -- FastAPI's
    # own 404, not a 500, proves this degraded gracefully.
    response = client.get("/")
    assert response.status_code == 404
```

Run: `uv run pytest tests/test_static.py -v` (from `backend/`) — expect
FAIL (`fcc_dashboard.static` doesn't exist).

- [ ] **Step 2: Implement `static.py`**

```python
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
```

(`static_dir` as an optional parameter, defaulting to `get_static_dir()`,
is what lets Step 1's tests mount a fresh, isolated `FastAPI()` instance
against a fake temp build without needing to monkeypatch a module-level
function — the real call site in `api.py`, Step 3 below, calls it with
no argument, so it resolves the real path.)

`Path(__file__).resolve().parents[3]`: from
`backend/src/fcc_dashboard/static.py`, `parents[0]` is `fcc_dashboard`,
`[1]` is `src`, `[2]` is `backend`, `[3]` is the repo root — verify this
resolves correctly by running the test in Step 1 rather than trusting
the arithmetic; if it's off by one, fix the index, don't add a workaround.

Run: `uv run pytest tests/test_static.py -v` — expect PASS.

- [ ] **Step 3: Wire into `api.py`**

Add `from .static import mount_static_files` and call
`mount_static_files(app)` as the LAST line after every
`app.include_router(...)` call (per the Global Constraints — this must
be registered after the API routes so it only catches what nothing else
matched). No arguments at this real call site — it resolves
`get_static_dir()`'s default (env-var-overridable, else `frontend/dist`
relative to the repo root) on its own.

- [ ] **Step 4: Confirm no regression against the real API routes**

Run: `uv run pytest` (from `backend/`) — expect all tests (139 + 3 from
Task 1 + 5 from this task) to PASS. Specifically confirm no existing
`/status`, `/requests`, `/stats`, `/pricing`, `/control/*`, `/db/*` test
started failing because of the new catch-all mount — if the repo's own
`frontend/dist` doesn't exist at test-run time, `mount_static_files`
should have been a no-op per Step 2's guard; if it DOES exist (e.g. a
build was run earlier in this session), the mount is active but should
still only affect `/` and paths under `/assets`, never any API route's
own prefix — reason through this, and if you see anything surprising,
report it rather than working around it silently.

- [ ] **Step 5: Commit**

```bash
git add backend/src/fcc_dashboard/static.py backend/src/fcc_dashboard/api.py backend/tests/test_static.py
git commit -m "feat(backend): serve the frontend's built static files in single-process mode"
```

---

### Task 3: Top-level README

**Files:**
- Create: `README.md` (repo root)

**Interfaces:** none — a documentation-only task.

- [ ] **Step 1: Write `README.md`**

Cover, concretely (not placeholders — write the actual commands):

1. **What this is** — one or two sentences: a monitoring/analytics
   dashboard for `free-claude-code` (FCC), reading FCC's own log and
   calling its API; a separate, standalone tool that never modifies FCC.
   Prerequisite: FCC itself must already be installed separately (this
   dashboard doesn't install or manage FCC's own installation, only
   starts/stops the `fcc-server` process once FCC is present — link to
   nothing external, just state this in prose).
2. **Setup** — exact commands: `uv sync` from `backend/`; `npm install`
   from `frontend/`.
3. **Development mode** — two terminals: `uv run fcc-dashboard-server`
   (from `backend/`, binds to `127.0.0.1:8000`) and `npm run dev` (from
   `frontend/`, Vite dev server on `127.0.0.1:5173`, proxying API calls
   to the backend — mention this is why dev mode needs BOTH running).
4. **Production / single-process mode** — `npm run build` (from
   `frontend/`, produces `frontend/dist/`), then `uv run
   fcc-dashboard-server` (from `backend/`) — one process, one port
   (`127.0.0.1:8000`), serving both the API and the built frontend.
5. **Data locations** (env-var overridable, name each variable and its
   default): `FCC_DASHBOARD_DB_PATH` (default
   `~/.fcc-dashboard/fcc_dashboard.db`), `FCC_DASHBOARD_PRICING_PATH`
   (default `~/.fcc-dashboard/pricing.json`), `FCC_LOG_PATH` (default
   `~/.fcc/logs/server.log` — FCC's own log, not this dashboard's),
   `FCC_DASHBOARD_STATIC_DIR` (default `frontend/dist` relative to the
   repo — only relevant if running from a location where that relative
   path doesn't resolve correctly).
6. **Security note** — the backend binds to `127.0.0.1` only, by
   construction (`__main__.py`'s `serve()` hardcodes it), never reachable
   from the network.

Keep it factual and to this project's own established tone — no
marketing language, no unverified claims (don't state performance
numbers, don't claim compatibility with FCC versions beyond what's
actually been tested in this codebase, which is v5.14.3 per
`current-task.md`'s own investigation notes if you want to mention a
version — check that file if you want an exact version string, or omit
version specifics rather than guess one).

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add top-level README with setup and run instructions"
```

---

### Task 4: Final end-to-end smoke test

**Files:**
- No new files expected — this task is verification-first; only touch
  something if the verification step surfaces a real bug.

- [ ] **Step 1: Build the frontend for real**

From `frontend/`: `npm run build`. Confirm `frontend/dist/index.html`
and `frontend/dist/assets/*.{js,css}` exist afterward.

- [ ] **Step 2: Craft a realistic sample FCC log fixture**

Write a temp file (e.g. in your scratch/temp directory, NOT inside the
repo) containing several realistic FCC trace-event JSON lines, one per
line, matching the exact shape `log_parser.py` expects (read that file
first for the exact field names/format if you need to double-check —
don't guess). Include, at minimum:
- A complete request: a `provider.request.sent` line followed by a
  matching `provider.response.completed` line (same `request_id`), for
  provider `nvidia_nim`, downstream model `glm-4`, gateway model
  `sonnet`, with real token counts.
- A second complete request for a different provider (e.g.
  `openrouter`, model `kimi-k2`) — so the Usage page's by-provider/
  by-model breakdown has more than one bucket to show.
- A failed request: a `provider.request.sent` followed by a
  `provider.response.transport_error` line (e.g. `http_status: 401`, so
  it shows up as a "stale key" on the Overview status panel).
- One line with a deliberately unparseable/malformed timestamp field on
  an otherwise-valid line, to exercise the `occurred_at_is_estimated`
  fallback path end-to-end, all the way into the Overview/Usage UI's
  visual marker.

- [ ] **Step 3: Start the real single-process server against this fixture**

Set `FCC_LOG_PATH` to the fixture file's path, `FCC_DASHBOARD_DB_PATH`
to a fresh temp DB path (so this doesn't touch any real user data), and
run `uv run fcc-dashboard-server` (from `backend/`) as a background
process, redirecting output to a log file. Wait at least
`POLL_INTERVAL_SECONDS` (5s) plus a small margin (e.g. 7-8s total) for
the background collector loop's first iteration to have ingested the
fixture — this is the real, end-to-end proof that Task 1's fix actually
works, not a mocked substitute.

- [ ] **Step 4: Verify all 4 pages' underlying data, end to end**

Using `curl` against `http://localhost:8000` directly (single process —
no separate frontend dev server or proxy needed this time, since the
backend itself now serves the built frontend):
- `curl -s http://localhost:8000/` — confirm this returns the real built
  `index.html` (check for `<div id="root">` or similar, not a 404).
- `curl -s http://localhost:8000/assets/` — or better, extract the real
  asset filename from the `index.html` response and curl that exact
  path — confirm a built JS/CSS asset is served correctly (non-404,
  correct content type if you want to check headers).
- `curl -s http://localhost:8000/requests` — confirm the fixture's rows
  appear (at least 3 rows: 2 completed, 1 error), including one with
  `"occurred_at_is_estimated": 1`.
- `curl -s "http://localhost:8000/stats?range=all_time"` — confirm
  `total_requests`, `volume_by_provider`, `volume_by_model` reflect the
  fixture data (2 providers, 2 models, non-zero token counts).
- `curl -s http://localhost:8000/status` — confirm the `openrouter` (or
  whichever provider you used for the error case) provider shows
  `"status": "stale_key"`.
- `curl -s -X POST http://localhost:8000/control/start` — confirm this
  responds normally (whatever the real outcome is on this machine —
  `already_running`/`executable_not_found`/`started` are all valid,
  fine outcomes; the point is confirming the endpoint itself works
  correctly when the frontend and backend are the same origin, not
  testing FCC's actual installation state). This specifically verifies
  the Global Constraints' claim that `/control/*` still works correctly
  under single-process serving, not just in dev's proxy-simulated
  same-origin setup.

- [ ] **Step 5: If a browser tool is available**

Additionally open `http://localhost:8000` in a real browser, navigate
through all 4 tabs, and visually confirm the fixture's data renders
correctly, including the estimated-timestamp marker on the one row that
has it. If no browser tool is available in your environment, the curl
evidence above is the required minimum — record exactly what you did
either way.

- [ ] **Step 6: Clean up**

Kill the background server process. Delete the temp DB file and log
fixture (they're outside the repo, in your scratch directory — nothing
to `git` clean up).

- [ ] **Step 7: Report**

Record what you actually observed (the real curl outputs, concretely)
in your report — this is the vault's final "verifiable" acceptance
criterion for the ENTIRE project: "Starting the single production
process and opening the dashboard shows correct data derived from the
sample fixture, across all 4 pages."
