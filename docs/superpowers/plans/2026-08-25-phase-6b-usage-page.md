# Phase 6b — Usage Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the fourth and final dashboard page — Usage — completing
`FRONTEND--architecture`'s 4-page design. This plan starts with a small,
deliberate backend extension (Task 1) that was found missing while
planning Phase 6a: `GET /stats` had no way to answer "how much was each
provider/model actually used," only "how much did each provider save me."

**Architecture:** Task 1 extends `GET /stats` with two new aggregate
fields, `volume_by_provider` and `volume_by_model` — computed over ALL
rows in range regardless of status/pricing (mirroring the endpoint's
existing `total_requests`/`total_input_tokens` aggregation style, not
`by_provider`'s priced-only style). Tasks 2-4 build the frontend page
against that extended contract: a range selector, two bar charts
(Recharts — installed in Phase 5, unused until now), composed into the
Usage page.

**Tech Stack:** Same as Phases 5-6a (React 19, TypeScript, TanStack
Query v5, Recharts, Tailwind v4, Vitest + React Testing Library) plus
Python/FastAPI/pytest for Task 1's backend work.

**Spec:** `vault-fcc-dashboard/plans/PHASE-6-FRONTEND-REMAINING-PAGES.md`
(scope — this plan covers Usage, the third of Phase 6's original three
pages), `vault-fcc-dashboard/features/FRONTEND/FRONTEND--usage.md`,
`FRONTEND--technologies.md`, `vault-fcc-dashboard/features/BACKEND/BACKEND--api.md`
(both already updated to describe the extended `/stats` contract — read
the `volume_by_provider`/`volume_by_model` entries there before writing
any code), `vault-fcc-dashboard/features/DATE-TIME/DATE-TIME--resilience.md`.

## Global Constraints

- **`volume_by_provider`/`volume_by_model` are NOT the same aggregate as
  the existing `by_provider` field.** `by_provider` only counts
  `completed`, priced rows (it answers a money question). The new
  volume fields count every row in range with a non-NULL grouping key,
  regardless of status or pricing (they answer a usage question). Do
  not merge, replace, or reuse `by_provider`'s existing aggregation
  logic for the new fields — write a separate aggregation pass, mirroring
  `total_requests`/`total_input_tokens`'s existing all-rows style instead.
- **`model` in `volume_by_model` means `downstream_model`** (the real
  model FCC routed a request to), never `gateway_model` (the intercepted
  Anthropic tier) — consistent with `by_provider`'s own `provider`
  field already meaning the real routing provider, not anything
  gateway-side.
- **Rows with a NULL grouping key are excluded, not bucketed as
  "unknown."** A row with `provider IS NULL` doesn't appear in
  `volume_by_provider`; a row with `downstream_model IS NULL` (even if
  `provider` is known) doesn't appear in `volume_by_model`. There's
  nothing meaningful to group them under — this mirrors
  `routes_status.py`'s existing `WHERE provider IS NOT NULL` pattern for
  the same reason.
- **`estimated_count` is a per-bucket rollup, not per-row marking.**
  Since usage data is aggregated into chart bars (not plotted per
  individual request), the estimated-timestamp acknowledgement required
  by `FRONTEND--usage` happens at the bucket level: each
  `volume_by_provider`/`volume_by_model` entry carries a count of how
  many of ITS rows have `occurred_at_is_estimated = 1`.
- **Relative URLs only, everywhere in the frontend API client** — same
  rule as Phases 5-6a. This task doesn't add a new client function
  (`getStats` already exists from Phase 5), only extends its response
  type — but any new code added anywhere in this plan still follows
  the rule.
- **No new client-side state library.** The range selector's selected
  value is local component state, same as every other piece of UI state
  in this codebase so far.
- **Tests mock at the `fetch` boundary** (frontend) / use the existing
  `client_and_db` fixture pattern (backend) — matching every prior
  phase's established convention exactly, not inventing a new one.

---

### Task 1: Backend — extend `GET /stats` with volume-by-provider and volume-by-model

**Files:**
- Modify: `backend/src/fcc_dashboard/routes_stats.py`
- Test: `backend/tests/test_routes_stats.py` (extend the existing file)

**Interfaces:**
- Consumes: nothing new — same `_fetch_rows_in_range` result the
  existing aggregation already computes from.
- Produces: `StatsResponse.volume_by_provider: list[ByProviderVolume]`
  and `StatsResponse.volume_by_model: list[ByModelVolume]`. Task 2
  mirrors these two Pydantic models field-for-field into the frontend's
  `types.ts`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_routes_stats.py`, following the existing
file's `client_and_db` fixture and `_insert_completed` helper exactly
(add a second helper if you need rows with a different `status`, e.g.
`_insert_pending`/`_insert_error`, following the same pattern as
`_insert_completed` — read `backend/src/fcc_dashboard/db.py`'s schema if
you need the exact column list):

```python
def test_volume_by_provider_counts_all_rows_regardless_of_pricing_or_status(client_and_db):
    client, db = client_and_db
    # Priced, completed.
    _insert_completed(db, "req_1", "nvidia_nim", "sonnet", "glm-4",
                       1_000_000, 1_000_000, "2026-08-24T10:00:00.000Z")
    # Same provider, UNPRICED downstream model -- by_provider would skip
    # this row entirely; volume_by_provider must still count it.
    _insert_completed(db, "req_2", "nvidia_nim", "sonnet", "some-unpriced-model",
                       500_000, 500_000, "2026-08-24T11:00:00.000Z")
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    volume = {row["provider"]: row for row in body["volume_by_provider"]}
    assert volume["nvidia_nim"]["request_count"] == 2
    assert volume["nvidia_nim"]["input_tokens"] == 1_500_000
    assert volume["nvidia_nim"]["output_tokens"] == 1_500_000
    # by_provider (the savings-only breakdown) should still only see the
    # one priced row -- confirms the two aggregates are genuinely
    # independent, not accidentally sharing a filter.
    by_provider_savings = {row["provider"]: row for row in body["by_provider"]}
    assert by_provider_savings["nvidia_nim"]["request_count"] == 1


def test_volume_by_provider_excludes_null_provider_rows(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, occurred_at, ingested_at, status) "
        "VALUES ('req_orphan', NULL, '2026-08-24T10:00:00.000Z', "
        "'2026-08-24T10:00:00.000Z', 'pending')"
    )
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    assert body["volume_by_provider"] == []


