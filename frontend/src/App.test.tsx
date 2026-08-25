/*
 * App.test.tsx
 * Behavioral spec for the app-level "backend unreachable" resilience gate,
 * plus (Task 1) the tab navigation shell built on top of it. The
 * resilience gate assertion is the original Phase 5 spec and must keep
 * passing unmodified: it proves the gate still short-circuits the whole
 * app before any tab content renders. Written before App.tsx is updated
 * (TDD).
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

  it('switches to the Settings tab on click, keeping the backend-reachable content mounted', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ fcc_status: 'up', providers: [] }), { status: 200 }),
    )
    const user = userEvent.setup()
    renderApp()
    await waitFor(() => expect(screen.getByRole('button', { name: /settings/i })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /settings/i }))
    expect(screen.queryByText(/fcc status/i)).not.toBeInTheDocument()
  })
})
