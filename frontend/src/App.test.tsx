/*
 * App.test.tsx
 * Behavioral spec for the app-level "backend unreachable" resilience gate.
 * A network-level fetch rejection (backend process not running) must
 * produce a distinct, full-page "backend not running" message — never a
 * status panel silently rendering empty/error data — per
 * FRONTEND--resilience. Written before App.tsx is updated (TDD).
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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
})
