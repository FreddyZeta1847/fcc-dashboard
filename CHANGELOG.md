# Changelog

All notable changes to FCC Dashboard are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-08-28

### Fixed

- **`/fcc/catalog` was not proxied in development.** The route was added in
  1.1.0 but never added to Vite's dev-server proxy map, so under `npm run dev`
  the request reached Vite instead of the backend and the pricing editor sat
  permanently in its manual-entry fallback. Invisible to every test: the
  production build serves the frontend and API from one origin, so the missing
  entry resolved there, and both the client call and the route were
  individually correct. A guard now cross-checks every fetched route prefix
  against the proxy map.

### Changed

- **The FCC catalog is fetched until it is obtained, then never again.** It had
  its own polling loop, which duplicated a signal already on the wire: `/status`
  is polled every 10s app-wide and already reports whether FCC is up. The
  catalog is FCC's *configuration*, not its running state -- it does not change
  because FCC stopped -- so once held it stays valid. The practical effect is
  that the pricing editor keeps working with FCC stopped, which was always the
  correct behaviour: prices live in this app's own config file, not FCC's.
- **The Database page opens on the `requests` table** instead of an inert
  "select a table" prompt. That table is the reason the page exists; the others
  are single-row bookkeeping.
- Corrected stale Anthropic tier names (`opus`/`sonnet`/`haiku`) in
  `pricing.py`'s docstrings -- the same stale naming that caused 1.1.0's
  price-refresh bug, left sitting in the documentation a reader would trust.

## [1.1.0] - 2026-08-27

### Added

- **Port fallback.** The server prefers port 8000 but now steps to the next free
  port in 8001–8009 instead of failing to start. When the port is held it names
  the holder, and if that holder is an older dashboard server it says so and
  prints the command to stop it — a silent fallback alone would leave a stale
  build serving on 8000 unnoticed. Set `FCC_DASHBOARD_PORT` to pin an exact port
  and skip the fallback.
- **Provider and model pickers in the pricing editor.** `GET /fcc/catalog`
  reads the providers FCC has configured and the models each can serve, so
  prices are set by selecting from FCC's own configuration rather than typing
  two strings from memory. A model not configured in FCC can never produce a
  request row, so FCC's config is the only useful set of choices.
- **Manual price entry as a fallback**, engaging automatically when FCC is
  unreachable and recovering on its own once FCC comes back — the dashboard can
  stop FCC itself, so a Settings page that only worked while FCC ran would be a
  trap.
- **Mismatch flagging.** A configured price pair FCC does not report is marked
  with a warning. Informational only: no data is changed and no row is hidden.
  Nothing is flagged while FCC is unreachable, or for Anthropic tiers, which FCC
  never reports.

### Changed

- **The savings chart is now day-by-day rather than a running total.** A
  cumulative chart only ever slopes up, so a day that saved nothing looked
  almost identical to a good one. Each bar is now that day's own savings, and a
  genuinely zero day is visually distinct from a small-but-nonzero one. The
  range total moved to the header so that figure is not lost.
  `CumulativeSavingsChart` was renamed to `DailySavingsChart`.
- The Vite dev proxy follows `FCC_DASHBOARD_PORT` instead of hardcoding 8000, so
  development mode still works when the backend has fallen back to another port.

### Fixed

- **Price refresh wrote Anthropic tiers to the wrong key.** The merge helper
  tested tier names against a hardcoded `opus`/`sonnet`/`haiku` list. Those tiers
  were later renamed to their full ids (`claude-opus-5` and friends), so the test
  silently stopped matching and an applied refresh wrote tiers into
  `providers.anthropic.*` instead of `anthropic.*`, corrupting the config shape.

### Notes

- The provider string stored in `requests.provider` is FCC's internal per-provider
  log tag (`NIM`, `OLLAMA`), not its provider id (`nvidia_nim`, `ollama`) or
  display name. FCC does not expose these over HTTP, so the dashboard keeps a
  deliberate copy of the mapping in `backend/src/fcc_dashboard/fcc_admin.py`. The
  `/fcc/catalog` response includes `observed_providers` — the provider values
  actually seen in the database — so a drift after an FCC upgrade becomes visible
  rather than silently breaking every price lookup.

## [1.0.0] - 2026-08-27

First release: single-process dashboard over FCC's gateway log — request feed,
usage and savings statistics, pricing configuration with catalog-assisted
refresh, a raw database browser, and FCC process control.

[1.1.1]: https://github.com/FreddyZeta1847/fcc-dashboard/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/FreddyZeta1847/fcc-dashboard/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/FreddyZeta1847/fcc-dashboard/releases/tag/v1.0.0
