/*
 * MoneySavedHeadline.tsx
 * Dashboard's core "how much did this save me" figure. Calls useStats()
 * itself with a fixed range (no range selector here — that is the Usage
 * page's job), same self-fetching pattern as StatusPanel.
 *
 * `total_savings: null` means the pricing engine has never had a config to
 * price against — a fact distinct from every request summing to a real
 * $0.00. Collapsing the two would silently tell the user "this saved you
 * nothing" when the true state is "we can't tell you yet". This mirrors a
 * project-wide invariant that also runs through the backend's pricing
 * engine: never assume free. So the null branch renders a distinct
 * "no pricing configured" message and deliberately avoids any
 * $/0.00-shaped text.
 *
 * `isError` is checked before the `isLoading || !data` guard: GET /stats has
 * a documented, reachable 500 (routes_stats.py deliberately lets
 * compute_savings raise ValueError for an unconfigured gateway_model rather
 * than swallowing it), and once loading finishes `data` stays undefined on
 * failure too — so without a separate error branch this panel would look
 * stuck on "Loading…" forever instead of surfacing the failure.
 */
import { useStats } from '../hooks/useStats'
import { Card } from './Card'
import { Skeleton } from './Skeleton'

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

export function MoneySavedHeadline() {
  const { data, isLoading, isError } = useStats('last_7_days')

  if (isError) {
    return (
      <Card accent="red" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <p style={{ color: 'var(--red)' }}>Couldn't load savings.</p>
      </Card>
    )
  }

  if (isLoading || !data) {
    return (
      <Card style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Skeleton width="40%" height={14} />
        <Skeleton width="65%" height={52} delay={0.15} />
        <Skeleton width="55%" height={12} delay={0.3} />
      </Card>
    )
  }

  const { total_savings, unpriced_request_count } = data

  if (total_savings === null) {
    return (
      <Card
        accent="none"
        dashed
        style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6 }}
      >
        <div
          style={{
            fontSize: 12,
            fontWeight: 800,
            letterSpacing: '.09em',
            textTransform: 'uppercase',
            color: 'var(--faint)',
          }}
        >
          Saved · last 7 days
        </div>
        <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--muted)', letterSpacing: '-.01em' }}>
          No pricing configured yet
        </div>
        <div style={{ color: 'var(--faint)' }}>
          Savings can't be calculated until at least one model has a price.
        </div>
      </Card>
    )
  }

  return (
    <Card accent="green" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6 }}>
      <div
        style={{
          fontSize: 12,
          fontWeight: 800,
          letterSpacing: '.09em',
          textTransform: 'uppercase',
          color: 'var(--green)',
        }}
      >
        Saved · last 7 days
      </div>
      <div
        style={{
          fontSize: 56,
          fontWeight: 800,
          letterSpacing: '-.03em',
          lineHeight: 1.1,
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        {currencyFormatter.format(total_savings)}
      </div>
      <div style={{ color: 'var(--muted)' }}>vs. what these requests would have cost on the paid API</div>
      {unpriced_request_count > 0 && (
        <div style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--faint)', fontSize: 12.5 }}>
          <span aria-hidden="true" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--faint)', flexShrink: 0 }} />
          {unpriced_request_count} requests excluded — their price is unknown
        </div>
      )}
    </Card>
  )
}
