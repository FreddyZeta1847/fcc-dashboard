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

export type RangeName = 'today' | 'last_7_days' | 'last_30_days' | 'all_time'

export interface ByProviderVolume {
  provider: string
  request_count: number
  input_tokens: number
  output_tokens: number
  estimated_count: number
}

export interface ByModelVolume {
  provider: string
  model: string
  request_count: number
  input_tokens: number
  output_tokens: number
  estimated_count: number
}

export interface DailySavingsEntry {
  date: string
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
  volume_by_provider: ByProviderVolume[]
  volume_by_model: ByModelVolume[]
  daily_savings: DailySavingsEntry[]
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

export interface PriceEntry {
  input_per_million: number
  output_per_million: number
  [key: string]: unknown // currency/last_updated/source may be present
}

export interface PricingConfig {
  anthropic: Record<string, PriceEntry>
  providers: Record<string, Record<string, PriceEntry>>
}

export interface PricingChange {
  provider: string
  model: string
  current: { input_per_million: number; output_per_million: number } | null
  proposed: { input_per_million: number; output_per_million: number } | null
  source: string
  changed: boolean
}

export interface PricingPairNotFound {
  provider: string
  model: string
}

export interface PricingRefreshResponse {
  changes: PricingChange[]
  not_found: PricingPairNotFound[]
}

export interface TablesListResponse {
  tables: string[]
}

export interface TableRowsResponse {
  table: string
  total: number
  limit: number
  offset: number
  columns: string[]
  rows: unknown[][]
}

export type ControlStartAction = 'started' | 'already_running' | 'executable_not_found' | 'launch_failed'
export type ControlStopAction = 'stopped' | 'not_running' | 'stop_failed'

export interface ControlStartResponse {
  action: ControlStartAction
  pid: number | null
}

export interface ControlStopResponse {
  action: ControlStopAction
  pid: number | null
}
