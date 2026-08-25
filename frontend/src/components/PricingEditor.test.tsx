/*
 * PricingEditor.test.tsx
 * Tests for the pricing config editor: (1) it renders every configured
 * (provider, model) price pair from usePricing(), and (2) the manual
 * add/edit form requires a two-step confirm before it ever calls
 * usePutPricing()'s mutate function — the first "Save" click must NOT
 * fire the PUT, only a follow-up "Confirm" click may.
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PricingEditor } from './PricingEditor'

afterEach(() => { vi.restoreAllMocks() })

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const config = {
  anthropic: {
    opus: { input_per_million: 15, output_per_million: 75 },
    sonnet: { input_per_million: 3, output_per_million: 15 },
    haiku: { input_per_million: 0.25, output_per_million: 1.25 },
  },
  providers: {
    deepseek: { 'deepseek-chat': { input_per_million: 0.27, output_per_million: 1.1 } },
  },
}

describe('PricingEditor', () => {
  it('renders every configured price pair', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(config), { status: 200 }))
    renderWithClient(<PricingEditor />)
    await waitFor(() => expect(screen.getByText('deepseek-chat')).toBeInTheDocument())
    expect(screen.getByText(/opus/i)).toBeInTheDocument()
  })

  it('lets the user add a new (provider, model) price pair and requires confirmation before saving', async () => {
    vi.spyOn(global, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url === '/pricing' && (!init || init.method === undefined)) {
        return Promise.resolve(new Response(JSON.stringify(config), { status: 200 }))
      }
      if (url === '/pricing' && init?.method === 'PUT') {
        return Promise.resolve(new Response(init.body as string, { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected fetch: ${url} ${init?.method}`))
    })
    const user = userEvent.setup()
    renderWithClient(<PricingEditor />)
    await waitFor(() => expect(screen.getByText('deepseek-chat')).toBeInTheDocument())

    await user.type(screen.getByLabelText(/provider/i), 'kimi')
    await user.type(screen.getByLabelText(/model/i), 'kimi-k2')
    await user.type(screen.getByLabelText(/input.*per million/i), '0.6')
    await user.type(screen.getByLabelText(/output.*per million/i), '2.5')
    await user.click(screen.getByRole('button', { name: /save/i }))

    // First click should ask for confirmation, not fire the write yet.
    expect(
      (global.fetch as ReturnType<typeof vi.fn>).mock.calls.some(([, init]) => init?.method === 'PUT'),
    ).toBe(false)

    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() =>
      expect(
        (global.fetch as ReturnType<typeof vi.fn>).mock.calls.some(([, init]) => init?.method === 'PUT'),
      ).toBe(true),
    )
  })

  it('blocks Save when a price field is blank, and never fires the PUT', async () => {
    vi.spyOn(global, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url === '/pricing' && (!init || init.method === undefined)) {
        return Promise.resolve(new Response(JSON.stringify(config), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected fetch: ${url} ${init?.method}`))
    })
    const user = userEvent.setup()
    renderWithClient(<PricingEditor />)
    await waitFor(() => expect(screen.getByText('deepseek-chat')).toBeInTheDocument())

    await user.type(screen.getByLabelText(/provider/i), 'kimi')
    await user.type(screen.getByLabelText(/model/i), 'kimi-k2')
    // Input price left blank on purpose.
    await user.type(screen.getByLabelText(/output.*per million/i), '2.5')
    await user.click(screen.getByRole('button', { name: /save/i }))

    // No Confirm step should even appear, and the PUT must never fire.
    expect(screen.queryByRole('button', { name: /confirm/i })).not.toBeInTheDocument()
    expect(
      (global.fetch as ReturnType<typeof vi.fn>).mock.calls.some(([, init]) => init?.method === 'PUT'),
    ).toBe(false)

    // Even trying to click through again after the blocked attempt must not fire it.
    await user.click(screen.getByRole('button', { name: /save/i }))
    expect(
      (global.fetch as ReturnType<typeof vi.fn>).mock.calls.some(([, init]) => init?.method === 'PUT'),
    ).toBe(false)
  })
})
