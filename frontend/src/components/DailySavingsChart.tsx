/*
 * DailySavingsChart.tsx
 * Usage page's per-day savings chart, built from `daily_savings`
 * (backend/src/fcc_dashboard/routes_stats.py's `_aggregate_daily_savings`).
 * Each bar is that day's OWN savings.
 *
 * This was previously a running cumulative total. Day-by-day answers a
 * different and more useful question: a cumulative chart only ever slopes up,
 * so a day that saved nothing looks identical to a good day (the line just
 * flattens slightly), and comparing two days means eyeballing the difference
 * between two heights. Per-day bars make an idle day visibly zero and make
 * heavy days stand out directly.
 *
 * The tradeoff, worth knowing: the running total is no longer readable off the
 * bars. The range total is kept in the header so that figure is not lost.
 *
 * No pricing math happens here — the $ formula stays entirely backend-side in
 * pricing.py. This component only sums for the header and scales bar heights,
 * which keeps this project's "never duplicate business logic client-side" rule
 * intact.
 *
 * `daily_savings` is always gap-filled by the backend (every calendar day in
 * range appears, even at $0.0 — see routes_stats.py's docstring), so this
 * component never needs to fill missing days itself; an empty array only
 * happens if the range genuinely has zero days (never in practice, but handled
 * defensively).
 */
import type { DailySavingsEntry } from '../api/types'

interface DailySavingsChartProps {
  data: DailySavingsEntry[]
}

const currencyFormatter = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

function formatShortDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function DailySavingsChart({ data }: DailySavingsChartProps) {
  if (data.length === 0) {
    return (
      <section>
        <h2 style={{ fontSize: 16, fontWeight: 800, marginBottom: 6 }}>Daily savings</h2>
        <p style={{ color: 'var(--faint)' }}>No usage data for this range</p>
      </section>
    )
  }

  const total = data.reduce((sum, entry) => sum + entry.savings, 0)
  // Scale to the busiest single day, not the range total, so bars use the full
  // height. The floor keeps an all-zero range from dividing by zero.
  const maxDaily = Math.max(...data.map((entry) => entry.savings), 0.0001)

  return (
    <section>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, marginBottom: 6, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800 }}>Daily savings</h2>
          <span style={{ fontSize: 12.5, color: 'var(--faint)' }}>each bar is that day's own savings</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
          <span style={{ fontSize: 11.5, color: 'var(--faint)' }}>range total</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 600, color: 'var(--green)' }}>
            {currencyFormatter.format(total)}
          </span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 170, marginTop: 14 }}>
        {data.map((entry) => {
          // A day with genuinely zero savings gets a flat sliver rather than
          // the 3% stub a nonzero-but-tiny day gets, so "nothing happened" and
          // "a little happened" stay visually distinct.
          const heightPct = entry.savings <= 0 ? 1 : Math.max(3, (entry.savings / maxDaily) * 100)
          return (
            <div
              key={entry.date}
              title={`${formatShortDate(entry.date)} — ${currencyFormatter.format(entry.savings)} saved`}
              style={{
                flex: 1,
                minWidth: 3,
                height: `${heightPct}%`,
                background:
                  entry.savings <= 0
                    ? 'var(--border2)'
                    : 'linear-gradient(180deg, var(--green), oklch(0.5 0.09 160))',
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
