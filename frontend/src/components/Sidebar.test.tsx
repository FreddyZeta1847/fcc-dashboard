/*
 * Sidebar.test.tsx
 * Behavioral spec for the sidebar navigation: renders all four tabs,
 * reports clicks via onTabChange, and visually marks the active tab.
 * Ported from Nav.test.tsx (the horizontal tab bar this component
 * replaces) — active/inactive here is expressed via inline style
 * (background/color from CSS custom properties), not a Tailwind
 * className, so the distinguishing check compares the rendered `style`
 * attribute instead of `className`.
 *
 * Sidebar also owns the stateful Run/Stop fcc-server action (useStatus +
 * useControlStart/useControlStop), so every render needs a
 * QueryClientProvider ancestor, same as any other component using a
 * TanStack Query hook, and `fetch` must be mocked to answer GET /status
 * for the button's up/down state as well as POST /control/*.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from './Sidebar'

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

function mockStatusFetch(fccStatus: 'up' | 'down') {
  vi.spyOn(global, 'fetch').mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.startsWith('/status')) {
      return Promise.resolve(
        new Response(JSON.stringify({ fcc_status: fccStatus, providers: [] }), { status: 200 }),
      )
    }
    return Promise.reject(new Error(`unexpected fetch: ${url}`))
  })
}

describe('Sidebar', () => {
  it('renders all four tabs', () => {
    mockStatusFetch('down')
    renderWithClient(<Sidebar activeTab="overview" onTabChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /overview/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /usage/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /settings/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /database/i })).toBeInTheDocument()
  })

  it('calls onTabChange with the clicked tab', async () => {
    mockStatusFetch('down')
    const onTabChange = vi.fn()
    renderWithClient(<Sidebar activeTab="overview" onTabChange={onTabChange} />)
    await userEvent.click(screen.getByRole('button', { name: /settings/i }))
    expect(onTabChange).toHaveBeenCalledWith('settings')
  })

  it('visually distinguishes the active tab from inactive ones', () => {
    mockStatusFetch('down')
    renderWithClient(<Sidebar activeTab="database" onTabChange={vi.fn()} />)
    const active = screen.getByRole('button', { name: /database/i })
    const inactive = screen.getByRole('button', { name: /overview/i })
    expect(active.getAttribute('style')).not.toBe(inactive.getAttribute('style'))
  })

  it('collapses on toggle, dropping the visible text label from the nav buttons', async () => {
    mockStatusFetch('down')
    renderWithClient(<Sidebar activeTab="overview" onTabChange={vi.fn()} />)
    const overviewButton = screen.getByRole('button', { name: /overview/i })
    expect(overviewButton).toHaveTextContent('Overview')
    await userEvent.click(screen.getByRole('button', { name: /^collapse$/i }))
    // Still findable (falls back to its `title` attribute once the label
    // span is gone), but no longer carries the visible text content.
    expect(screen.getByRole('button', { name: /overview/i })).not.toHaveTextContent('Overview')
  })

  it('shows "Run fcc-server" while FCC is down, and requires confirmation before starting it', async () => {
    vi.spyOn(global, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.startsWith('/status')) {
        return Promise.resolve(new Response(JSON.stringify({ fcc_status: 'down', providers: [] }), { status: 200 }))
      }
      if (url === '/control/start' && init?.method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({ action: 'started', pid: 4242 }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })
    const user = userEvent.setup()
    renderWithClient(<Sidebar activeTab="overview" onTabChange={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('button', { name: /run fcc-server/i })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /run fcc-server/i }))
    expect(global.fetch).not.toHaveBeenCalledWith('/control/start', { method: 'POST' })
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /run fcc-server/i }))
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/control/start', { method: 'POST' }))
    await waitFor(() => expect(screen.getByText(/started/i)).toBeInTheDocument())
  })

  it('shows "Stop fcc-server" while FCC is up, and requires confirmation before stopping it', async () => {
    vi.spyOn(global, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.startsWith('/status')) {
        return Promise.resolve(new Response(JSON.stringify({ fcc_status: 'up', providers: [] }), { status: 200 }))
      }
      if (url === '/control/stop' && init?.method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({ action: 'stopped', pid: null }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })
    const user = userEvent.setup()
    renderWithClient(<Sidebar activeTab="overview" onTabChange={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('button', { name: /stop fcc-server/i })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /stop fcc-server/i }))
    expect(global.fetch).not.toHaveBeenCalledWith('/control/stop', { method: 'POST' })
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /stop fcc-server/i }))
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/control/stop', { method: 'POST' }))
    await waitFor(() => expect(screen.getByText(/stopped/i)).toBeInTheDocument())
  })
})
