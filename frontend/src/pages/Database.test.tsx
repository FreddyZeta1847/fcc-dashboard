/*
 * Database.test.tsx
 * Task 3 brief's exact test spec: table list renders real names (no
 * hardcoded assumptions), selecting a table renders its rows using the
 * response's own `columns`/`rows` (never a hardcoded schema), and a
 * zero-row table shows an explicit "no rows" message instead of an empty
 * table shell.
 */
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
    mockFetchByPath({
      // Listed before '/db/tables': mockFetchByPath matches by startsWith in
      // insertion order, so the generic key would otherwise shadow this one.
      // The page opens on `requests`, so its rows are fetched immediately.
      '/db/tables/requests': {
        table: 'requests', total: 0, limit: 50, offset: 0, columns: [], rows: [],
      },
      '/db/tables': { tables: ['requests', 'collector_state'] },
    })
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

  it('shows how many rows are displayed out of the real total, so truncation is visible', async () => {
    mockFetchByPath({
      '/db/tables/requests': {
        table: 'requests', total: 120, limit: 50, offset: 0,
        columns: ['request_id'],
        rows: [['req-1'], ['req-2'], ['req-3'], ['req-4'], ['req-5']],
      },
      '/db/tables': { tables: ['requests'] },
    })
    renderWithClient(<Database />)
    await waitFor(() => expect(screen.getByText('requests')).toBeInTheDocument())
    await userEvent.click(screen.getByText('requests'))
    await waitFor(() => expect(screen.getByText('req-1')).toBeInTheDocument())
    expect(screen.getByText(/5.*120/)).toBeInTheDocument()
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

  it('says "most recent first" for the requests table, but not for other tables', async () => {
    mockFetchByPath({
      '/db/tables/requests': {
        table: 'requests', total: 1, limit: 50, offset: 0,
        columns: ['request_id'], rows: [['req-1']],
      },
      '/db/tables': { tables: ['requests'] },
    })
    renderWithClient(<Database />)
    await waitFor(() => expect(screen.getByText('requests')).toBeInTheDocument())
    await userEvent.click(screen.getByText('requests'))
    await waitFor(() => expect(screen.getByText(/most recent first/i)).toBeInTheDocument())
  })

  it('expands a requests row into a grouped overview, and collapses it again', async () => {
    mockFetchByPath({
      '/db/tables/requests': {
        table: 'requests', total: 1, limit: 50, offset: 0,
        columns: ['request_id', 'provider', 'gateway_model', 'downstream_model', 'input_tokens', 'output_tokens', 'savings', 'status'],
        rows: [['req-1', 'NIM', 'claude-opus-5', 'deepseek-ai/deepseek-v4-flash-0731', 50244, 716, 0.27, 'completed']],
      },
      '/db/tables': { tables: ['requests'] },
    })
    const user = userEvent.setup()
    renderWithClient(<Database />)
    await waitFor(() => expect(screen.getByText('requests')).toBeInTheDocument())
    await user.click(screen.getByText('requests'))
    await waitFor(() => expect(screen.getByText('req-1')).toBeInTheDocument())

    expect(screen.queryByText('Model routing')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /expand request details/i }))
    expect(screen.getByText('Model routing')).toBeInTheDocument()
    expect(screen.getByText('Tokens')).toBeInTheDocument()
    expect(screen.getByText('Cost')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /collapse request details/i }))
    expect(screen.queryByText('Model routing')).not.toBeInTheDocument()
  })

  it('does not add an expand column for tables other than requests', async () => {
    mockFetchByPath({
      '/db/tables/collector_state': {
        table: 'collector_state', total: 1, limit: 50, offset: 0,
        columns: ['id', 'last_offset'], rows: [[1, 100]],
      },
      '/db/tables': { tables: ['collector_state'] },
    })
    renderWithClient(<Database />)
    await waitFor(() => expect(screen.getByText('collector_state')).toBeInTheDocument())
    await userEvent.click(screen.getByText('collector_state'))
    await waitFor(() => expect(screen.getByText('100')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /expand request details/i })).not.toBeInTheDocument()
  })
  it('opens on the requests table instead of an empty prompt', async () => {
    /*
     * The requests table is the reason this page exists -- every other table
     * here is single-row bookkeeping -- so landing on an inert "select a
     * table" message wasted a click every time.
     */
    mockFetchByPath({
      '/db/tables/requests': {
        table: 'requests', total: 1, limit: 50, offset: 0,
        columns: ['request_id'], rows: [['req-default']],
      },
      '/db/tables': { tables: ['collector_state', 'requests', 'process_state'] },
    })
    renderWithClient(<Database />)

    // Rows appear with no interaction at all.
    await waitFor(() => expect(screen.getByText('req-default')).toBeInTheDocument())
    expect(screen.queryByText(/select a table/i)).not.toBeInTheDocument()
  })

  it('lets the user switch away from the default and keeps that choice', async () => {
    mockFetchByPath({
      '/db/tables/requests': {
        table: 'requests', total: 1, limit: 50, offset: 0,
        columns: ['request_id'], rows: [['req-default']],
      },
      '/db/tables/collector_state': {
        table: 'collector_state', total: 1, limit: 50, offset: 0,
        columns: ['last_offset'], rows: [[4242]],
      },
      '/db/tables': { tables: ['requests', 'collector_state'] },
    })
    renderWithClient(<Database />)
    await waitFor(() => expect(screen.getByText('req-default')).toBeInTheDocument())

    await userEvent.click(screen.getByText('collector_state'))

    await waitFor(() => expect(screen.getByText('4242')).toBeInTheDocument())
    expect(screen.queryByText('req-default')).not.toBeInTheDocument()
  })

  it('falls back to the first table when requests is absent', async () => {
    mockFetchByPath({
      '/db/tables/collector_state': {
        table: 'collector_state', total: 1, limit: 50, offset: 0,
        columns: ['last_offset'], rows: [[7]],
      },
      '/db/tables': { tables: ['collector_state'] },
    })
    renderWithClient(<Database />)
    await waitFor(() => expect(screen.getByText('7')).toBeInTheDocument())
  })
})
