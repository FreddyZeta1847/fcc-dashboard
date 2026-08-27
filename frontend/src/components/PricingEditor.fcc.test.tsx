/*
 * PricingEditor.fcc.test.tsx
 * Tests for the FCC-driven provider/model pickers, kept separate from
 * PricingEditor.test.tsx so that file stays focused on the confirm-before-write
 * rule it was written for.
 *
 * The behaviour that matters here is not "a dropdown renders" but that the
 * value it submits is the provider's `log_tag` — the exact string FCC writes
 * into its logs and the collector stores in `requests.provider`. Submitting
 * `provider_id` ('nvidia_nim') or `display_name` ('NVIDIA NIM') instead would
 * look correct on screen while producing a price that silently never matches a
 * request, which is the whole failure this feature exists to prevent. So the
 * PUT body is asserted, not just the UI.
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query'
import { PricingEditor } from './PricingEditor'

/*
 * Drive React Query's own focus manager rather than dispatching a synthetic
 * window 'focus' event. jsdom's event never reaches the manager, so a test
 * built on it cannot fail — verified by removing `staleTime: Infinity` and
 * watching the suite still pass. This actually toggles the refetch trigger.
 */
async function simulateWindowRefocus() {
  focusManager.setFocused(false)
  focusManager.setFocused(true)
  await new Promise((r) => setTimeout(r, 150))
}

afterEach(() => {
  vi.restoreAllMocks()
})

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const config = {
  anthropic: {
    'claude-opus-5': { input_per_million: 5, output_per_million: 25 },
  },
  providers: {
    NIM: {
      'deepseek-ai/deepseek-v4-flash-0731': {
        input_per_million: 0,
        output_per_million: 0,
      },
    },
  },
}

const catalog = {
  available: true,
  providers: [
    {
      provider_id: 'nvidia_nim',
      display_name: 'NVIDIA NIM',
      log_tag: 'NIM',
      kind: 'remote',
      models: ['deepseek-ai/deepseek-v4-flash-0731'],
    },
    {
      provider_id: 'ollama',
      display_name: 'Ollama',
      log_tag: 'OLLAMA',
      kind: 'local',
      models: ['gemma3:4b', 'qwen2:7b'],
    },
  ],
  observed_providers: ['NIM'],
  error: null,
}

const unavailableCatalog = {
  available: false,
  providers: [],
  observed_providers: ['NIM'],
  error: 'Could not reach FCC at http://127.0.0.1:8082 (ConnectError).',
}

/** Mock both endpoints; capture PUT bodies for assertion. */
function mockApi(catalogPayload: unknown) {
  const putBodies: string[] = []
  vi.spyOn(global, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (url === '/fcc/catalog') {
      return Promise.resolve(new Response(JSON.stringify(catalogPayload), { status: 200 }))
    }
    if (url === '/pricing' && init?.method === 'PUT') {
      putBodies.push(init.body as string)
      return Promise.resolve(new Response(init.body as string, { status: 200 }))
    }
    if (url === '/pricing') {
      return Promise.resolve(new Response(JSON.stringify(config), { status: 200 }))
    }
    return Promise.reject(new Error(`unexpected fetch: ${url}`))
  })
  return putBodies
}

async function confirmSave(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /save price/i }))
  const dialog = await screen.findByRole('dialog')
  await user.click(within(dialog).getByRole('button', { name: /save price/i }))
}

