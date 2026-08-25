/*
 * client.test.ts
 * Behavioral spec for the API client functions in ./client — mocks
 * global.fetch and asserts on the exact URL called, the parsed JSON
 * returned, and error propagation for both HTTP-error and network-error
 * cases. Written before client.ts exists (TDD): this file is the contract.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getStatus, getStats, getRecentRequests } from './client'

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
