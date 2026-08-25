/*
 * RecentRequestsFeed.tsx
 * Table of the most recent gateway requests (fixed limit of 20, no
 * pagination — a "load more" view is a later task). Owns its own
 * useRecentRequests() query, same self-fetching pattern as StatusPanel
 * and MoneySavedHeadline, so Overview can compose panels without
 * prop-drilling query results.
 *
 * `occurred_at_is_estimated` arrives as a raw SQLite integer (0 or 1),
 * not a JSON boolean — checked here via truthiness, never `=== true`,
 * or the estimated-marker badge would silently never render.
 *
 * `provider` and `downstream_model` render in separate grid columns,
 * matching the approved design mockup's own grid — provider "deepseek"
 * being a substring of downstream_model "deepseek-chat" means a `/deepseek/i`
 * regex text query would ambiguously match both cells; tests use an
 * exact-string `getByText('deepseek')` instead where that matters, since
 * an exact match only hits the provider cell.
 *
 * `isError` is checked before the `isLoading || !data` guard: on a fetch
 * failure `data` stays undefined the same way it does while genuinely
 * loading, so without a separate error branch this panel would look stuck
 * on "Loading…" forever (silently re-polling) instead of surfacing the
 * failure.
 */
import { useRecentRequests } from '../hooks/useRecentRequests'
import type { RequestRow } from '../api/types'
import { Card } from './Card'
import { Skeleton } from './Skeleton'

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function formatSavings(savings: number | null) {
  return savings === null ? '—' : currencyFormatter.format(savings)
}

const gridColumns = '130px 100px minmax(0,1fr) 24px 115px 80px'
const monoFont = "'JetBrains Mono', monospace"

const STATUS_DOT_COLOR: Record<RequestRow['status'], string> = {
  completed: 'var(--green)',
  pending: 'var(--amber)',
  error: 'var(--red)',
}

function RequestTableRow({ row }: { row: RequestRow }) {
  const isEstimated = Boolean(row.occurred_at_is_estimated)

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: gridColumns,
        gap: 8,
        alignItems: 'center',
        padding: '9px 10px',
        borderTop: '1px solid var(--border)',
      }}
    >
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontFamily: monoFont, fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
        {new Date(row.occurred_at).toLocaleString()}
        {isEstimated && (
          <span
            title="Timestamp estimated — not reported by the provider"
            style={{
              fontFamily: "'Manrope', sans-serif",
              fontSize: 10,
              fontWeight: 800,
              padding: '1px 6px',
              borderRadius: 999,
              background: 'var(--amberT)',
              color: 'var(--amber)',
              border: '1px solid var(--amberB)',
            }}
          >
            ~ estimated
          </span>
        )}
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700 }}>
        {row.provider ?? '—'}
      </span>
      <span style={{ fontFamily: monoFont, fontSize: 12.5, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {row.downstream_model ?? '—'}
      </span>
      <span
        title={row.status}
        aria-hidden="true"
        style={{ width: 8, height: 8, borderRadius: '50%', background: STATUS_DOT_COLOR[row.status], justifySelf: 'center' }}
      />
      <span style={{ textAlign: 'right', fontFamily: monoFont, fontSize: 12.5, color: 'var(--muted)' }}>
        {row.input_tokens ?? '—'} / {row.output_tokens ?? '—'}
      </span>
      <span style={{ textAlign: 'right', fontFamily: monoFont, fontSize: 12.5, fontWeight: 600, color: row.savings === null ? 'var(--faint)' : 'var(--green)' }}>
        {formatSavings(row.savings)}
      </span>
    </div>
  )
}

export function RecentRequestsFeed() {
  const { data, isLoading, isError } = useRecentRequests(20)

  if (isError) {
    return (
      <Card accent="red">
        <p style={{ color: 'var(--red)' }}>Couldn't load recent requests.</p>
      </Card>
    )
  }

  if (isLoading || !data) {
    return (
      <Card style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Skeleton height={14} />
        <Skeleton height={14} delay={0.15} />
        <Skeleton height={14} delay={0.3} />
        <Skeleton height={14} delay={0.45} />
      </Card>
    )
  }

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 14 }}>
        <h2 style={{ fontSize: 16, fontWeight: 800 }}>Recent requests</h2>
        <span style={{ fontSize: 12.5, color: 'var(--faint)' }}>latest first</span>
      </div>
      {data.results.length === 0 ? (
        <p style={{ color: 'var(--faint)' }}>No requests yet.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: gridColumns,
              gap: 8,
              padding: '6px 10px',
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: '.07em',
              textTransform: 'uppercase',
              color: 'var(--faint)',
            }}
          >
            <span>Time</span>
            <span>Provider</span>
            <span>Model</span>
            <span title="Status">St</span>
            <span style={{ textAlign: 'right' }}>Tokens in / out</span>
            <span style={{ textAlign: 'right' }}>Saved</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {data.results.map((row) => (
              <RequestTableRow key={row.request_id} row={row} />
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}
