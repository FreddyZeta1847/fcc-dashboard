/*
 * PriceRefreshFlow.test.tsx
 * Tests for the price-refresh preview-then-approve flow: (1) clicking
 * "Refresh" only calls POST /pricing/refresh (a preview) and must never
 * trigger a PUT /pricing write on its own, and (2) a write only happens
 * after the user reviews the diff and explicitly clicks "Apply".
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PriceRefreshFlow } from './PriceRefreshFlow'

afterEach(() => { vi.restoreAllMocks() })

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const diff = {
  changes: [
    { provider: 'openrouter', model: 'kimi-k2', current: { input_per_million: 0.6, output_per_million: 2.5 }, proposed: { input_per_million: 0.55, output_per_million: 2.2 }, source: 'openrouter', changed: true },
  ],
  not_found: [{ provider: 'deepseek', model: 'v3' }],
}

describe('PriceRefreshFlow', () => {
  it('does not write anything just from clicking refresh', async () => {
    const putCalls: unknown[] = []
    vi.spyOn(global, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url === '/pricing/refresh') return Promise.resolve(new Response(JSON.stringify(diff), { status: 200 }))
      if (url === '/pricing' && init?.method === 'PUT') { putCalls.push(init); return Promise.resolve(new Response('{}', { status: 200 })) }
      if (url === '/pricing') return Promise.resolve(new Response(JSON.stringify({ anthropic: {}, providers: {} }), { status: 200 }))
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })
    const user = userEvent.setup()
    renderWithClient(<PriceRefreshFlow />)
    await user.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(screen.getByText('kimi-k2')).toBeInTheDocument())
    expect(screen.getByText(/not found|deepseek/i)).toBeInTheDocument()
    expect(putCalls).toHaveLength(0)
  })

  it('writes the approved diff only after explicit approval', async () => {
    const putCalls: unknown[] = []
    vi.spyOn(global, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url === '/pricing/refresh') return Promise.resolve(new Response(JSON.stringify(diff), { status: 200 }))
      if (url === '/pricing' && init?.method === 'PUT') { putCalls.push(init); return Promise.resolve(new Response('{}', { status: 200 })) }
      if (url === '/pricing') return Promise.resolve(new Response(JSON.stringify({ anthropic: {}, providers: {} }), { status: 200 }))
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })
    const user = userEvent.setup()
    renderWithClient(<PriceRefreshFlow />)
    await user.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(screen.getByText('kimi-k2')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /apply/i }))
    await waitFor(() => expect(putCalls).toHaveLength(1))
  })
})
