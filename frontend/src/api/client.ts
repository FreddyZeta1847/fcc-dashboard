/*
 * client.ts
 * Thin fetch wrappers over the dashboard backend's endpoints: the original
 * three read endpoints (/status, /stats, /requests) from Phase 5, plus
 * pricing (/pricing, /pricing/refresh), the raw db browser (/db/tables,
 * /db/tables/{name}), and FCC process control (/control/start,
 * /control/stop). Relative URLs only — the Vite dev proxy (Task 1) and the
 * production build's same-origin serving both resolve these without a base
 * URL. Each function throws on a non-ok response so TanStack Query's own
 * error state (the hooks in ../hooks/) picks it up; no retry/timeout logic
 * here — that's owned by the query hooks, not this layer.
 */
import type {
  ControlStartResponse,
  ControlStopResponse,
  PricingConfig,
  PricingRefreshResponse,
  RequestsListResponse,
  StatsResponse,
  StatusResponse,
  TableRowsResponse,
  TablesListResponse,
} from './types'

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`)
  }
  return response.json() as Promise<T>
}

export async function getStatus(): Promise<StatusResponse> {
  const response = await fetch('/status')
  return parseJsonOrThrow<StatusResponse>(response)
}

export async function getStats(range: string): Promise<StatsResponse> {
  const response = await fetch(`/stats?range=${range}`)
  return parseJsonOrThrow<StatsResponse>(response)
}

export async function getRecentRequests(limit: number): Promise<RequestsListResponse> {
  const response = await fetch(`/requests?limit=${limit}`)
  return parseJsonOrThrow<RequestsListResponse>(response)
}

export async function getPricing(): Promise<PricingConfig> {
  const response = await fetch('/pricing')
  return parseJsonOrThrow<PricingConfig>(response)
}

export async function putPricing(config: PricingConfig): Promise<PricingConfig> {
  const response = await fetch('/pricing', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  return parseJsonOrThrow<PricingConfig>(response)
}

export async function postPricingRefresh(): Promise<PricingRefreshResponse> {
  const response = await fetch('/pricing/refresh', { method: 'POST' })
  return parseJsonOrThrow<PricingRefreshResponse>(response)
}

export async function getDbTables(): Promise<TablesListResponse> {
  const response = await fetch('/db/tables')
  return parseJsonOrThrow<TablesListResponse>(response)
}

export async function getDbTableRows(
  name: string,
  limit: number,
  offset: number,
): Promise<TableRowsResponse> {
  // `name` is user/schema-derived (a raw table name), not an enum-constrained
  // value like this file's other path segments — encode it rather than
  // interpolating it raw into the URL.
  const response = await fetch(
    `/db/tables/${encodeURIComponent(name)}?limit=${limit}&offset=${offset}`,
  )
  return parseJsonOrThrow<TableRowsResponse>(response)
}

export async function postControlStart(): Promise<ControlStartResponse> {
  const response = await fetch('/control/start', { method: 'POST' })
  return parseJsonOrThrow<ControlStartResponse>(response)
}

export async function postControlStop(): Promise<ControlStopResponse> {
  const response = await fetch('/control/stop', { method: 'POST' })
  return parseJsonOrThrow<ControlStopResponse>(response)
}
