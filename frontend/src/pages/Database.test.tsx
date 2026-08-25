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
