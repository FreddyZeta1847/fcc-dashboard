/*
 * RecentRequestsFeed.test.tsx
 * Verifies the recent-requests table renders one row per result and,
 * critically, that the estimated-timestamp marker keys off truthiness of
 * `occurred_at_is_estimated` (a raw 0/1 integer from SQLite, not a JSON
 * boolean) rather than a strict `=== true` check that would never match.
 */
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

  it('renders an error message, not a stuck loading state, when the fetch fails', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response('boom', { status: 500 }))
    renderWithClient(<RecentRequestsFeed />)
    await waitFor(() => expect(screen.getByText(/couldn't load recent requests/i)).toBeInTheDocument())
    expect(screen.queryByText(/loading recent requests/i)).not.toBeInTheDocument()
  })
})