def test_volume_by_model_groups_by_provider_and_downstream_model(client_and_db):
    client, db = client_and_db
    _insert_completed(db, "req_1", "nvidia_nim", "sonnet", "glm-4",
                       1_000_000, 1_000_000, "2026-08-24T10:00:00.000Z")
    _insert_completed(db, "req_2", "openrouter", "sonnet", "glm-4",
                       200_000, 200_000, "2026-08-24T11:00:00.000Z")
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    assert len(body["volume_by_model"]) == 2
    keyed = {(row["provider"], row["model"]): row for row in body["volume_by_model"]}
    assert keyed[("nvidia_nim", "glm-4")]["request_count"] == 1
    assert keyed[("openrouter", "glm-4")]["request_count"] == 1


def test_volume_by_model_excludes_rows_with_null_downstream_model(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, downstream_model, occurred_at, "
        "ingested_at, status) VALUES "
        "('req_orphan', 'nvidia_nim', NULL, '2026-08-24T10:00:00.000Z', "
        "'2026-08-24T10:00:00.000Z', 'pending')"
    )
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    assert body["volume_by_model"] == []


def test_volume_estimated_count_reflects_estimated_timestamp_rows(client_and_db):
    client, db = client_and_db
    db.execute(
        "INSERT INTO requests (request_id, provider, downstream_model, occurred_at, "
        "occurred_at_is_estimated, ingested_at, status) VALUES "
        "('req_est', 'nvidia_nim', 'glm-4', '2026-08-24T10:00:00.000Z', 1, "
        "'2026-08-24T10:00:00.000Z', 'pending')"
    )
    _insert_completed(db, "req_real", "nvidia_nim", "sonnet", "glm-4",
                       100, 100, "2026-08-24T11:00:00.000Z")
    db.commit()

    response = client.get("/stats?range=last_7_days")
    body = response.json()

    provider_entry = next(r for r in body["volume_by_provider"] if r["provider"] == "nvidia_nim")
    assert provider_entry["request_count"] == 2
    assert provider_entry["estimated_count"] == 1

    model_entry = next(r for r in body["volume_by_model"] if r["model"] == "glm-4")
    assert model_entry["estimated_count"] == 1
