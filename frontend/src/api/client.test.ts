/*
 * client.test.ts
 * Behavioral spec for the API client functions in ./client — mocks
 * global.fetch and asserts on the exact URL called, the parsed JSON
 * returned, and error propagation for both HTTP-error and network-error
 * cases. Written before client.ts exists (TDD): this file is the contract.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getStatus,
  getStats,
  getRecentRequests,
  getPricing,
  putPricing,
  postPricingRefresh,
  getDbTables,
  getDbTableRows,
  postControlStart,
  postControlStop,
} from './client'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('getStatus', () => {
  it('fetches /status and returns the parsed JSON', async () => {
    const body = { fcc_status: 'up', providers: [] }
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(body), { status: 200 }),
    )
    const result = await getStatus()
    expect(global.fetch).toHaveBeenCalledWith('/status')
    expect(result).toEqual(body)
  })

  it('throws when the response is not ok', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('server error', { status: 500 }),
    )
    await expect(getStatus()).rejects.toThrow()
  })

  it('propagates a network-level fetch rejection', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(getStatus()).rejects.toThrow('Failed to fetch')
  })
})

describe('getStats', () => {
  it('fetches /stats with the range as a query param', async () => {
    const body = {
      range: 'last_7_days', range_start: 'x', range_end: 'y',
      total_requests: 0, completed_requests: 0, error_requests: 0,
      pending_requests: 0, total_input_tokens: 0, total_output_tokens: 0,
      total_savings: null, unpriced_request_count: 0, by_provider: [],
    }
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(body), { status: 200 }),
    )
    const result = await getStats('last_7_days')
    expect(global.fetch).toHaveBeenCalledWith('/stats?range=last_7_days')
    expect(result).toEqual(body)
  })
})

describe('getRecentRequests', () => {
  it('fetches /requests with a limit query param', async () => {
    const body = { total: 0, limit: 20, offset: 0, results: [] }
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(body), { status: 200 }),
    )
    const result = await getRecentRequests(20)
    expect(global.fetch).toHaveBeenCalledWith('/requests?limit=20')
    expect(result).toEqual(body)
  })
})

describe('getPricing', () => {
  it('fetches /pricing', async () => {
    const body = { anthropic: {}, providers: {} }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await getPricing()
    expect(global.fetch).toHaveBeenCalledWith('/pricing')
    expect(result).toEqual(body)
  })
})

describe('putPricing', () => {
  it('PUTs the full config document as JSON', async () => {
    const config = { anthropic: {}, providers: {} }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(config), { status: 200 }))
    await putPricing(config as never)
    expect(global.fetch).toHaveBeenCalledWith('/pricing', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
  })
})

describe('postPricingRefresh', () => {
  it('POSTs to /pricing/refresh with no body', async () => {
    const body = { changes: [], not_found: [] }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await postPricingRefresh()
    expect(global.fetch).toHaveBeenCalledWith('/pricing/refresh', { method: 'POST' })
    expect(result).toEqual(body)
  })
})

describe('getDbTables', () => {
  it('fetches /db/tables', async () => {
    const body = { tables: ['requests'] }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await getDbTables()
    expect(global.fetch).toHaveBeenCalledWith('/db/tables')
    expect(result).toEqual(body)
  })
})

describe('getDbTableRows', () => {
  it('fetches /db/tables/{name} with limit and offset', async () => {
    const body = { table: 'requests', total: 0, limit: 20, offset: 0, columns: [], rows: [] }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await getDbTableRows('requests', 20, 0)
    expect(global.fetch).toHaveBeenCalledWith('/db/tables/requests?limit=20&offset=0')
    expect(result).toEqual(body)
  })
})

describe('postControlStart', () => {
  it('POSTs to /control/start', async () => {
    const body = { action: 'started', pid: 123 }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await postControlStart()
    expect(global.fetch).toHaveBeenCalledWith('/control/start', { method: 'POST' })
    expect(result).toEqual(body)
  })
})

describe('postControlStop', () => {
  it('POSTs to /control/stop', async () => {
    const body = { action: 'stopped', pid: 123 }
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    const result = await postControlStop()
    expect(global.fetch).toHaveBeenCalledWith('/control/stop', { method: 'POST' })
    expect(result).toEqual(body)
  })
})
