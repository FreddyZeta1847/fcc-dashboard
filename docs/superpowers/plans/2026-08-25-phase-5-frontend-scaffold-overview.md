# Phase 5 — Frontend Scaffold & Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up FRONTEND's locked stack decisions for real (TanStack Query,
Recharts, Tailwind already present) and build the first real page — Overview —
against the actual running Phase 3/4 backend API. First true end-to-end slice
of the whole project: real FCC log data, through the collector, through the
API, into a rendered browser UI.

**Architecture:** React + TypeScript function components, TanStack Query for
all data fetching (no other client state library — React Query's cache is the
only cache, per `FRONTEND--caching`), Tailwind for styling. One page
(`Overview`) composed of three independent panels, each backed by its own
query hook. Vitest + React Testing Library for tests, mocking at the
`fetch` boundary so component tests exercise the same code path production
uses.

**Tech Stack:** React 19, TypeScript, Vite 8 (already scaffolded, Phase 0),
`@tanstack/react-query` v5, `recharts` (installed now per
`FRONTEND--technologies`, not yet used — Phase 6 owns the charts), Tailwind
CSS v4 (already scaffolded), Vitest + `@testing-library/react` +
`@testing-library/jest-dom` + `jsdom` (new test tooling this phase — no
frontend test framework has been chosen before now).

