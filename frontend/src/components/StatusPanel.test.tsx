/*
 * StatusPanel.test.tsx
 * Behavioral spec for <StatusPanel /> — asserts FCC reachability and
 * per-provider health render distinctly (a stale API key must read
 * differently from a fully down provider, since they need different
 * operator responses). Written before StatusPanel.tsx exists (TDD).
 * Each test wraps the panel in its own QueryClientProvider since
 * useStatus() requires one in its ancestry.
 */
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