```

Run: `uv run pytest tests/test_routes_stats.py -v` (from `backend/`) —
expect the 5 new tests to FAIL (fields don't exist yet on the response).

- [ ] **Step 2: Add the two new Pydantic models and extend `StatsResponse`**

In `backend/src/fcc_dashboard/routes_stats.py`, add:

```python
class ByProviderVolume(BaseModel):
    provider: str
    request_count: int
    input_tokens: int
    output_tokens: int
    estimated_count: int


class ByModelVolume(BaseModel):
    provider: str
    model: str
    request_count: int
    input_tokens: int
    output_tokens: int
    estimated_count: int
```

Add two fields to the existing `StatsResponse` class:
`volume_by_provider: list[ByProviderVolume]` and
`volume_by_model: list[ByModelVolume]`.

- [ ] **Step 3: Write the aggregation function**

Write a new function, `_aggregate_volume(rows: list[sqlite3.Row]) ->
tuple[list[ByProviderVolume], list[ByModelVolume]]`, next to the
existing `_aggregate_costs` function (don't modify `_aggregate_costs`
itself — it stays exactly as it is, still `by_provider`'s own
savings-only pass). This function iterates `rows` ONCE and builds both
breakdowns in the same pass (two dicts, keyed by `provider` and by
`(provider, downstream_model)` respectively):

- Skip a row from the provider breakdown if `row["provider"] is None`.
- Skip a row from the model breakdown if `row["provider"] is None` OR
  `row["downstream_model"] is None`.
- A row that's skipped from one breakdown can still count in the other
  (e.g. a row with a real `provider` but `NULL` `downstream_model`
  counts in `volume_by_provider` but not `volume_by_model`).
- For each counted row: increment that bucket's `request_count`; add
  `row["input_tokens"]`/`row["output_tokens"]` to the running totals
  ONLY if they're not `None` (same `is not None` guard the existing
  `total_input_tokens`/`total_output_tokens` aggregation already uses —
  don't let a `NULL` token count silently become a Python `TypeError` or
  get coerced into `0` in a way that misrepresents "we don't know" as
  "zero tokens used"); increment `estimated_count` if
  `row["occurred_at_is_estimated"]` is truthy (it's a raw SQLite
  `0`/`1` integer, same as the frontend's own handling of this column in
  Phase 5).
- Sort both output lists deterministically — `volume_by_provider` by
  `provider` name, `volume_by_model` by `(provider, model)` — matching
  `_aggregate_costs`' own `sorted(by_provider.items())` pattern, for a
  stable response across runs.

- [ ] **Step 4: Wire the new aggregation into `get_stats`**

Call `_aggregate_volume(rows)` alongside the existing
`_aggregate_costs(rows, pricing_config)` call in the `get_stats` handler
(both the success path and the "no pricing config file yet" early-return
path — the volume breakdown doesn't depend on pricing being configured
at all, so it must still populate correctly even when `total_savings`
comes back `null`). Add `volume_by_provider=...`/`volume_by_model=...`
to both `StatsResponse(...)` construction sites in this function.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_routes_stats.py -v` (from `backend/`) —
expect all tests (existing + 5 new) to PASS. Then run the full backend
suite: `uv run pytest` (from `backend/`) — expect no regressions (134
tests before this task).

- [ ] **Step 6: Commit**

```bash
git add backend/src/fcc_dashboard/routes_stats.py backend/tests/test_routes_stats.py
git commit -m "feat(backend): add volume_by_provider/volume_by_model to GET /stats"
```

---

### Task 2: Frontend — extended types, range selector, and Usage page skeleton

**Files:**
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/components/RangeSelector.tsx`
- Test: `frontend/src/components/RangeSelector.test.tsx`
- Create: `frontend/src/pages/Usage.tsx` (skeleton only — Task 3 adds
  the actual charts)
- Test: `frontend/src/pages/Usage.test.tsx`

**Interfaces:**
- Consumes: `useStats(range)` (already exists, from Phase 5) — no new
  hook needed, only its response TYPE is extended.
- Produces: `RangeName` type (`'today' | 'last_7_days' | 'last_30_days'
  | 'all_time'` — mirror `backend/src/fcc_dashboard/routes_stats.py`'s
  `RangeName` enum exactly, don't invent different values),
  `<RangeSelector value={...} onChange={...} />`, and a `Usage` page
  that manages the selected range in local state and passes it to
  `useStats(range)`. Task 3 mounts the actual chart components inside
  this page, consuming the same `useStats(range)` result this task
  already wires up.

- [ ] **Step 1: Extend `types.ts`**

Add to `frontend/src/api/types.ts`:

```ts
export type RangeName = 'today' | 'last_7_days' | 'last_30_days' | 'all_time'

