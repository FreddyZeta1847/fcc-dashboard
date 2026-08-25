/*
 * types.ts
 * TypeScript mirrors of BACKEND's Pydantic response models. Field names
 * and nullability must match backend/src/fcc_dashboard/routes_*.py
 * exactly — these are not independently designed, they are a transcription
 * of an existing contract.
 */

export type ProviderHealthStatus = 'ok' | 'stale_key' | 'rate_limited' | 'down'

export interface ProviderStatus {
  provider: string
  status: ProviderHealthStatus
  last_error_at: string | null
  http_status: number | null
}

export interface StatusResponse {
  fcc_status: 'up' | 'down'
  providers: ProviderStatus[]
}

export interface ByProviderStats {
  provider: string
  request_count: number
  savings: number
}

export interface StatsResponse {
  range: string
  range_start: string
  range_end: string
  total_requests: number
  completed_requests: number
  error_requests: number
  pending_requests: number
  total_input_tokens: number
  total_output_tokens: number
  total_savings: number | null
  unpriced_request_count: number
  by_provider: ByProviderStats[]
}

export type RequestStatus = 'pending' | 'completed' | 'error'

export interface RequestRow {
  request_id: string
  provider: string | null
  gateway_model: string | null
  downstream_model: string | null
  input_tokens: number | null
  output_tokens: number | null
  input_tokens_estimate: number | null
  finish_reason: string | null
  http_status: number | null
  exc_type: string | null
  occurred_at: string
  occurred_at_is_estimated: 0 | 1
  ingested_at: string
  actual_cost: number | null
  equivalent_cost: number | null
  savings: number | null
  status: RequestStatus
}

export interface RequestsListResponse {
  total: number
  limit: number
  offset: number
  results: RequestRow[]
}
