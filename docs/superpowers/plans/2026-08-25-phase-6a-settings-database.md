# Phase 6a — Settings & Database Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add page navigation to the dashboard (currently Overview-only) and
build the Settings and Database pages against the already-complete backend
API. Usage (the fourth page) is deliberately NOT part of this plan — see
the "Scope note" below.

**Architecture:** A lightweight tab-based navigation shell (no router
library — this is a local, single-user tool with no deep-linking
requirement anywhere in its design), each page still following Phase 5's
established pattern: self-fetching components, TanStack Query as the only
cache, Tailwind for styling.

**Tech Stack:** Same as Phase 5 (React 19, TypeScript, TanStack Query v5,
Tailwind v4, Vitest + React Testing Library). No new dependencies planned.

**Spec:** `vault-fcc-dashboard/plans/PHASE-6-FRONTEND-REMAINING-PAGES.md`
(scope — this plan covers 2 of its 3 pages, see the note below),
`vault-fcc-dashboard/features/FRONTEND/FRONTEND--settings.md`,
`FRONTEND--database.md`, `FRONTEND--security.md`, `FRONTEND--architecture.md`,
`vault-fcc-dashboard/features/BACKEND/BACKEND--api.md`,
`BACKEND--process-control.md`,
`vault-fcc-dashboard/features/PRICING-ENGINE/PRICING-ENGINE--price-refresh.md`,
`PRICING-ENGINE--resilience.md`.

## Scope note (ruling, not a plan gap)

The vault's Phase 6 doc groups Usage, Settings, and Database together.
While preparing this plan, a real contract gap was found: `FRONTEND--usage`
requires charts of token AND call volume broken down by BOTH provider AND
model, but `GET /stats`'s only breakdown (`by_provider`) is savings-only
(no token counts, no by-model split, and it silently excludes unpriced/
non-completed rows because it's specifically the money-math breakdown, not
a volume breakdown). Building Usage correctly needs a small, deliberate
backend extension, not a quick frontend-only task — that's real design
work, not mechanical implementation, and doesn't belong crammed into an
SDD task brief. Ruling: split Phase 6 into two plans. This plan (6a) ships
Settings and Database now, against the existing, complete, gap-free API —
a real, independently-valuable increment with its own rollback point.
Usage becomes plan 6b, planned separately once its backend extension is
designed. This is the correct call under "the spec is the binding
authority, the plan is its argument, your judgment settles what neither
answers" — proceeding rather than stalling, and splitting rather than
either skipping proper design or blocking two clean, ready pages on it.

## Global Constraints

- **Relative URLs only, everywhere in the API client** — same rule as
  Phase 5. Every new client function added in Task 1 uses a relative path
  (`/pricing`, `/db/tables`, `/control/start`, etc.), never an absolute
  URL, so the existing Vite dev proxy and the `Sec-Fetch-Site` same-origin
  property established in Phase 5 keep working for these new,
  security-sensitive endpoints too (`/control/*` already enforces this
  server-side; getting it wrong here would 403 in dev without explanation).
- **No new client-side state library or router.** Tab navigation state is
  local `useState` in one place (Task 2), same "React Query's cache is the
  only real cache" rule as Phase 5.
- **Never invent a price.** A `(provider, model)` pair with no configured
  price must always render as "unknown," never as `$0` or blank — same
  invariant Phase 5 applied to `total_savings`, now applied to individual
  price entries in the Settings pricing table.
- **The price-refresh flow is strictly two-step and never auto-applies.**
  `POST /pricing/refresh` only ever produces a diff for display — no task
  in this plan may wire its result directly into a `PUT /pricing` call.
  Only an explicit, separate user action (Task 6) writes anything.