export interface ByProviderVolume {
  provider: string
  request_count: number
  input_tokens: number
  output_tokens: number
  estimated_count: number
}

export interface ByModelVolume {
  provider: string
  model: string
  request_count: number
  input_tokens: number
  output_tokens: number
  estimated_count: number
}
```

Add `volume_by_provider: ByProviderVolume[]` and
`volume_by_model: ByModelVolume[]` to the existing `StatsResponse`
interface — do not otherwise change `StatsResponse` or `ByProviderStats`
(the existing savings-only type stays exactly as it is).

- [ ] **Step 2: Write the failing `RangeSelector` tests**

`frontend/src/components/RangeSelector.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RangeSelector } from './RangeSelector'

describe('RangeSelector', () => {
  it('renders all 4 range options', () => {
    render(<RangeSelector value="last_7_days" onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /today/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /last 7 days/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /last 30 days/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /all time/i })).toBeInTheDocument()
  })

  it('calls onChange with the clicked range', async () => {
    const onChange = vi.fn()
    render(<RangeSelector value="last_7_days" onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: /last 30 days/i }))
    expect(onChange).toHaveBeenCalledWith('last_30_days')
  })

  it('visually distinguishes the selected range', () => {
    render(<RangeSelector value="today" onChange={vi.fn()} />)
    const active = screen.getByRole('button', { name: /^today$/i })
    const inactive = screen.getByRole('button', { name: /last 7 days/i })
    expect(active.className).not.toBe(inactive.className)
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 3: Implement `RangeSelector`**

`frontend/src/components/RangeSelector.tsx` — 2 props, `value: RangeName`
and `onChange: (range: RangeName) => void`. 4 buttons with human-readable
labels ("Today", "Last 7 days", "Last 30 days", "All time"), calling
`onChange` with the matching `RangeName` value on click, active one
styled distinctly (same pattern as Phase 6a's `Nav.tsx` — active vs.
inactive Tailwind classes).

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 4: Write the failing `Usage` page skeleton test**

`frontend/src/pages/Usage.test.tsx`:

```tsx
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Usage } from './Usage'

afterEach(() => { vi.restoreAllMocks() })

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const emptyStats = {
  range: 'last_7_days', range_start: 'x', range_end: 'y',
  total_requests: 0, completed_requests: 0, error_requests: 0, pending_requests: 0,
  total_input_tokens: 0, total_output_tokens: 0, total_savings: null,
  unpriced_request_count: 0, by_provider: [], volume_by_provider: [], volume_by_model: [],
}

describe('Usage', () => {
  it('re-fetches stats with the newly selected range on click', async () => {
    const calls: string[] = []
    vi.spyOn(global, 'fetch').mockImplementation((input) => {
      calls.push(String(input))
      return Promise.resolve(new Response(JSON.stringify(emptyStats), { status: 200 }))
    })
    const user = userEvent.setup()
    renderWithClient(<Usage />)
    await waitFor(() => expect(calls.some((u) => u.includes('range=last_7_days'))).toBe(true))
    await user.click(screen.getByRole('button', { name: /last 30 days/i }))
    await waitFor(() => expect(calls.some((u) => u.includes('range=last_30_days'))).toBe(true))
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 5: Implement the `Usage` page skeleton**

`frontend/src/pages/Usage.tsx` — local `useState<RangeName>('last_7_days')`
(defaulting to the same range Overview's `MoneySavedHeadline` uses, for
consistency), renders `<RangeSelector value={range} onChange={setRange} />`
and calls `useStats(range)` itself (this page owns the range and the
query — Task 3's chart components will be simple, prop-driven, NOT
self-fetching, unlike every component in Phases 5-6a so far: charts
need to share the SAME `useStats(range)` result the range selector just
changed, rather than each independently calling `useStats` with a range
they'd have no way to know about). For this task, just render a
placeholder below the selector (e.g. `<div>Charts coming in Task 3</div>`)
where the real charts will go.

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 6: Wire into `App.tsx`**

Replace the `usage` tab's placeholder (`<div>Usage — coming soon</div>`,
from Phase 6a's Task 1) with `<Usage />`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/components/RangeSelector.tsx frontend/src/components/RangeSelector.test.tsx frontend/src/pages/Usage.tsx frontend/src/pages/Usage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): range selector and Usage page skeleton"
```

---

### Task 3: Frontend — volume charts (by provider, by model)

**Files:**
- Create: `frontend/src/components/VolumeChart.tsx`
- Test: `frontend/src/components/VolumeChart.test.tsx`
- Modify: `frontend/src/pages/Usage.tsx` (mount the real charts,
  replacing Task 2's placeholder)
- Modify: `frontend/src/pages/Usage.test.tsx` (extend, don't rewrite —
  read it first)

**Interfaces:**
- Consumes: `ByProviderVolume[]` / `ByModelVolume[]` (from Task 1/2's
  extended `StatsResponse`).
- Produces: `<VolumeChart data={...} groupLabel={...} />` — a single,
  reusable component parameterized by which breakdown it's showing (NOT
  two separate near-duplicate components — provider and model volumes
  share the same shape: a label, `request_count`, `input_tokens`,
  `output_tokens`, `estimated_count`).

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/VolumeChart.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { VolumeChart } from './VolumeChart'

const data = [
  { label: 'deepseek', request_count: 10, input_tokens: 1000, output_tokens: 2000, estimated_count: 0 },
  { label: 'openrouter', request_count: 3, input_tokens: 300, output_tokens: 400, estimated_count: 2 },
]

describe('VolumeChart', () => {
  it('renders a bar chart with a bar per entry', () => {
    render(<VolumeChart data={data} groupLabel="Provider" />)
    // Recharts renders SVG; assert on data presence via accessible text
    // (a legend/axis label or a rendered data table fallback), not on
    // SVG internals -- your call how you expose this, but it must be
    // genuinely observable in the DOM, not just "the SVG exists."
    expect(screen.getByText('deepseek')).toBeInTheDocument()
    expect(screen.getByText('openrouter')).toBeInTheDocument()
  })

  it('marks an entry with a nonzero estimated_count as having estimated timestamps, scoped to that entry', () => {
    render(<VolumeChart data={data} groupLabel="Provider" />)
    // Each entry must be wrapped in its own accessible list item (or
    // equivalent container) carrying its label as accessible text, so
    // the estimated marker can be looked up scoped to ONE entry rather
    // than searched for anywhere on the page.
    const openrouterItem = screen.getByRole('listitem', { name: /openrouter/i })
    expect(within(openrouterItem).getByText(/2.*estimated/i)).toBeInTheDocument()
  })

  it('does not mark an entry with zero estimated_count', () => {
    render(<VolumeChart data={data} groupLabel="Provider" />)
    const deepseekItem = screen.getByRole('listitem', { name: /deepseek/i })
    expect(within(deepseekItem).queryByText(/estimated/i)).not.toBeInTheDocument()
  })

  it('renders a neutral message when data is empty', () => {
    render(<VolumeChart data={[]} groupLabel="Provider" />)
    expect(screen.getByText(/no data|no usage/i)).toBeInTheDocument()
  })
})
```

Run: `npm run test -- --run` — expect FAIL.

- [ ] **Step 2: Implement `VolumeChart`**

`frontend/src/components/VolumeChart.tsx` — props: `data: Array<{ label:
string; request_count: number; input_tokens: number; output_tokens:
number; estimated_count: number }>` and `groupLabel: string` (used as a
heading, e.g. "By Provider" / "By Model"). Empty `data` renders a
neutral "No usage data for this range" message instead of an empty
chart. Otherwise renders a Recharts `BarChart` (`import { BarChart, Bar,
XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'` — this is
the first real use of Recharts in this codebase; read its docs/types as
needed, this project has no established pattern to copy yet) showing
`request_count` per entry (your call whether to also chart tokens, e.g.
as a second bar or a toggle — the brief's tests only require
`request_count` and the estimated marker to be verifiably present, but
`FRONTEND--usage` asks for BOTH token and call volume, so include token
volume somewhere in the rendered output too — a second chart, a toggle,
or a per-bar tooltip breakdown are all reasonable, your call). Below or
alongside the chart, render each entry in its own `<li>` (inside a `<ul>`
or `<ol>`, giving the tests above a real `role="listitem"` to query),
with the entry's `label` as its accessible name/visible text (for the
chart to be meaningfully testable and accessible, not just an opaque
SVG), and for any entry with `estimated_count > 0`, render a marker
inside that SAME `<li>` containing both the count and the word
"estimated" (e.g. "2 estimated") — never rendered outside that entry's
own list item, so the marker is genuinely scoped per-entry, not a
page-global note.

Note: the Task 2 skeleton's props for the two callers (provider volume
vs. model volume) won't have a `label` field directly — `ByProviderVolume`
has `provider`, `ByModelVolume` has `provider` AND `model`. Map each to
this component's generic `{ label, ... }` shape at the call site in
`Usage.tsx` (Step 3 below) — e.g. `provider` alone for the provider
chart, `` `${provider} / ${model}` `` for the model chart — rather than
making `VolumeChart` itself aware of two different backend shapes.