describe('PricingEditor + FCC catalog', () => {
  it('offers the providers FCC reports as configured', async () => {
    mockApi(catalog)
    renderWithClient(<PricingEditor />)

    const select = await screen.findByLabelText(/provider/i)
    await waitFor(() => expect(within(select).getAllByRole('option').length).toBeGreaterThan(1))

    expect(within(select).getByRole('option', { name: /NVIDIA NIM/ })).toBeInTheDocument()
    expect(within(select).getByRole('option', { name: /Ollama/ })).toBeInTheDocument()
  })

  it('filters the model list to the selected provider', async () => {
    mockApi(catalog)
    const user = userEvent.setup()
    renderWithClient(<PricingEditor />)

    const providerSelect = await screen.findByLabelText(/provider/i)
    await waitFor(() =>
      expect(within(providerSelect).getAllByRole('option').length).toBeGreaterThan(1),
    )
    await user.selectOptions(providerSelect, 'OLLAMA')

    const modelSelect = screen.getByLabelText(/model/i)
    expect(within(modelSelect).getByRole('option', { name: 'gemma3:4b' })).toBeInTheDocument()
    expect(
      within(modelSelect).queryByRole('option', {
        name: 'deepseek-ai/deepseek-v4-flash-0731',
      }),
    ).not.toBeInTheDocument()
  })

  it('writes the provider log_tag, not the provider_id or display name', async () => {
    const putBodies = mockApi(catalog)
    const user = userEvent.setup()
    renderWithClient(<PricingEditor />)

    const providerSelect = await screen.findByLabelText(/provider/i)
    await waitFor(() =>
      expect(within(providerSelect).getAllByRole('option').length).toBeGreaterThan(1),
    )
    await user.selectOptions(providerSelect, 'OLLAMA')
    await user.selectOptions(screen.getByLabelText(/model/i), 'gemma3:4b')
    await user.type(screen.getByLabelText(/input.*mtok/i), '0')
    await user.type(screen.getByLabelText(/output.*mtok/i), '0')
    await confirmSave(user)

    await waitFor(() => expect(putBodies.length).toBe(1))
    const written = JSON.parse(putBodies[0])
    expect(written.providers.OLLAMA['gemma3:4b']).toEqual({
      input_per_million: 0,
      output_per_million: 0,
    })
    expect(written.providers.ollama).toBeUndefined()
    expect(written.providers['NVIDIA NIM']).toBeUndefined()
    // The pre-existing NIM entry must survive the whole-document PUT.
    expect(written.providers.NIM).toBeDefined()
  })

  it('resets the model when the provider changes', async () => {
    mockApi(catalog)
    const user = userEvent.setup()
    renderWithClient(<PricingEditor />)

    const providerSelect = await screen.findByLabelText(/provider/i)
    await waitFor(() =>
      expect(within(providerSelect).getAllByRole('option').length).toBeGreaterThan(1),
    )
    await user.selectOptions(providerSelect, 'OLLAMA')
    await user.selectOptions(screen.getByLabelText(/model/i), 'gemma3:4b')
    await user.selectOptions(providerSelect, 'NIM')

    expect((screen.getByLabelText(/model/i) as HTMLSelectElement).value).toBe('')
  })

  it('falls back to manual text entry when FCC is unreachable', async () => {
    mockApi(unavailableCatalog)
    renderWithClient(<PricingEditor />)

    await waitFor(() => expect(screen.getByText(/falling back to manual entry/i)).toBeInTheDocument())

    const providerField = screen.getByLabelText(/provider/i)
    expect(providerField.tagName).toBe('INPUT')
    expect(screen.getByLabelText(/model/i).tagName).toBe('INPUT')
  })

  it('lets the user switch back to manual entry while FCC is reachable', async () => {
    mockApi(catalog)
    const user = userEvent.setup()
    renderWithClient(<PricingEditor />)

    await waitFor(() => expect((screen.getByLabelText(/provider/i)).tagName).toBe('SELECT'))
    await user.click(screen.getByRole('button', { name: /enter manually/i }))

    expect(screen.getByLabelText(/provider/i).tagName).toBe('INPUT')
  })

  it('flags a configured pair FCC does not report', async () => {
    const staleConfig = {
      anthropic: config.anthropic,
      providers: {
        ...config.providers,
        GONE: { 'some-model': { input_per_million: 1, output_per_million: 2 } },
      },
    }
    vi.spyOn(global, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url === '/fcc/catalog') {
        return Promise.resolve(new Response(JSON.stringify(catalog), { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify(staleConfig), { status: 200 }))
    })
    renderWithClient(<PricingEditor />)

    const warnings = await screen.findAllByLabelText(/not reported by fcc/i)
    expect(warnings.length).toBe(1)
  })

  it('does not flag anything when FCC is unreachable', async () => {
    mockApi(unavailableCatalog)
    renderWithClient(<PricingEditor />)

    await waitFor(() => expect(screen.getByText(/falling back to manual entry/i)).toBeInTheDocument())

    // Absence of FCC is not evidence that a configured row is wrong.
    expect(screen.queryByLabelText(/not reported by fcc/i)).not.toBeInTheDocument()
  })

  it('does not flag Anthropic tiers, which FCC never reports', async () => {
    mockApi(catalog)
    renderWithClient(<PricingEditor />)

    await waitFor(() => expect(screen.getByText('claude-opus-5')).toBeInTheDocument())

    expect(screen.queryByLabelText(/not reported by fcc/i)).not.toBeInTheDocument()
  })
  it('stops fetching the catalog once it has a usable one', async () => {
    /*
     * The core of the fetch-until-we-have-it-then-stop rule. The catalog is
     * FCC's configuration, not its running state, so re-fetching it would only
     * re-learn something already known. `staleTime: Infinity` is what has to
     * hold here: without it React Query's refetch-on-mount/focus defaults would
     * fire and this count would climb.
     */
    let catalogFetches = 0
    vi.spyOn(global, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url === '/fcc/catalog') {
        catalogFetches += 1
        return Promise.resolve(new Response(JSON.stringify(catalog), { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify(config), { status: 200 }))
    })

    renderWithClient(<PricingEditor />)
    await waitFor(() => expect(screen.getByLabelText(/provider/i).tagName).toBe('SELECT'))
    expect(catalogFetches).toBe(1)

    // Refocus is the trigger most likely to sneak a refetch past the rule,
    // since React Query listens for it by default.
    await simulateWindowRefocus()

    expect(catalogFetches).toBe(1)
  })

  it('keeps the pickers working after FCC goes down, once the catalog is held', async () => {
    /*
     * The practical payoff of holding the catalog: prices live in OUR config
     * file, not FCC's, so adding a pair must not require FCC to be running.
     * Once the list has loaded, stopping FCC must not drop the editor back to
     * manual entry.
     */
    let fccUp = true
    vi.spyOn(global, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url === '/fcc/catalog') {
        return Promise.resolve(
          new Response(JSON.stringify(fccUp ? catalog : unavailableCatalog), { status: 200 }),
        )
      }
      return Promise.resolve(new Response(JSON.stringify(config), { status: 200 }))
    })

    renderWithClient(<PricingEditor />)
    await waitFor(() => expect(screen.getByLabelText(/provider/i).tagName).toBe('SELECT'))

    // FCC stops. Nothing should re-ask, so the held catalog stays in use.
    fccUp = false
    await simulateWindowRefocus()

    expect(screen.getByLabelText(/provider/i).tagName).toBe('SELECT')
    expect(screen.queryByText(/falling back to manual entry/i)).not.toBeInTheDocument()
  })

  it('keeps manual entry when the user chose it, even after FCC returns', async () => {
    /* An explicit choice must not be overridden by FCC coming back. */
    mockApi(catalog)
    const user = userEvent.setup()
    renderWithClient(<PricingEditor />)

    await waitFor(() => expect(screen.getByLabelText(/provider/i).tagName).toBe('SELECT'))
    await user.click(screen.getByRole('button', { name: /enter manually/i }))

    expect(screen.getByLabelText(/provider/i).tagName).toBe('INPUT')
    // Still manual after re-renders driven by query updates.
    await waitFor(() => expect(screen.getByLabelText(/provider/i).tagName).toBe('INPUT'))
  })
})
