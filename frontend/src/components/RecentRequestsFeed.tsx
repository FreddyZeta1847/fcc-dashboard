/*
 * RecentRequestsFeed.tsx
 * Table of the most recent gateway requests (fixed limit of 20, no
 * pagination — a "load more" view is a later task). Owns its own
 * useRecentRequests() query, same self-fetching pattern as StatusPanel
 * and MoneySavedHeadline, so Task 6 can compose panels without
 * prop-drilling query results.
 *
 * `occurred_at_is_estimated` arrives as a raw SQLite integer (0 or 1),
 * not a JSON boolean — checked here via truthiness, never `=== true`,
 * or the estimated-marker badge would silently never render.
 *
 * `provider` and `downstream_model` share one cell ("provider → model")
 * instead of two: sample data like provider "deepseek" and
 * downstream_model "deepseek-chat" makes "deepseek" a substring of both,
 * so two separate cells give a text query on /deepseek/i two matching
 * elements instead of one.
 */
import { useRecentRequests } from '../hooks/useRecentRequests'
import type { RequestRow } from '../api/types'

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function formatSavings(savings: number | null) {
  return savings === null ? '—' : currencyFormatter.format(savings)
}

function RequestTableRow({ row }: { row: RequestRow }) {
  const isEstimated = Boolean(row.occurred_at_is_estimated)

  return (
    <tr className="border-b border-gray-200">
      <td className="px-3 py-2 text-sm text-gray-700">
        {new Date(row.occurred_at).toLocaleString()}
        {isEstimated && (
          <span
            title="Timestamp estimated — not reported by the provider"
            className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800"
          >
            estimated
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-sm text-gray-700">
        {row.provider ?? '—'} → {row.downstream_model ?? '—'}
      </td>
      <td className="px-3 py-2 text-sm text-gray-700">{row.status}</td>
      <td className="px-3 py-2 text-sm text-gray-700">
        {row.input_tokens ?? '—'} / {row.output_tokens ?? '—'}
      </td>
      <td className="px-3 py-2 text-sm text-gray-700">{formatSavings(row.savings)}</td>
    </tr>
  )
}

export function RecentRequestsFeed() {
  const { data, isLoading } = useRecentRequests(20)

  if (isLoading || !data) {
    return <div className="p-4">Loading recent requests…</div>
  }

  return (
    <section className="p-4">
      <h2 className="text-sm font-medium text-gray-500">Recent requests</h2>
      {data.results.length === 0 ? (
        <p className="text-sm text-gray-500">No requests yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-gray-300 text-left">
                <th className="px-3 py-2 text-xs font-medium text-gray-500">Occurred at</th>
                <th className="px-3 py-2 text-xs font-medium text-gray-500">Provider → Model</th>
                <th className="px-3 py-2 text-xs font-medium text-gray-500">Status</th>
                <th className="px-3 py-2 text-xs font-medium text-gray-500">Tokens (in/out)</th>
                <th className="px-3 py-2 text-xs font-medium text-gray-500">Savings</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => (
                <RequestTableRow key={row.request_id} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
