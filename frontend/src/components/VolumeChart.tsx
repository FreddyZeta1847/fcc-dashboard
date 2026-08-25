/*
 * VolumeChart.tsx
 * Reusable volume breakdown (by provider or by model — the two shapes
 * share `request_count` / `input_tokens` / `output_tokens` /
 * `estimated_count`, so this component takes a generic `{ label, ... }`
 * entry rather than knowing about `ByProviderVolume` / `ByModelVolume`
 * directly; Usage.tsx maps each backend shape onto `label` at the call
 * site). Renders as horizontal "meter" rows — a thicker bar for
 * `request_count`, a thinner one below it for total tokens — rather than
 * an SVG chart, matching the approved design mockup exactly (which uses
 * plain CSS width percentages throughout, no charting library anywhere).
 * This replaced an earlier Recharts-based version; `recharts` is no
 * longer a runtime dependency of this component.
 *
 * Each entry renders in its own accessible `<li>`, carrying the label as
 * its accessible name (via aria-label, since "listitem" doesn't reliably
 * compute a name from content) and, when `estimated_count > 0`, an
 * "N estimated" marker scoped to that SAME `<li>` — never a page-global
 * note — mirroring the per-row estimated-timestamp badge in
 * RecentRequestsFeed.tsx.
 *
 * Bar widths are percentages of the MAX value across the whole list (per
 * metric), floored at 2% so an entry with a tiny-but-nonzero value still
 * renders a visible sliver instead of disappearing.
 */
import type { CSSProperties } from 'react'

export interface VolumeChartEntry {
  label: string
  request_count: number
  input_tokens: number
  output_tokens: number
  estimated_count: number
}

interface VolumeChartProps {
  data: VolumeChartEntry[]
  groupLabel: string
}

const BAR_COLORS = ['var(--blue)', 'var(--violet)', 'var(--amber)', 'var(--green)', 'var(--red)']

function formatTokens(count: number): string {
  return count >= 1000 ? `${(count / 1000).toFixed(1)}k` : String(count)
}

function widthPercent(value: number, max: number): CSSProperties['width'] {
  if (max <= 0) return '2%'
  return `${Math.max(2, (value / max) * 100)}%`
}

export function VolumeChart({ data, groupLabel }: VolumeChartProps) {
  if (data.length === 0) {
    return (
      <section>
        <h2 style={{ fontSize: 16, fontWeight: 800, marginBottom: 18 }}>{groupLabel}</h2>
        <p style={{ color: 'var(--faint)' }}>No usage data for this range</p>
      </section>
    )
  }

  const maxRequests = Math.max(...data.map((entry) => entry.request_count))
  const maxTokens = Math.max(...data.map((entry) => entry.input_tokens + entry.output_tokens))

  return (
    <section>
      <h2 style={{ fontSize: 16, fontWeight: 800, marginBottom: 18 }}>{groupLabel}</h2>
      <ul style={{ display: 'flex', flexDirection: 'column', gap: 14, listStyle: 'none', margin: 0, padding: 0 }}>
        {data.map((entry, index) => {
          const totalTokens = entry.input_tokens + entry.output_tokens
          const color = BAR_COLORS[index % BAR_COLORS.length]
          return (
            <li key={entry.label} aria-label={entry.label} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 150px', gap: 14, alignItems: 'center' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
                  <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 2, background: color, flexShrink: 0 }} />
                  {entry.label}
                </div>
                {entry.estimated_count > 0 && (
                  <div style={{ fontSize: 11, color: 'var(--amber)', marginTop: 2 }}>
                    ~ {entry.estimated_count} requests have an estimated timestamp
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <div style={{ height: 16, borderRadius: 5, background: 'var(--card2)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: widthPercent(entry.request_count, maxRequests), background: color, borderRadius: 5 }} />
                </div>
                <div style={{ height: 6, borderRadius: 3, background: 'var(--card2)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: widthPercent(totalTokens, maxTokens), background: color, opacity: 0.45, borderRadius: 3 }} />
                </div>
              </div>
              <div style={{ textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                {entry.request_count.toLocaleString()} req · {formatTokens(totalTokens)} tok
              </div>
            </li>
          )
        })}
      </ul>
      <div style={{ display: 'flex', gap: 18, marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)', fontSize: 11.5, color: 'var(--faint)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span aria-hidden="true" style={{ width: 14, height: 8, borderRadius: 3, background: 'var(--muted)' }} />
          requests
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span aria-hidden="true" style={{ width: 14, height: 4, borderRadius: 2, background: 'var(--muted)', opacity: 0.45 }} />
          tokens
        </span>
      </div>
    </section>
  )
}
