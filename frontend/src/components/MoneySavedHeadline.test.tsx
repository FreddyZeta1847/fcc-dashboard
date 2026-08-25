/*
 * MoneySavedHeadline.test.tsx
 * Guards the "never conflate null savings with zero" invariant: a genuine
 * $0 total and an unpriced ("never configured") total must render as
 * visibly distinct states, and the null case must never produce a
 * $0/0.00-shaped string. See MoneySavedHeadline.tsx for the full rationale.
 */
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

  it('renders an error message, not a stuck loading state, when the /stats fetch fails', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response('boom', { status: 500 }))
    renderWithClient(<MoneySavedHeadline />)
    await waitFor(() => expect(screen.getByText(/couldn't load savings/i)).toBeInTheDocument())
    expect(screen.queryByText(/loading savings/i)).not.toBeInTheDocument()
  })
})
