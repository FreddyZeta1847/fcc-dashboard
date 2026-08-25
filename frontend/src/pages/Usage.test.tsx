/*
 * Usage.test.tsx
 * Confirms Usage owns range state and the useStats(range) query: clicking
 * a RangeSelector option re-fetches /stats with the newly selected range
 * baked into the URL, proving the page (not a child) drives the query.
 * Also confirms (Task 3) that once that same query resolves, both volume
 * charts are mounted from it — no separate fetch per chart.
 */
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
  daily_savings: [],
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

  it('renders both volume charts, fed from the one useStats(range) result, once stats load', async () => {
    const statsWithVolume = {
      ...emptyStats,
      volume_by_provider: [
        { provider: 'deepseek', request_count: 10, input_tokens: 1000, output_tokens: 2000, estimated_count: 0 },
      ],
      volume_by_model: [
        { provider: 'deepseek', model: 'deepseek-chat', request_count: 10, input_tokens: 1000, output_tokens: 2000, estimated_count: 0 },
      ],
    }
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(statsWithVolume), { status: 200 }),
    )
    renderWithClient(<Usage />)

    await waitFor(() => expect(screen.getByText('By Provider')).toBeInTheDocument())
    expect(screen.getByText('By Model')).toBeInTheDocument()
    expect(screen.getByText('deepseek')).toBeInTheDocument()
    expect(screen.getByText('deepseek / deepseek-chat')).toBeInTheDocument()
  })
})
