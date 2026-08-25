/*
 * CumulativeSavingsChart.tsx
 * Usage page's day-by-day running total of savings, built from
 * `daily_savings` (backend/src/fcc_dashboard/routes_stats.py's
 * `_aggregate_daily_savings` — added specifically for this chart). The
 * backend returns each day's OWN savings only; the RUNNING cumulative
 * total (bar height = total-through-that-day, not that day's own amount)
 * is a plain presentational `reduce` computed here, not a pricing
 * calculation — the actual $ formula stays entirely backend-side in
 * pricing.py, so doing this one running-sum transform client-side
 * doesn't violate this project's "never duplicate business logic
 * client-side" rule.
 *
 * `daily_savings` is always gap-filled by the backend (every calendar day
 * in range appears, even at $0.0 — see routes_stats.py's docstring), so
 * this component never needs to fill missing days itself; an empty array
 * only happens if the range genuinely has zero days (never in practice,
 * but handled defensively).
 */
import type { DailySavingsEntry } from '../api/types'

interface CumulativeSavingsChartProps {
  data: DailySavingsEntry[]
}

const currencyFormatter = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

function formatShortDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function CumulativeSavingsChart({ data }: CumulativeSavingsChartProps) {
  if (data.length === 0) {
    return (
      <section>
        <h2 style={{ fontSize: 16, fontWeight: 800, marginBottom: 6 }}>Cumulative savings</h2>
        <p style={{ color: 'var(--faint)' }}>No usage data for this range</p>
      </section>
    )
  }

  const cumulative = data.reduce<number[]>((acc, entry) => {
    const previousTotal = acc.length > 0 ? acc[acc.length - 1] : 0
    acc.push(previousTotal + entry.savings)
    return acc
  }, [])
  const total = cumulative[cumulative.length - 1] ?? 0
  const maxCumulative = Math.max(...cumulative, 0.0001)

  return (
    <section>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, marginBottom: 6, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800 }}>Cumulative savings</h2>
          <span style={{ fontSize: 12.5, color: 'var(--faint)' }}>each bar adds that day's savings to the running total</span>
        </div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 600, color: 'var(--green)' }}>
          {currencyFormatter.format(total)}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 170, marginTop: 14 }}>
        {data.map((entry, index) => {
          const heightPct = Math.max(3, (cumulative[index] / maxCumulative) * 100)
          return (
            <div
              key={entry.date}
              title={`${formatShortDate(entry.date)} — ${currencyFormatter.format(cumulative[index])} total (+${currencyFormatter.format(entry.savings)} that day)`}
              style={{
                flex: 1,
                minWidth: 3,
                height: `${heightPct}%`,
                background: 'linear-gradient(180deg, var(--green), oklch(0.5 0.09 160))',
                borderRadius: '4px 4px 2px 2px',
                opacity: 0.85,
              }}
            />
          )
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 11.5, color: 'var(--faint)' }}>
        <span>{formatShortDate(data[0].date)}</span>
        <span>{formatShortDate(data[data.length - 1].date)}</span>
      </div>
    </section>
  )
}