**Spec:** `vault-fcc-dashboard/plans/PHASE-5-FRONTEND-SCAFFOLD-OVERVIEW.md`
(scope), `vault-fcc-dashboard/features/FRONTEND/FRONTEND--technologies.md`,
`FRONTEND--architecture.md`, `FRONTEND--overview.md`, `FRONTEND--resilience.md`,
`FRONTEND--caching.md`, `vault-fcc-dashboard/features/BACKEND/BACKEND--api.md`
(the exact response shapes this phase's UI renders).

## Global Constraints

- **Relative URLs only, everywhere in the API client.** Never build an
  absolute `http://localhost:8000/...` URL. Fetch calls use paths like
  `/status`, `/stats`, `/requests` — relative to whatever origin served the
  page. This is not just style: it is what makes Phase 4's `Sec-Fetch-Site`
  same-origin guard on `/control/*` work correctly. In dev, Vite's proxy
  (added in Task 1) forwards these paths to the real backend at
  `localhost:8000`, but the *browser* only ever sees requests to its own
  Vite origin (`localhost:5173`) — so the browser sets
  `Sec-Fetch-Site: same-origin`, which the backend's existing allow-list
  (`None` / `same-origin` / `none`) already accepts, and Vite's proxy
  forwards that header through unchanged. In production, `BACKEND` serves
  the built frontend itself (`FRONTEND--architecture`'s single-process
  serving), so the page and the API are already the same origin. Using an
  absolute URL anywhere would defeat both of these and reintroduce the gap
  `current-task.md` carried forward from Phase 4.
- **`GET /status` never 500s by the backend's own documented contract**
  (`routes_status.py`'s docstring: "both best-effort ... meant to degrade
  gracefully rather than 500"). So any failure at all fetching `/status` —
  a network error, a connection refused, a non-2xx response — means the
  *dashboard's own backend* isn't reachable, never "FCC is down" (that
  case is represented inside a successful response, as
  `fcc_status: "down"`). Every task that touches status-query error
  handling must preserve this distinction — see `FRONTEND--resilience`.
- **Money-saved is never a bare number defaulting to 0.** `GET /stats`
  returns `total_savings: number | null` — `null` means "no pricing config
  has ever been written," a fact distinct from "everything summed to
  zero." The UI must render these two cases differently (see Task 4).
- **`occurred_at_is_estimated` is a SQLite integer (`0`/`1`) in the raw API
  response**, not a JSON boolean — `GET /requests`' `results` field is
  `dict[str, Any]` per row (`routes_requests.py`), a direct
  `dict(sqlite3.Row)` dump. Treat it as truthy/falsy, not `=== true`.
- **No new client-side state library.** TanStack Query's cache is the only
  cache (`FRONTEND--caching`). Don't add Redux/Zustand/Context-based
  stores for server data.
- **`staleTime` = 10_000ms and `refetchInterval` = 10_000ms** on every
  query hook. `FRONTEND--technologies` locks `staleTime` at 10s; this plan
  additionally rules `refetchInterval` to the same value so the dashboard
  actually re-polls while a tab stays open (the user's original "i dati
  devono essere live" requirement) — `staleTime` alone only affects
  refetch-on-remount/refocus, not a background poll. Ruling, not a vault
  gap: not deep enough on its own to need a sub-feature rewrite, but
  binding for this phase's implementer.
- **Tests mock at the `fetch` boundary, not by mocking the API client
  module.** `vi.spyOn(global, 'fetch')` (or `vi.fn()` assigned to
  `global.fetch`) in every test that needs network data — this is what
  lets a component test exercise the real `api/client.ts` parsing logic,
  not just a stub. See Task 2 for the client's error contract tests must
  rely on.
- **No absolute reliance on a running backend for `npm run test`.** Tests
  must pass with the backend not running at all (CI-safe). The one
  "verifiable" manual check against the real backend (Task 6) is separate
  from the automated test suite.

---

### Task 1: Stack wiring — dependencies, dev proxy, test tooling

**Files:**
- Modify: `frontend/package.json` (new dependencies + `test` script)
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/src/test/setup.test.ts` (placeholder, proves the test
  runner itself works)

**Interfaces:**
- Produces: a working `npm run test` command (Vitest), a Vite dev server
  that proxies `/status`, `/requests`, `/stats`, `/pricing`, `/control`,
  `/db` to `http://localhost:8000`, and `main.tsx` wrapping `<App />` in a
  `QueryClientProvider` — every later task's query hooks depend on this
  provider existing.
- Consumes: nothing (first task).

- [ ] **Step 1: Install runtime and dev dependencies**

From `frontend/`, run:

```bash
npm install @tanstack/react-query recharts
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

`recharts` has no import anywhere yet in this task or this phase — it is
installed now per `FRONTEND--technologies`'s explicit instruction to wire
the stack "for real" in Phase 5, ready for Phase 6's Usage page. Do not
add a placeholder import just to "use" it; an unused dependency in
`package.json` is not a lint violation.

- [ ] **Step 2: Add the dev-server proxy and Vitest config to `vite.config.ts`**

Replace the file's content with (keep the existing header comment, extend
it if the added config isn't self-explanatory from the header alone):

```ts
/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/status': 'http://localhost:8000',
      '/requests': 'http://localhost:8000',
      '/stats': 'http://localhost:8000',
      '/pricing': 'http://localhost:8000',
      '/control': 'http://localhost:8000',
      '/db': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
```

The `/// <reference types="vitest/config" />` triple-slash directive is
what makes TypeScript accept the `test` key on `defineConfig`'s return
type without needing a separate `vitest.config.ts` — confirm this
compiles (`npx tsc --noEmit` or just `npm run build`) rather than taking
it on faith; if it doesn't, use `import { defineConfig } from 'vitest/config'`
merged with Vite's own config via `mergeConfig` instead, whichever
actually type-checks cleanly with the versions `npm install` resolved.

Each proxy entry is a path-prefix match (Vite's dev proxy, built on
`http-proxy`, matches by prefix by default) — `/pricing` also covers
`POST /pricing/refresh`, `/control` also covers `/control/start` and
`/control/stop`, `/db` also covers `/db/tables/{name}`. No `changeOrigin`
or header rewriting: the point is that headers (including the browser's
`Sec-Fetch-Site`) pass through unchanged, per the Global Constraints note
above.

- [ ] **Step 3: Create the Vitest setup file**

`frontend/src/test/setup.ts`:

```ts
/*
 * setup.ts
 * Vitest setup file — extends `expect` with jest-dom's DOM matchers
 * (toBeInTheDocument, etc.) for every test file, and cleans up mounted
 * components between tests.
 */
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})
```

- [ ] **Step 4: Write and run a placeholder test to prove the runner works**

`frontend/src/test/setup.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

describe('vitest setup', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2)
  })
})
```

Run: `npm run test -- --run` (from `frontend/`)
Expected: 1 passed.

- [ ] **Step 5: Add the `test` script to `package.json`**

Add `"test": "vitest"` to the `scripts` block (alongside the existing
`dev`/`build`/`lint`/`preview`).

- [ ] **Step 6: Wrap `<App />` in `QueryClientProvider`**

Modify `frontend/src/main.tsx`:

```tsx
/*
 * main.tsx
 * Application entry point — mounts <App /> into the DOM, wrapped in a
 * TanStack Query client provider (every data-fetching hook in this app
 * depends on this provider existing above it in the tree).
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 7: Verify the dev server still boots**

Run: `npm run dev` (from `frontend/`), confirm it starts without error,
then stop it (Ctrl+C) — full manual UI verification happens in Task 6
once there's real content to look at.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/test/setup.ts frontend/src/test/setup.test.ts frontend/src/main.tsx
git commit -m "feat(frontend): wire TanStack Query, Recharts, dev proxy, and Vitest"
```

---

### Task 2: API client, types, and TanStack Query hooks

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/hooks/useStatus.ts`
- Create: `frontend/src/hooks/useStats.ts`
- Create: `frontend/src/hooks/useRecentRequests.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: nothing new (the `QueryClientProvider` from Task 1 must wrap
  any component that renders these hooks, but the hooks themselves have no
  compile-time dependency on it).
- Produces: `useStatus()`, `useStats()`, `useRecentRequests()` — each
  returns whatever `useQuery` returns (`{ data, isLoading, isError, ... }`)
  typed against this file's response types. Tasks 3-5 consume these three
  hooks by name and rely on `data`'s shape matching `types.ts` exactly.

- [ ] **Step 1: Write the response types, mirroring the backend's Pydantic models field-for-field**

`frontend/src/api/types.ts` — copy every field name and nullability
exactly from `backend/src/fcc_dashboard/routes_status.py`,
`routes_stats.py`, `routes_requests.py` (read them if you need to
double-check a field — do not guess a name):

```ts
/*
 * types.ts
 * TypeScript mirrors of BACKEND's Pydantic response models. Field names
 * and nullability must match backend/src/fcc_dashboard/routes_*.py
 * exactly — these are not independently designed, they are a transcription
 * of an existing contract.
 */

export type ProviderHealthStatus = 'ok' | 'stale_key' | 'rate_limited' | 'down'

export interface ProviderStatus {
  provider: string
  status: ProviderHealthStatus
  last_error_at: string | null
  http_status: number | null
}

export interface StatusResponse {
  fcc_status: 'up' | 'down'
  providers: ProviderStatus[]
}

export interface ByProviderStats {
  provider: string
  request_count: number
  savings: number
}

export interface StatsResponse {
  range: string
  range_start: string
  range_end: string
  total_requests: number
  completed_requests: number
  error_requests: number
  pending_requests: number
  total_input_tokens: number
  total_output_tokens: number
  total_savings: number | null
  unpriced_request_count: number
  by_provider: ByProviderStats[]
}

export type RequestStatus = 'pending' | 'completed' | 'error'

export interface RequestRow {
  request_id: string
  provider: string | null
  gateway_model: string | null
  downstream_model: string | null
  input_tokens: number | null
  output_tokens: number | null
  input_tokens_estimate: number | null
  finish_reason: string | null
  http_status: number | null
  exc_type: string | null
  occurred_at: string
  occurred_at_is_estimated: 0 | 1
  ingested_at: string
  actual_cost: number | null
  equivalent_cost: number | null
  savings: number | null
  status: RequestStatus
}

export interface RequestsListResponse {
  total: number
  limit: number
  offset: number
  results: RequestRow[]
}
```

- [ ] **Step 2: Write the failing client tests**

`frontend/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getStatus, getStats, getRecentRequests } from './client'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('getStatus', () => {
  it('fetches /status and returns the parsed JSON', async () => {
    const body = { fcc_status: 'up', providers: [] }
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(body), { status: 200 }),
    )
    const result = await getStatus()
    expect(global.fetch).toHaveBeenCalledWith('/status')
    expect(result).toEqual(body)
  })

  it('throws when the response is not ok', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('server error', { status: 500 }),
    )
    await expect(getStatus()).rejects.toThrow()
  })

  it('propagates a network-level fetch rejection', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(getStatus()).rejects.toThrow('Failed to fetch')
  })
})

describe('getStats', () => {
  it('fetches /stats with the range as a query param', async () => {
    const body = {
      range: 'last_7_days', range_start: 'x', range_end: 'y',
      total_requests: 0, completed_requests: 0, error_requests: 0,
      pending_requests: 0, total_input_tokens: 0, total_output_tokens: 0,
      total_savings: null, unpriced_request_count: 0, by_provider: [],
    }
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(body), { status: 200 }),
    )
    const result = await getStats('last_7_days')
    expect(global.fetch).toHaveBeenCalledWith('/stats?range=last_7_days')
    expect(result).toEqual(body)
  })
})

describe('getRecentRequests', () => {
  it('fetches /requests with a limit query param', async () => {
    const body = { total: 0, limit: 20, offset: 0, results: [] }
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(body), { status: 200 }),
    )
    const result = await getRecentRequests(20)
    expect(global.fetch).toHaveBeenCalledWith('/requests?limit=20')
    expect(result).toEqual(body)
  })
})
```

Run: `npm run test -- --run` — expect all of these to FAIL (module
`./client` doesn't exist yet).

- [ ] **Step 3: Implement the client to make the tests pass**

Write `frontend/src/api/client.ts` yourself to satisfy the tests above:
three exported async functions, `getStatus(): Promise<StatusResponse>`,
`getStats(range: string): Promise<StatsResponse>`,
`getRecentRequests(limit: number): Promise<RequestsListResponse>`. Each
calls `fetch` with a relative URL (`/status`, `/stats?range=...`,
`/requests?limit=...`), throws an `Error` if `!response.ok` (include the
HTTP status in the thrown message so a future error boundary/log has
something useful), and returns `response.json()` cast to the matching
type. Do not add retry logic, timeouts, or an abstraction layer beyond
this — TanStack Query already owns retry/staleness behavior at the hook
level (Step 4).

Run: `npm run test -- --run` — expect all tests from Step 2 to PASS.

- [ ] **Step 4: Write the three query hooks**

`frontend/src/hooks/useStatus.ts`:

```ts
/*
 * useStatus.ts
 * TanStack Query hook for GET /status — FCC reachability and per-provider
 * health. `isError` here means the dashboard's own backend is unreachable,
 * never "FCC is down" (see BACKEND--api / routes_status.py: /status is
 * designed to never fail while the backend itself is running — that fact
 * degrades gracefully into a successful `fcc_status: "down"` response
 * instead of a thrown error). Consumed by StatusPanel and by App's
 * backend-unreachable gate (Task 3).
 */
import { useQuery } from '@tanstack/react-query'
import { getStatus } from '../api/client'

export function useStatus() {
  return useQuery({
    queryKey: ['status'],
    queryFn: getStatus,
    staleTime: 10_000,
    refetchInterval: 10_000,
  })
}
```

`frontend/src/hooks/useStats.ts` (same shape, `queryKey: ['stats', range]`,
`queryFn: () => getStats(range)`, takes a `range: string` parameter,
defaulting the caller's choice — no default range baked into the hook
itself, Task 4 decides the range it passes).

`frontend/src/hooks/useRecentRequests.ts` (same shape,
`queryKey: ['recentRequests', limit]`, `queryFn: () => getRecentRequests(limit)`,
takes a `limit: number` parameter).

All three: `staleTime: 10_000, refetchInterval: 10_000` per the Global
Constraints ruling.

- [ ] **Step 5: Run the full test suite**

Run: `npm run test -- --run`
Expected: all tests pass (Task 1's placeholder + Task 2's client tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api frontend/src/hooks
git commit -m "feat(frontend): API client, response types, and query hooks"
```

---

### Task 3: StatusPanel + the backend-unreachable resilience gate

**Files:**
- Create: `frontend/src/components/StatusPanel.tsx`
- Test: `frontend/src/components/StatusPanel.test.tsx`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `useStatus()` from Task 2 (`StatusResponse` shape from
  `types.ts`).
- Produces: `<StatusPanel />` (no props — it calls `useStatus()` itself,
  matching this app's "every panel owns its own query" pattern so Task 6
  can compose panels without prop-drilling query results). Also produces
  the pattern `App.tsx` uses to decide whether to render the dashboard at
  all — Task 6's `App.tsx` change directly copies this task's approach.

- [ ] **Step 1: Write the failing StatusPanel tests**

`frontend/src/components/StatusPanel.test.tsx` — wrap every render in a
fresh `QueryClientProvider` (a small local test helper, since
`useStatus` requires one in its ancestry):

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StatusPanel } from './StatusPanel'

afterEach(() => {
  vi.restoreAllMocks()
})

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  )
}

describe('StatusPanel', () => {
  it('shows FCC as up with no provider issues', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ fcc_status: 'up', providers: [] }),
        { status: 200 },
      ),
    )
    renderWithClient(<StatusPanel />)
    await waitFor(() => expect(screen.getByText(/up/i)).toBeInTheDocument())
  })

  it('shows a stale-key provider distinctly from a down provider', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          fcc_status: 'up',
          providers: [
            { provider: 'deepseek', status: 'stale_key', last_error_at: '2026-08-25T00:00:00.000Z', http_status: 401 },
            { provider: 'kimi', status: 'down', last_error_at: '2026-08-25T00:00:00.000Z', http_status: null },
          ],
        }),
        { status: 200 },
      ),
    )
    renderWithClient(<StatusPanel />)
    await waitFor(() => expect(screen.getByText(/deepseek/i)).toBeInTheDocument())
    expect(screen.getByText(/stale.?key/i)).toBeInTheDocument()
    expect(screen.getByText(/kimi/i)).toBeInTheDocument()
    expect(screen.getByText(/down/i)).toBeInTheDocument()
  })
})
```

Run: `npm run test -- --run` — expect FAIL (`./StatusPanel` doesn't exist).

- [ ] **Step 2: Implement `StatusPanel`**

Write `frontend/src/components/StatusPanel.tsx` to satisfy the tests: a
function component that calls `useStatus()`, renders a loading state
while `isLoading`, and once data is present renders `fcc_status`
("up"/"down", styled distinctly — e.g. a colored dot/badge) plus one row
per entry in `providers` showing `provider` and a human-readable label
for `status` (`ok` -> "OK", `stale_key` -> "Stale key", `rate_limited` ->
"Rate limited", `down` -> "Down" — exact wording is your call, the tests
above only match case-insensitively on substrings). Do not handle the
`isError` (backend-unreachable) case inside this component — that is
deliberately `App.tsx`'s job (Step 4 below), so a panel embedded
elsewhere later doesn't have to duplicate a full-page fallback.

Run: `npm run test -- --run` — expect the Step 1 tests to PASS.

- [ ] **Step 3: Write the failing App-level resilience test**

`frontend/src/App.test.tsx`:

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'

afterEach(() => {
  vi.restoreAllMocks()
})

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

describe('App resilience', () => {
  it('shows a backend-not-running state when /status cannot be reached at all', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    renderApp()
    await waitFor(() =>
      expect(screen.getByText(/backend.*not running|can'?t reach.*backend/i)).toBeInTheDocument(),
    )
  })
})
```

Run: `npm run test -- --run` — expect FAIL (App doesn't render this state
yet — it currently renders the Phase 0 placeholder heading unconditionally).

- [ ] **Step 4: Update `App.tsx` to gate on backend reachability**

Modify `frontend/src/App.tsx`: call `useStatus()` at the top level: while
`isLoading` on the very first load, render a neutral loading state; if
`isError`, render a full-page "Backend not running" message instead of
any dashboard content (per `FRONTEND--resilience`'s "distinct 'backend
not running' state, not a status panel with empty/error data") — this
message doesn't need to be elaborate, but should be visually distinct
(not just reusing `StatusPanel`, which Task 6 will still render as one of
several panels once the backend *is* reachable). Otherwise (data present,
no error) render the dashboard content — at the end of this task, App
still only mounts `<StatusPanel />` directly (Task 6 replaces this with
the full `Overview` page once `MoneySavedHeadline` and
`RecentRequestsFeed` exist).

Run: `npm run test -- --run` — expect the Step 3 test to PASS, and
`StatusPanel.test.tsx` to keep passing (it never triggers `isError`, so
it must still render normally through `App` unaffected... actually verify
this only if `StatusPanel.test.tsx` renders `<App />`; if it renders
`<StatusPanel />` directly as written above, this concern doesn't apply —
just make sure nothing regressed: `npm run test -- --run` all-green).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StatusPanel.tsx frontend/src/components/StatusPanel.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat(frontend): StatusPanel and the backend-unreachable resilience gate"
```

---

### Task 4: MoneySavedHeadline

**Files:**
- Create: `frontend/src/components/MoneySavedHeadline.tsx`
- Test: `frontend/src/components/MoneySavedHeadline.test.tsx`

**Interfaces:**
- Consumes: `useStats()` from Task 2, called with a fixed range —
  `useStats('last_7_days')` — no range selector in this task (Usage page,
  Phase 6, owns range selection; Overview's headline uses a fixed default,
  same default `GET /stats` itself uses server-side).
- Produces: `<MoneySavedHeadline />` (no props, same self-fetching pattern
  as `StatusPanel`).

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/MoneySavedHeadline.test.tsx`:

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MoneySavedHeadline } from './MoneySavedHeadline'

afterEach(() => {
  vi.restoreAllMocks()
})

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const baseStats = {
  range: 'last_7_days', range_start: 'x', range_end: 'y',
  total_requests: 10, completed_requests: 8, error_requests: 1,
  pending_requests: 1, total_input_tokens: 1000, total_output_tokens: 2000,
  unpriced_request_count: 0, by_provider: [],
}

describe('MoneySavedHeadline', () => {
  it('renders a real savings total', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...baseStats, total_savings: 12.5 }), { status: 200 }),
    )
    renderWithClient(<MoneySavedHeadline />)
    await waitFor(() => expect(screen.getByText(/12\.5/)).toBeInTheDocument())
  })

  it('renders a distinct message when total_savings is null (never priced), not $0', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...baseStats, total_savings: null, unpriced_request_count: 8 }), { status: 200 }),
    )
    renderWithClient(<MoneySavedHeadline />)
    await waitFor(() =>
      expect(screen.getByText(/no pricing|not.*priced|unavailable/i)).toBeInTheDocument(),
    )
    expect(screen.queryByText(/\$?0(\.00)?\b/)).not.toBeInTheDocument()
  })

  it('surfaces the unpriced-request count when some requests were excluded from the total', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...baseStats, total_savings: 5.0, unpriced_request_count: 3 }), { status: 200 }),
    )
    renderWithClient(<MoneySavedHeadline />)
    await waitFor(() => expect(screen.getByText(/3/)).toBeInTheDocument())
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 2: Implement `MoneySavedHeadline`**

Write the component to satisfy the tests: calls `useStats('last_7_days')`,
shows a loading state while `isLoading`. Once data is present: if
`total_savings === null`, render a message distinguishing "we have never
priced anything" from a genuine $0 (do not render any `$0`/`0.00`-shaped
text in this branch — the tests explicitly forbid it). Otherwise render
`total_savings` formatted as currency (`Intl.NumberFormat('en-US', { style:
'currency', currency: 'USD' })` — no new dependency needed, this is a
browser built-in). If `unpriced_request_count > 0`, render it as a
secondary note near the headline (e.g. "3 requests excluded — unpriced").

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MoneySavedHeadline.tsx frontend/src/components/MoneySavedHeadline.test.tsx
git commit -m "feat(frontend): MoneySavedHeadline, never conflating null savings with zero"
```

---

### Task 5: RecentRequestsFeed with the estimated-timestamp marker

**Files:**
- Create: `frontend/src/components/RecentRequestsFeed.tsx`
- Test: `frontend/src/components/RecentRequestsFeed.test.tsx`

**Interfaces:**
- Consumes: `useRecentRequests()` from Task 2, called with a fixed limit —
  `useRecentRequests(20)`.
- Produces: `<RecentRequestsFeed />` (no props, same self-fetching
  pattern).

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/RecentRequestsFeed.test.tsx`:

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RecentRequestsFeed } from './RecentRequestsFeed'

afterEach(() => {
  vi.restoreAllMocks()
})

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

function makeRow(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    request_id: 'req-1', provider: 'deepseek', gateway_model: 'sonnet',
    downstream_model: 'deepseek-chat', input_tokens: 100, output_tokens: 200,
    input_tokens_estimate: null, finish_reason: 'stop', http_status: 200,
    exc_type: null, occurred_at: '2026-08-25T10:00:00.000Z',
    occurred_at_is_estimated: 0, ingested_at: '2026-08-25T10:00:01.000Z',
    actual_cost: 0.01, equivalent_cost: 0.05, savings: 0.04, status: 'completed',
    ...overrides,
  }
}

describe('RecentRequestsFeed', () => {
  it('renders a row for each request', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ total: 1, limit: 20, offset: 0, results: [makeRow()] }),
        { status: 200 },
      ),
    )
    renderWithClient(<RecentRequestsFeed />)
    await waitFor(() => expect(screen.getByText(/deepseek/i)).toBeInTheDocument())
  })

  it('visually marks a row whose timestamp is estimated', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          total: 1, limit: 20, offset: 0,
          results: [makeRow({ request_id: 'req-2', occurred_at_is_estimated: 1 })],
        }),
        { status: 200 },
      ),
    )
    renderWithClient(<RecentRequestsFeed />)
    await waitFor(() => expect(screen.getByText(/estimated/i)).toBeInTheDocument())
  })

  it('does not mark a row with a real timestamp as estimated', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          total: 1, limit: 20, offset: 0,
          results: [makeRow({ request_id: 'req-3', occurred_at_is_estimated: 0 })],
        }),
        { status: 200 },
      ),
    )
    renderWithClient(<RecentRequestsFeed />)
    await waitFor(() => expect(screen.getByText(/deepseek/i)).toBeInTheDocument())
    expect(screen.queryByText(/estimated/i)).not.toBeInTheDocument()
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 2: Implement `RecentRequestsFeed`**

Write the component: calls `useRecentRequests(20)`, loading state while
`isLoading`, then renders a table (or table-like list) with one row per
entry in `results`. Each row shows at minimum: `occurred_at` (formatted
via `new Date(row.occurred_at).toLocaleString()` — no date library
needed), `provider`, `downstream_model`, `status`, `input_tokens` /
`output_tokens`, and `savings` (formatted as currency, `null` shown as
"—" or similar, not `$0`). A row where `occurred_at_is_estimated` is
truthy (`1`, not `=== true` — see Global Constraints) additionally
renders a marker/badge containing the word "estimated" (e.g. a tooltip
or inline label) — the exact presentation is your call, the tests only
check for that substring's presence/absence.

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/RecentRequestsFeed.tsx frontend/src/components/RecentRequestsFeed.test.tsx
git commit -m "feat(frontend): RecentRequestsFeed with the estimated-timestamp marker"
```

---

### Task 6: Overview page composition, App wiring, end-to-end verification

**Files:**
- Create: `frontend/src/pages/Overview.tsx`
- Test: `frontend/src/pages/Overview.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx` (only if Task 3's test needs
  adjusting now that `App` renders more than `StatusPanel` — read it
  first; adjust only what the new content requires, don't rewrite
  unrelated assertions)

**Interfaces:**
- Consumes: `StatusPanel` (Task 3), `MoneySavedHeadline` (Task 4),
  `RecentRequestsFeed` (Task 5) — this task only composes them, it does
  not add new data-fetching logic.
- Produces: the finished Overview page, mounted as `App`'s content once
  the backend-unreachable gate (Task 3) passes.

- [ ] **Step 1: Write the failing Overview composition test**

`frontend/src/pages/Overview.test.tsx`:

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Overview } from './Overview'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Overview', () => {
  it('renders status, savings, and the requests feed together', async () => {
    vi.spyOn(global, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/status')) {
        return Promise.resolve(
          new Response(JSON.stringify({ fcc_status: 'up', providers: [] }), { status: 200 }),
        )
      }
      if (url.startsWith('/stats')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              range: 'last_7_days', range_start: 'x', range_end: 'y',
              total_requests: 1, completed_requests: 1, error_requests: 0,
              pending_requests: 0, total_input_tokens: 10, total_output_tokens: 20,
              total_savings: 1.23, unpriced_request_count: 0, by_provider: [],
            }),
            { status: 200 },
          ),
        )
      }
      if (url.startsWith('/requests')) {
        return Promise.resolve(
          new Response(JSON.stringify({ total: 0, limit: 20, offset: 0, results: [] }), { status: 200 }),
        )
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Overview />
      </QueryClientProvider>,
    )

    await waitFor(() => expect(screen.getByText(/up/i)).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText(/1\.23/)).toBeInTheDocument())
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 2: Implement `Overview`**

`frontend/src/pages/Overview.tsx` — a function component rendering
`<StatusPanel />`, `<MoneySavedHeadline />`, and `<RecentRequestsFeed />`
together (layout/styling with Tailwind utility classes is your call —
keep it simple, this is a scaffold, not a final visual design pass).

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Wire `Overview` into `App`**

Modify `frontend/src/App.tsx`: replace the direct `<StatusPanel />` mount
(from Task 3) with `<Overview />` in the "backend reachable" branch. The
loading and backend-unreachable branches from Task 3 stay unchanged.

If `App.test.tsx`'s existing assertions now fail because `Overview`
fetches `/stats` and `/requests` in addition to `/status` and the test's
mocked `fetch` only handles `/status`, update that test's mock to route
by URL the same way Step 1's `Overview.test.tsx` does above (or mock
`global.fetch` to resolve generically for any URL, if the test doesn't
care about the other panels' content) — whichever keeps the test's
original intent (proving the backend-unreachable branch renders) clearest.
Do not delete or weaken the assertion that a network failure on `/status`
renders the backend-not-running state; that is this test's whole point.

Run: `npm run test -- --run` — expect all tests across the whole suite to
PASS.

- [ ] **Step 4: Manual end-to-end verification against the real backend**

This is the plan's own "Verifiable" criterion — do this for real, don't
skip it:

1. In one terminal, from `backend/`: `uv run fcc-dashboard-server` (or
   however `__main__.py`'s `serve()` entrypoint is invoked — check
   `pyproject.toml`'s `[project.scripts]` entry from Phase 3 if unsure).
2. In another terminal, from `frontend/`: `npm run dev`.
3. Open the printed Vite dev URL (typically `http://localhost:5173`) in a
   browser.
4. Confirm the Overview page renders real data from the real backend — not
   a blank page, not a "backend not running" message (unless the backend
   really isn't up, in which case fix that first). If the local SQLite DB
   has no rows yet (a fresh install), confirm the page still renders
   cleanly with empty/zero states rather than crashing — this is a
   legitimate real-world first-run state, not a test-only edge case.
5. Open the browser's network tab and confirm requests to `/status` etc.
   are going to the Vite origin (proxied), not directly to
   `localhost:8000` — this is the actual proof the Task 1 proxy + Global
   Constraints relative-URL rule work together correctly.

Record the outcome (screenshot not required, but note what you observed)
in your report.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Overview.tsx frontend/src/pages/Overview.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat(frontend): compose the Overview page and wire it into App"
```
