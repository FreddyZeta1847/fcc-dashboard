/*
 * client.ts
 * Thin fetch wrappers over the dashboard backend's three read endpoints
 * (/status, /stats, /requests). Relative URLs only — the Vite dev proxy
 * (Task 1) and the production build's same-origin serving both resolve
 * these without a base URL. Each function throws on a non-ok response so
 * TanStack Query's own error state (Step 4's hooks) picks it up; no
 * retry/timeout logic here — that's owned by the query hooks, not this
 * layer.
 */
import type { RequestsListResponse, StatsResponse, StatusResponse } from './types'

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
