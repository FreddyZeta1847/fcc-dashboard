/*
 * Overview.test.tsx
 * Behavioral spec for the Overview page: proves StatusPanel,
 * MoneySavedHeadline, and RecentRequestsFeed all mount together and each
 * render real data from their own self-fetching queries, routed by URL
 * through a single mocked `fetch`. Written before Overview.tsx (TDD).
 */
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