- **Confirm-before-action on every one of these three actions**: starting
  FCC (`POST /control/start`), stopping FCC (`POST /control/stop`), and
  any price-config write (`PUT /pricing`, both manual edits and an
  approved refresh diff). `FRONTEND--settings.md` is explicit that
  "both" start and stop "go through the confirm-before-action step ...
  before firing" — follow that literally rather than the narrower
  reading `FRONTEND--security.md`'s own rationale alone might suggest
  (it explains WHY stopping/pricing-writes need it but doesn't
  contradict `--settings`' broader instruction to gate start too). Use
  an in-app confirmation UI element (a two-step button, or a small
  inline confirm panel) — never the browser's native
  `window.confirm()`/`alert()`, which doesn't match this project's
  visual design and can't be styled or tested the same way as the rest
  of the UI.
- **`GET /db/tables/{name}` returns rows as plain arrays, not objects**
  (`columns: string[]`, `rows: unknown[][]`) — this is a raw physical
  debug view, not a curated response. Task 3's table renders columns and
  rows exactly as given, zipping `columns[i]` with `row[i]` for display,
  never assuming specific column names (the whole point of this page is
  that it works for any table, including ones added by a future phase).
- **Tests mock at the `fetch` boundary**, matching Phase 5's established
  pattern (`vi.spyOn(global, 'fetch')`), never by mocking the API client
  module directly.

---

### Task 1: Tab navigation shell

**Files:**
- Create: `frontend/src/components/Nav.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/components/Nav.test.tsx`
- Test: `frontend/src/App.test.tsx` (extend, don't rewrite existing
  assertions — read it first)

**Interfaces:**
- Produces: `<Nav activeTab={...} onTabChange={...} />` and a restructured
  `App.tsx` that renders one of four page slots based on local
  `useState<'overview' | 'usage' | 'settings' | 'database'>('overview')`
  state, keeping the existing `isLoading`/`isError` backend-unreachable
  gate from Phase 5 completely unchanged and evaluated BEFORE any tab
  content renders (a broken backend must still short-circuit the whole
  app, regardless of which tab was last selected).
- Consumes: `Overview` (existing, Phase 5). The `usage` tab renders a
  simple placeholder (`<div>Usage — coming soon</div>` is fine, literally)
  until Phase 6b. `settings` and `database` tabs render the pages this
  plan builds in Tasks 3-7 — at the end of THIS task, before those exist,
  they may also render simple placeholders; Tasks 3 and 7 replace them.

- [ ] **Step 1: Write the failing Nav tests**

`frontend/src/components/Nav.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Nav } from './Nav'

describe('Nav', () => {
  it('renders all four tabs', () => {
    render(<Nav activeTab="overview" onTabChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /overview/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /usage/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /settings/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /database/i })).toBeInTheDocument()
  })

  it('calls onTabChange with the clicked tab', async () => {
    const onTabChange = vi.fn()
    render(<Nav activeTab="overview" onTabChange={onTabChange} />)
    await userEvent.click(screen.getByRole('button', { name: /settings/i }))
    expect(onTabChange).toHaveBeenCalledWith('settings')
  })

  it('visually distinguishes the active tab from inactive ones', () => {
    render(<Nav activeTab="database" onTabChange={vi.fn()} />)
    const active = screen.getByRole('button', { name: /database/i })
    const inactive = screen.getByRole('button', { name: /overview/i })
    expect(active.className).not.toBe(inactive.className)
  })
})
```

Run: `npm run test -- --run` — expect FAIL (`./Nav` doesn't exist).

- [ ] **Step 2: Implement `Nav`**

`frontend/src/components/Nav.tsx` — a function component with two props,
`activeTab: 'overview' | 'usage' | 'settings' | 'database'` and
`onTabChange: (tab: 'overview' | 'usage' | 'settings' | 'database') => void`
(define and export this union type here — later tasks/tests import it).
Renders 4 `<button>` elements, one per tab, calling `onTabChange` with
that tab's value on click, with the active one styled distinctly
(Tailwind classes — e.g. a different background/border on the matching
tab, your call on exact styling).

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Write the failing App restructuring test**

Read the existing `frontend/src/App.test.tsx` first (it currently has an
`isError`-triggers-backend-unreachable test from Phase 5 — do not weaken
or remove that assertion). Add a new test to the same file:

```tsx
it('switches to the Settings tab on click, keeping the backend-reachable content mounted', async () => {
  vi.spyOn(global, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ fcc_status: 'up', providers: [] }), { status: 200 }),
  )
  const user = userEvent.setup()
  renderApp() // reuse this file's existing helper, don't duplicate it
  await waitFor(() => expect(screen.getByRole('button', { name: /settings/i })).toBeInTheDocument())
  await user.click(screen.getByRole('button', { name: /settings/i }))
  // Task 7 replaces the Settings placeholder — for now, just confirm the
  // tab switch itself works and Overview's content is no longer the only
  // thing rendered. Adjust this assertion once Settings has real content
  // if it's more natural to assert against that instead — your call,
  // as long as it genuinely proves the tab switched.
})
```

(`userEvent` needs importing at the top of the test file if not already
present — `@testing-library/user-event` was installed in Phase 5 Task 1.)

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 4: Restructure `App.tsx`**

Add the `useState` tab state, render `<Nav activeTab={tab} onTabChange={setTab} />`
above the page content, and switch which page renders based on `tab` —
`isLoading`/`isError` branches stay exactly as they are, evaluated first,
unconditionally on the tab state (a user who switched to Settings and
then the backend goes down must still see the backend-unreachable screen,
not a broken Settings page).

Run: `npm run test -- --run` — expect PASS, and confirm ALL existing
`App.test.tsx` tests (including the Phase 5 resilience one) still pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Nav.tsx frontend/src/components/Nav.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat(frontend): tab navigation shell for the 4-page dashboard"
```

---

### Task 2: API client, types, and hooks for pricing, db, and control

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/hooks/usePricing.ts`
- Create: `frontend/src/hooks/usePricingMutations.ts`
- Create: `frontend/src/hooks/useDbTables.ts`
- Create: `frontend/src/hooks/useControl.ts`
- Test: `frontend/src/api/client.test.ts` (extend the existing file)

**Interfaces:**
- Consumes: nothing new.
- Produces: `usePricing()` (query), `usePricingRefresh()` (mutation, calls
  `POST /pricing/refresh`), `usePutPricing()` (mutation, calls
  `PUT /pricing`), `useDbTables()` (query, list of table names),
  `useDbTableRows(name, limit, offset)` (query), `useControlStart()` /
  `useControlStop()` (mutations). Tasks 3-6 consume these by name.

- [ ] **Step 1: Add the new response/request types**

Extend `frontend/src/api/types.ts` — mirror these exactly from
`backend/src/fcc_dashboard/routes_pricing.py` and `routes_db.py` (read
them if you need to double-check a field — don't guess):

```ts
export interface PriceEntry {
  input_per_million: number
  output_per_million: number
  [key: string]: unknown // currency/last_updated/source may be present
}

export interface PricingConfig {
  anthropic: { opus: PriceEntry; sonnet: PriceEntry; haiku: PriceEntry }
  providers: Record<string, Record<string, PriceEntry>>
}

export interface PricingChange {
  provider: string
  model: string
  current: { input_per_million: number; output_per_million: number } | null
  proposed: { input_per_million: number; output_per_million: number } | null
  source: string
  changed: boolean
}

export interface PricingPairNotFound {
  provider: string
  model: string
}

export interface PricingRefreshResponse {
  changes: PricingChange[]
  not_found: PricingPairNotFound[]
}

export interface TablesListResponse {
  tables: string[]
}

export interface TableRowsResponse {
  table: string
  total: number
  limit: number
  offset: number
  columns: string[]
  rows: unknown[][]
}

export type ControlStartAction = 'started' | 'already_running' | 'executable_not_found' | 'launch_failed'
export type ControlStopAction = 'stopped' | 'not_running' | 'stop_failed'

export interface ControlStartResponse {
  action: ControlStartAction
  pid: number | null
}

export interface ControlStopResponse {
  action: ControlStopAction
  pid: number | null
}
```

- [ ] **Step 2: Write the failing client tests**

Append to `frontend/src/api/client.test.ts` (matching the file's existing
`describe`/`it` style and its `afterEach(() => vi.restoreAllMocks())`):

```ts
describe('getPricing', () => {
  it('fetches /pricing', async () => {
    const body = { anthropic: {}, providers: {} }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await getPricing()
    expect(global.fetch).toHaveBeenCalledWith('/pricing')
    expect(result).toEqual(body)
  })
})

describe('putPricing', () => {
  it('PUTs the full config document as JSON', async () => {
    const config = { anthropic: {}, providers: {} }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(config), { status: 200 }))
    await putPricing(config as never)
    expect(global.fetch).toHaveBeenCalledWith('/pricing', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
  })
})

describe('postPricingRefresh', () => {
  it('POSTs to /pricing/refresh with no body', async () => {
    const body = { changes: [], not_found: [] }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await postPricingRefresh()
    expect(global.fetch).toHaveBeenCalledWith('/pricing/refresh', { method: 'POST' })
    expect(result).toEqual(body)
  })
})

describe('getDbTables', () => {
  it('fetches /db/tables', async () => {
    const body = { tables: ['requests'] }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await getDbTables()
    expect(global.fetch).toHaveBeenCalledWith('/db/tables')
    expect(result).toEqual(body)
  })
})

describe('getDbTableRows', () => {
  it('fetches /db/tables/{name} with limit and offset', async () => {
    const body = { table: 'requests', total: 0, limit: 20, offset: 0, columns: [], rows: [] }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await getDbTableRows('requests', 20, 0)
    expect(global.fetch).toHaveBeenCalledWith('/db/tables/requests?limit=20&offset=0')
    expect(result).toEqual(body)
  })
})

describe('postControlStart', () => {
  it('POSTs to /control/start', async () => {
    const body = { action: 'started', pid: 123 }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await postControlStart()
    expect(global.fetch).toHaveBeenCalledWith('/control/start', { method: 'POST' })
    expect(result).toEqual(body)
  })
})

describe('postControlStop', () => {
  it('POSTs to /control/stop', async () => {
    const body = { action: 'stopped', pid: 123 }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await postControlStop()
    expect(global.fetch).toHaveBeenCalledWith('/control/stop', { method: 'POST' })
    expect(result).toEqual(body)
  })
})
```

Add the matching imports (`getPricing, putPricing, postPricingRefresh,
getDbTables, getDbTableRows, postControlStart, postControlStop`) to this
test file's existing `import { ... } from './client'` line.

Run: `npm run test -- --run` — expect FAIL (these exports don't exist yet).

- [ ] **Step 3: Implement the 7 new client functions**

Add to `frontend/src/api/client.ts`, following the file's existing
`parseJsonOrThrow` helper and error-on-non-ok pattern exactly:
`getPricing()`, `putPricing(config: PricingConfig)` (PUT with a JSON
body and `Content-Type: application/json` header — note the exact
`fetch` call shape the tests above assert), `postPricingRefresh()` (POST,
no body), `getDbTables()`, `getDbTableRows(name: string, limit: number,
offset: number)`, `postControlStart()`, `postControlStop()` (both POST,
no body). Table names in the URL: use `encodeURIComponent(name)` when
building the `/db/tables/{name}` path — this project's convention so far
has been simple string interpolation for backend-constrained enum
values, but a raw table name is user/schema-derived, not enum-constrained,
so encode it properly here even though `client.test.ts`'s literal test
case (`'requests'`) wouldn't itself catch a missing-encode bug.

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 4: Write the query/mutation hooks**

`frontend/src/hooks/usePricing.ts`:
```ts
import { useQuery } from '@tanstack/react-query'
import { getPricing } from '../api/client'

export function usePricing() {
  return useQuery({
    queryKey: ['pricing'],
    queryFn: getPricing,
    staleTime: 10_000,
  })
}
```
(No `refetchInterval` here — unlike Phase 5's read-heavy hooks, pricing
data only changes via explicit user action on this same page, not by
outside events worth polling for every 10s. This is a deliberate,
documented deviation from Phase 5's uniform-polling rule — note it in
this file's header comment.)

`frontend/src/hooks/usePricingMutations.ts` — two `useMutation` hooks,
`usePutPricing()` and `usePricingRefresh()`, each wrapping the matching
client function. `usePutPricing`'s `onSuccess` should invalidate the
`['pricing']` query (`queryClient.invalidateQueries({ queryKey: ['pricing'] })`,
via `useQueryClient()`) so the pricing table re-fetches and shows the
just-written values, rather than stale pre-write data sitting in the
cache for up to `staleTime`.

`frontend/src/hooks/useDbTables.ts` — `useDbTables()` (`queryKey:
['dbTables']`, `queryFn: getDbTables`) and `useDbTableRows(name: string,
limit: number, offset: number)` (`queryKey: ['dbTableRows', name, limit,
offset]`, `queryFn: () => getDbTableRows(name, limit, offset)`,
`enabled: name !== ''` or similar — this hook needs a selected table
name before it should fetch anything, see Task 3).

`frontend/src/hooks/useControl.ts` — `useControlStart()` and
`useControlStop()`, both `useMutation` wrapping their client functions.
No automatic query invalidation needed here (Task 6 decides what to
refetch after a control action, if anything — `/status`'s own 10s poll
from Phase 5 will pick up the new state on its own within that window).

- [ ] **Step 5: Run the full test suite**

Run: `npm run test -- --run` — expect all tests (Phase 5's + this task's
new ones) to pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api frontend/src/hooks
git commit -m "feat(frontend): API client, types, and hooks for pricing, db, and control"
```

---

### Task 3: Database page — table list and row browser

**Files:**
- Create: `frontend/src/pages/Database.tsx`
- Test: `frontend/src/pages/Database.test.tsx`
- Modify: `frontend/src/App.tsx` (wire the real `Database` page into the
  `database` tab, replacing Task 1's placeholder)

**Interfaces:**
- Consumes: `useDbTables()`, `useDbTableRows()` from Task 2.
- Produces: `<Database />` (no props).

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/Database.test.tsx`:

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Database } from './Database'

afterEach(() => { vi.restoreAllMocks() })

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

function mockFetchByPath(handlers: Record<string, unknown>) {
  vi.spyOn(global, 'fetch').mockImplementation((input) => {
    const url = String(input)
    for (const [prefix, body] of Object.entries(handlers)) {
      if (url.startsWith(prefix)) {
        return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
      }
    }
    return Promise.reject(new Error(`unexpected fetch: ${url}`))
  })
}

describe('Database', () => {
  it('lists the real table names', async () => {
    mockFetchByPath({ '/db/tables': { tables: ['requests', 'collector_state'] } })
    renderWithClient(<Database />)
    await waitFor(() => expect(screen.getByText('requests')).toBeInTheDocument())
    expect(screen.getByText('collector_state')).toBeInTheDocument()
  })

  it('shows rows for the selected table using the response columns, not hardcoded ones', async () => {
    mockFetchByPath({
      '/db/tables/requests': {
        table: 'requests', total: 1, limit: 50, offset: 0,
        columns: ['request_id', 'provider'],
        rows: [['req-1', 'deepseek']],
      },
      '/db/tables': { tables: ['requests'] },
    })
    renderWithClient(<Database />)
    await waitFor(() => expect(screen.getByText('requests')).toBeInTheDocument())
    await userEvent.click(screen.getByText('requests'))
    await waitFor(() => expect(screen.getByText('req-1')).toBeInTheDocument())
    expect(screen.getByText('deepseek')).toBeInTheDocument()
    expect(screen.getByText('request_id')).toBeInTheDocument()
    expect(screen.getByText('provider')).toBeInTheDocument()
  })

  it('shows an empty-table message when a table has zero rows', async () => {
    mockFetchByPath({
      '/db/tables/collector_state': {
        table: 'collector_state', total: 0, limit: 50, offset: 0,
        columns: ['id', 'last_offset'], rows: [],
      },
      '/db/tables': { tables: ['collector_state'] },
    })
    renderWithClient(<Database />)
    await waitFor(() => expect(screen.getByText('collector_state')).toBeInTheDocument())
    await userEvent.click(screen.getByText('collector_state'))
    await waitFor(() => expect(screen.getByText(/no rows/i)).toBeInTheDocument())
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 2: Implement `Database`**

Write the component: calls `useDbTables()`, renders the table names as
clickable items; tracks the selected table in local `useState<string>`
(empty string = none selected yet); calls `useDbTableRows(selectedTable,
50, 0)` (fixed limit/offset for this task — pagination controls are not
required by the brief and can be left for a future refinement, this page
is explicitly "read-only viewing... not a query builder"); once a table
is selected and its rows load, renders a table with `columns` as the
header row and each entry in `rows` as a body row, zipping by index —
never assume a specific column name or count. Zero rows renders a "No
rows" message instead of an empty table. No table selected yet renders a
neutral prompt (e.g. "Select a table to view its rows").

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Wire into `App.tsx`**

Replace Task 1's `database` tab placeholder with `<Database />`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Database.tsx frontend/src/pages/Database.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): Database page — read-only table browser"
```

---

### Task 4: Settings — pricing config editor (view + manual add/edit)

**Files:**
- Create: `frontend/src/components/PricingEditor.tsx`
- Test: `frontend/src/components/PricingEditor.test.tsx`

**Interfaces:**
- Consumes: `usePricing()`, `usePutPricing()` from Task 2.
- Produces: `<PricingEditor />` (no props). Task 7 mounts this inside the
  full Settings page.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/PricingEditor.test.tsx`:

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PricingEditor } from './PricingEditor'

afterEach(() => { vi.restoreAllMocks() })

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const config = {
  anthropic: {
    opus: { input_per_million: 15, output_per_million: 75 },
    sonnet: { input_per_million: 3, output_per_million: 15 },
    haiku: { input_per_million: 0.25, output_per_million: 1.25 },
  },
  providers: {
    deepseek: { 'deepseek-chat': { input_per_million: 0.27, output_per_million: 1.1 } },
  },
}

describe('PricingEditor', () => {
  it('renders every configured price pair', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(config), { status: 200 }))
    renderWithClient(<PricingEditor />)
    await waitFor(() => expect(screen.getByText('deepseek-chat')).toBeInTheDocument())
    expect(screen.getByText(/opus/i)).toBeInTheDocument()
  })

  it('lets the user add a new (provider, model) price pair and requires confirmation before saving', async () => {
    vi.spyOn(global, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url === '/pricing' && (!init || init.method === undefined)) {
        return Promise.resolve(new Response(JSON.stringify(config), { status: 200 }))
      }
      if (url === '/pricing' && init?.method === 'PUT') {
        return Promise.resolve(new Response(init.body as string, { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected fetch: ${url} ${init?.method}`))
    })
    const user = userEvent.setup()
    renderWithClient(<PricingEditor />)
    await waitFor(() => expect(screen.getByText('deepseek-chat')).toBeInTheDocument())

    await user.type(screen.getByLabelText(/provider/i), 'kimi')
    await user.type(screen.getByLabelText(/model/i), 'kimi-k2')
    await user.type(screen.getByLabelText(/input.*per million/i), '0.6')
    await user.type(screen.getByLabelText(/output.*per million/i), '2.5')
    await user.click(screen.getByRole('button', { name: /save/i }))

    // First click should ask for confirmation, not fire the write yet.
    expect(
      (global.fetch as ReturnType<typeof vi.fn>).mock.calls.some(([, init]) => init?.method === 'PUT'),
    ).toBe(false)

    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() =>
      expect(
        (global.fetch as ReturnType<typeof vi.fn>).mock.calls.some(([, init]) => init?.method === 'PUT'),
      ).toBe(true),
    )
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 2: Implement `PricingEditor`**

Write the component: calls `usePricing()`, renders a table/list of every
`(provider, model)` pair currently configured — the 3 Anthropic tiers
plus everything under `providers` — each row showing
`input_per_million`/`output_per_million`. Below that, a small form (fields
for provider, model, input price, output price — use proper `<label>`
elements associated with each input via `htmlFor`/`id`, since the tests
above use `getByLabelText`) to add or edit one pair. Clicking "Save" does
NOT immediately call the mutation — it flips into a "confirm?" state
(e.g. the button becomes "Confirm", possibly alongside a "Cancel" option)
per the Global Constraints' confirm-before-action rule; only the
follow-up confirm click calls `usePutPricing()`'s mutate function with
the FULL config document (the existing `usePricing()` data, with the new/
edited pair merged in — `PUT /pricing` replaces the whole document, per
`BACKEND--api`, so a partial body would silently delete every other
provider's prices; do not send a partial document under any circumstance).
A pair with no price at all (not present anywhere in the config) should
render as "unknown," not blank or `$0` — this only matters once Task 5 or
future data can produce that state via a name that isn't in `providers`
yet, but keep the display logic correct regardless.

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PricingEditor.tsx frontend/src/components/PricingEditor.test.tsx
git commit -m "feat(frontend): pricing config editor with manual add/edit and confirm-before-save"
```

---

### Task 5: Settings — price-refresh preview-then-approve flow

**Files:**
- Create: `frontend/src/components/PriceRefreshFlow.tsx`
- Test: `frontend/src/components/PriceRefreshFlow.test.tsx`

**Interfaces:**
- Consumes: `usePricingRefresh()`, `usePutPricing()`, `usePricing()` from
  Task 2.
- Produces: `<PriceRefreshFlow />` (no props).

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/PriceRefreshFlow.test.tsx`:

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PriceRefreshFlow } from './PriceRefreshFlow'

afterEach(() => { vi.restoreAllMocks() })

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const diff = {
  changes: [
    { provider: 'openrouter', model: 'kimi-k2', current: { input_per_million: 0.6, output_per_million: 2.5 }, proposed: { input_per_million: 0.55, output_per_million: 2.2 }, source: 'openrouter', changed: true },
  ],
  not_found: [{ provider: 'deepseek', model: 'v3' }],
}

describe('PriceRefreshFlow', () => {
  it('does not write anything just from clicking refresh', async () => {
    const putCalls: unknown[] = []
    vi.spyOn(global, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url === '/pricing/refresh') return Promise.resolve(new Response(JSON.stringify(diff), { status: 200 }))
      if (url === '/pricing' && init?.method === 'PUT') { putCalls.push(init); return Promise.resolve(new Response('{}', { status: 200 })) }
      if (url === '/pricing') return Promise.resolve(new Response(JSON.stringify({ anthropic: {}, providers: {} }), { status: 200 }))
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })
    const user = userEvent.setup()
    renderWithClient(<PriceRefreshFlow />)
    await user.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(screen.getByText('kimi-k2')).toBeInTheDocument())
    expect(screen.getByText(/not found|deepseek/i)).toBeInTheDocument()
    expect(putCalls).toHaveLength(0)
  })

  it('writes the approved diff only after explicit approval', async () => {
    const putCalls: unknown[] = []
    vi.spyOn(global, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url === '/pricing/refresh') return Promise.resolve(new Response(JSON.stringify(diff), { status: 200 }))
      if (url === '/pricing' && init?.method === 'PUT') { putCalls.push(init); return Promise.resolve(new Response('{}', { status: 200 })) }
      if (url === '/pricing') return Promise.resolve(new Response(JSON.stringify({ anthropic: {}, providers: {} }), { status: 200 }))
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })
    const user = userEvent.setup()
    renderWithClient(<PriceRefreshFlow />)
    await user.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(screen.getByText('kimi-k2')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /apply/i }))
    await waitFor(() => expect(putCalls).toHaveLength(1))
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 2: Implement `PriceRefreshFlow`**

Write the component: a "Refresh prices" button that calls
`usePricingRefresh()`'s mutate function. Once a result is present, render
`changes` (each row: provider, model, current vs. proposed, source) and
`not_found` (each pair, clearly marked as not found — this is exactly
`PRICING-ENGINE--price-refresh`'s "left as unknown for manual entry, not
guessed" case, so no price should ever be invented for these). An "Apply"
button (this IS the confirm-before-action step per the Global
Constraints — reviewing a concrete diff and clicking Apply is the
required confirmation, no additional double-click needed here unlike
Task 4's blind manual-entry form) that, on click, builds the full,
updated config document by taking `usePricing()`'s current data and
merging in every `changes[i].proposed` value (only the `changed: true`
ones need to actually differ, but merging all of `changes` — even a
`changed: false` "no-op" entry — is harmless and simpler than filtering),
then calls `usePutPricing()`'s mutate function with that full document —
never a partial one. Not-found pairs are never written (there's nothing
to write for them — that's the whole point of `not_found`).

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PriceRefreshFlow.tsx frontend/src/components/PriceRefreshFlow.test.tsx
git commit -m "feat(frontend): price-refresh preview-then-approve flow"
```

---

### Task 6: Settings — FCC start/stop controls

**Files:**
- Create: `frontend/src/components/ProcessControls.tsx`
- Test: `frontend/src/components/ProcessControls.test.tsx`

**Interfaces:**
- Consumes: `useControlStart()`, `useControlStop()` from Task 2.
- Produces: `<ProcessControls />` (no props).

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/ProcessControls.test.tsx`:

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProcessControls } from './ProcessControls'

afterEach(() => { vi.restoreAllMocks() })

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('ProcessControls', () => {
  it('requires confirmation before starting FCC', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ action: 'started', pid: 4242 }), { status: 200 }),
    )
    const user = userEvent.setup()
    renderWithClient(<ProcessControls />)
    await user.click(screen.getByRole('button', { name: /^start/i }))
    expect(global.fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/control/start', { method: 'POST' }))
    await waitFor(() => expect(screen.getByText(/started/i)).toBeInTheDocument())
  })

  it('requires confirmation before stopping FCC', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ action: 'stopped', pid: 4242 }), { status: 200 }),
    )
    const user = userEvent.setup()
    renderWithClient(<ProcessControls />)
    await user.click(screen.getByRole('button', { name: /^stop/i }))
    expect(global.fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/control/stop', { method: 'POST' }))
  })

  it('shows a clear message for executable_not_found without treating it as an error', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ action: 'executable_not_found', pid: null }), { status: 200 }),
    )
    const user = userEvent.setup()
    renderWithClient(<ProcessControls />)
    await user.click(screen.getByRole('button', { name: /^start/i }))
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() => expect(screen.getByText(/not found|not installed/i)).toBeInTheDocument())
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 2: Implement `ProcessControls`**

Write the component: both the "Start" button and the "Stop" button go
through the same confirm-before-action pattern as Task 4's save button
(first click shows a "Confirm" option next to/instead of the original
button, only that second click actually calls `useControlStart()`'s or
`useControlStop()`'s mutate function respectively) — per the Global
Constraints, `FRONTEND--settings.md` requires this for both actions, not
just stop. After either mutation resolves, render the returned `action`
as a human-readable status message — `started`/`already_running`/
`executable_not_found`/`launch_failed` for start, `stopped`/
`not_running`/`stop_failed` for stop — each with wording appropriate to
what actually happened (e.g. `executable_not_found` should read as "FCC
isn't installed" or similar, not as a generic failure — this is a normal,
expected `200` outcome per `BACKEND--api`, not an error state).

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ProcessControls.tsx frontend/src/components/ProcessControls.test.tsx
git commit -m "feat(frontend): FCC start/stop controls with confirm-before-stop"
```

---

### Task 7: Settings page composition, App wiring, end-to-end verification

**Files:**
- Create: `frontend/src/pages/Settings.tsx`
- Test: `frontend/src/pages/Settings.test.tsx`
- Modify: `frontend/src/App.tsx` (wire the real `Settings` page into the
  `settings` tab, replacing Task 1's placeholder)

**Interfaces:**
- Consumes: `PricingEditor` (Task 4), `PriceRefreshFlow` (Task 5),
  `ProcessControls` (Task 6) — pure composition, no new fetching.
- Produces: the finished Settings page.

- [ ] **Step 1: Write the failing composition test**

`frontend/src/pages/Settings.test.tsx` — follow the exact pattern
Phase 5's `Overview.test.tsx` used (a `mockImplementation` that routes by
URL prefix across `/pricing`, `/pricing/refresh` if triggered,
`/control/*` if triggered), asserting all three sub-components' key
content is reachable on the page (e.g. the pricing table renders, the
"Refresh prices" button exists, the "Start"/"Stop" buttons exist).

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 2: Implement `Settings`**

`frontend/src/pages/Settings.tsx` — renders `<PricingEditor />`,
`<PriceRefreshFlow />`, and `<ProcessControls />` together (layout is your
call — grouping process controls visually apart from the pricing tools is
reasonable given they're unrelated actions, but not required).

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Wire into `App.tsx`**

Replace Task 1's `settings` tab placeholder with `<Settings />`.

- [ ] **Step 4: Full regression run**

Run: `npm run test -- --run` (expect every test across the whole plan —
Phase 5's plus this plan's — to pass) and `npx tsc -b` (expect clean).

- [ ] **Step 5: Manual end-to-end verification against the real backend**

Same shape as Phase 5's Task 6 verification — start the real backend
(`uv run fcc-dashboard-server` from `backend/`) and the frontend dev
server (`npm run dev` from `frontend/`), then exercise, at minimum:
`GET /pricing` renders real data (or the seeded Anthropic defaults on a
fresh install) in the pricing table; `GET /db/tables` lists real tables
and clicking one shows real rows (or "No rows" on an empty table);
`POST /control/start` / `POST /control/stop` actually work against a real
`fcc-server` if one is installed on the machine running this verification
— if `fcc-server` isn't installed, confirm `executable_not_found` renders
correctly instead, which is itself a valid, complete verification of that
path. If no browser tool is available in your environment, adapt via
curl the same way Phase 5's Task 6 did (proxied vs. direct calls,
cross-checked against the backend's own access log) — record whichever
method you used and what you actually observed in your report.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Settings.tsx frontend/src/pages/Settings.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): compose the Settings page and wire it into App"
```
