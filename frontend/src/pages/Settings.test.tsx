/*
 * Settings.test.tsx
 * Behavioral spec for the Settings page: proves PricingEditor,
 * PriceRefreshFlow, and ProcessControls all mount together and each
 * render their own key content, routed by URL through a single mocked
 * `fetch` (same pattern as Overview.test.tsx). Written before Settings.tsx
 * (TDD).
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Settings } from './Settings'

afterEach(() => {
  vi.restoreAllMocks()
})

const pricingConfig = {
  anthropic: {
    opus: { input_per_million: 15, output_per_million: 75 },
    sonnet: { input_per_million: 3, output_per_million: 15 },
    haiku: { input_per_million: 0.25, output_per_million: 1.25 },
  },
  providers: {
    deepseek: { 'deepseek-chat': { input_per_million: 0.27, output_per_million: 1.1 } },
  },
}

describe('Settings', () => {
  it('renders the pricing editor, the refresh flow, and the process controls together', async () => {
    vi.spyOn(global, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.startsWith('/pricing/refresh')) {
        return Promise.resolve(
          new Response(JSON.stringify({ changes: [], not_found: [] }), { status: 200 }),
        )
      }
      if (url.startsWith('/pricing')) {
        if (init?.method === 'PUT') {
          return Promise.resolve(new Response(init.body as string, { status: 200 }))
        }
        return Promise.resolve(new Response(JSON.stringify(pricingConfig), { status: 200 }))
      }
      if (url.startsWith('/control/')) {
        return Promise.resolve(new Response(JSON.stringify({ action: 'started', pid: 1 }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Settings />
      </QueryClientProvider>,
    )

    await waitFor(() => expect(screen.getByText('deepseek-chat')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /refresh prices/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^start/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^stop/i })).toBeInTheDocument()
  })
})