Run: `npm run test -- --run` — expect PASS.

- [ ] **Step 3: Mount both charts in `Usage.tsx`**

Replace Task 2's placeholder with two `<VolumeChart />` instances, one
fed `data.volume_by_provider.map(v => ({ label: v.provider, ...v }))`
with `groupLabel="By Provider"`, the other fed
`data.volume_by_model.map(v => ({ label: \`${v.provider} / ${v.model}\`, ...v }))`
with `groupLabel="By Model"` — both driven by the SAME `useStats(range)`
result this page already holds from Task 2 (no new fetching). Handle
`isLoading`/`isError` from that single `useStats(range)` call sensibly
(a loading state while fetching, an error message on failure — same
panel-local-error pattern Phase 5's final-review fix established for
`MoneySavedHeadline`/`RecentRequestsFeed`, not a page-level crash).

- [ ] **Step 4: Extend the `Usage.test.tsx` composition test**

Add a test asserting that once stats load, both chart sections are
present (e.g. assert on both "By Provider" and "By Model" headings, and
at least one provider/model label from fixture data) — read the existing
Task 2 test first and extend the file, don't replace its existing test.

- [ ] **Step 5: Run the full test suite**

Run: `npm run test -- --run` (expect all Phase 5 + Phase 6a + this
plan's tests to pass) and `npx tsc -b` (expect clean).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/VolumeChart.tsx frontend/src/components/VolumeChart.test.tsx frontend/src/pages/Usage.tsx frontend/src/pages/Usage.test.tsx
git commit -m "feat(frontend): volume-by-provider and volume-by-model bar charts"
```

---

### Task 4: End-to-end verification and final polish

**Files:**
- No new files expected — this task is verification-first; only touch
  something if the verification step actually surfaces a real bug.

- [ ] **Step 1: Full regression run**

From `frontend/`: `npm run test -- --run`, `npx tsc -b`, `npm run lint`.
From `backend/`: `uv run pytest`. All must be clean.

- [ ] **Step 2: Manual end-to-end verification against the real backend**

Same adapted approach as Phases 5 and 6a's precedent (curl through the
Vite proxy, cross-checked against a direct backend call and the
backend's own access log, if no interactive browser is available in
your environment):

1. Start the real backend (`uv run fcc-dashboard-server` from
   `backend/`) and frontend dev server (`npm run dev` from `frontend/`).
2. `curl -s http://localhost:5173/stats?range=last_7_days` — confirm the
   response includes real, well-formed `volume_by_provider` and
   `volume_by_model` arrays (empty arrays on a fresh install are a valid,
   correct result — not a failure).
3. `curl -s http://localhost:5173/stats?range=all_time` — confirm the
   `range` selector's values genuinely reach the backend correctly (all
   4 `RangeName` values, not just the default).
4. If a browser tool is available, additionally open the dev URL,
   navigate to the Usage tab, click through all 4 range options, and
   visually confirm both charts update. If not, the curl-based proof
   above is the required minimum — record exactly what you did either
   way.
5. Kill both background processes cleanly when done.

- [ ] **Step 3: Report**

Record what you actually observed in your report — this is the plan's
final "verifiable" acceptance criterion, and also completes
`PHASE-6-FRONTEND-REMAINING-PAGES.md`'s original "all 4 pages functional
end to end" criterion across both 6a and 6b.
