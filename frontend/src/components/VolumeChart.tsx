/*
 * VolumeChart.tsx
 * Reusable bar chart for a volume breakdown (by provider or by model —
 * the two shapes share `request_count` / `input_tokens` / `output_tokens`
 * / `estimated_count`, so this component takes a generic `{ label, ... }`
 * entry rather than knowing about `ByProviderVolume` / `ByModelVolume`
 * directly; Usage.tsx maps each backend shape onto `label` at the call
 * site). Renders TWO grouped bars per entry (`request_count` on the left
 * axis, total tokens on the right) since call volume and token volume
 * live on very different scales — a handful of requests vs. thousands of
 * tokens — and FRONTEND--usage asks for both to be visible.
 *
 * The chart's SVG is intentionally not the only way to read this data:
 * each entry also gets its own <li>, carrying the label as its accessible
 * name (via aria-label, since "listitem" doesn't reliably compute a name
 * from content) and, when `estimated_count > 0`, an "N estimated" marker
 * scoped to that SAME <li> — never a page-global note — mirroring the
 * per-row estimated-timestamp badge in RecentRequestsFeed.tsx.
 *
 * The X axis renders bars grouped by `label` but suppresses its own tick
 * text (`tick={false}`) rather than also printing each label above the
 * bars: Recharts' SVG <text> ticks are real DOM text nodes, so leaving
 * them on would duplicate every label (once in the SVG, once in the
 * <li>) and make a plain text query for that label ambiguous. The <li>
 * list is the single source of visible label text; the chart stays
 * readable via its Tooltip and color-coded bars.
 */
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

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

export function VolumeChart({ data, groupLabel }: VolumeChartProps) {
  return (
    <section className="p-4">
      <h2 className="text-sm font-medium text-gray-500">{groupLabel}</h2>
      {data.length === 0 ? (
        <p className="text-sm text-gray-500">No usage data for this range</p>
      ) : (
        <>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.map((entry) => ({ ...entry, total_tokens: entry.input_tokens + entry.output_tokens }))}>
                <XAxis dataKey="label" tick={false} />
                <YAxis yAxisId="requests" />
                <YAxis yAxisId="tokens" orientation="right" />
                <Tooltip />
                <Bar yAxisId="requests" dataKey="request_count" name="Requests" fill="#2563eb" isAnimationActive={false} />
                <Bar yAxisId="tokens" dataKey="total_tokens" name="Tokens (in+out)" fill="#16a34a" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <ul className="mt-2 flex flex-col gap-1">
            {data.map((entry) => (
              <li key={entry.label} aria-label={entry.label} className="text-sm text-gray-700">
                <span className="font-medium">{entry.label}</span>
                {' — '}
                {entry.request_count} requests, {entry.input_tokens} in / {entry.output_tokens} out tokens
                {entry.estimated_count > 0 && (
                  <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800">
                    {entry.estimated_count} estimated
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
