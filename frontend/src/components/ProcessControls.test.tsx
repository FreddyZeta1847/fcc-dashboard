/*
 * ProcessControls.test.tsx
 * Tests for the Settings page's FCC start/stop controls. Confirms both
 * Start and Stop go through a confirm-before-action step (not just Stop —
 * see ProcessControls.tsx header) and that a normal, expected 200 outcome
 * like `executable_not_found` reads as a plain status message, not an
 * error.
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProcessControls } from './ProcessControls'

afterEach(() => { vi.restoreAllMocks() })

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('ProcessControls', () => {
  it('requires confirmation before starting FCC', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ action: 'started', pid: 4242 }), { status: 200 }),
    )
    const user = userEvent.setup()
    renderWithClient(<ProcessControls />)
    await user.click(screen.getByRole('button', { name: /^start/i }))
    expect(global.fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/control/start', { method: 'POST' }))
    await waitFor(() => expect(screen.getByText(/started/i)).toBeInTheDocument())
  })

  it('requires confirmation before stopping FCC', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ action: 'stopped', pid: 4242 }), { status: 200 }),
    )
    const user = userEvent.setup()
    renderWithClient(<ProcessControls />)
    await user.click(screen.getByRole('button', { name: /^stop/i }))
    expect(global.fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/control/stop', { method: 'POST' }))
  })

  it('shows a clear message for executable_not_found without treating it as an error', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ action: 'executable_not_found', pid: null }), { status: 200 }),
    )
    const user = userEvent.setup()
    renderWithClient(<ProcessControls />)
    await user.click(screen.getByRole('button', { name: /^start/i }))
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() => expect(screen.getByText(/not found|not installed/i)).toBeInTheDocument())
  })
})
