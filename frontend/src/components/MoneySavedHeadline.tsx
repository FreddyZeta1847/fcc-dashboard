/*
 * MoneySavedHeadline.tsx
 * Dashboard's core "how much did this save me" figure. Calls useStats()
 * itself with a fixed range (no range selector here — that is the Usage
 * page's job in Phase 6), same self-fetching pattern as StatusPanel.
 *
 * `total_savings: null` means the pricing engine has never had a config to
 * price against — a fact distinct from every request summing to a real
 * $0.00. Collapsing the two would silently tell the user "this saved you
 * nothing" when the true state is "we can't tell you yet". This mirrors a
 * project-wide invariant that also runs through the backend's pricing
 * engine (see backend/src/fcc_dashboard's pricing code): never assume
 * free. So the null branch renders a distinct "no pricing configured"
 * message and deliberately avoids any $/0.00-shaped text.
 */
import { useStats } from '../hooks/useStats'

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

export function MoneySavedHeadline() {
  const { data, isLoading } = useStats('last_7_days')

  if (isLoading || !data) {
    return <div className="p-4">Loading savings…</div>
  }

  const { total_savings, unpriced_request_count } = data

  return (
    <section className="p-4">
      <h2 className="text-sm font-medium text-gray-500">Money saved (last 7 days)</h2>
      {total_savings === null ? (
        <p className="text-2xl font-semibold text-gray-500">No pricing configured yet</p>
      ) : (
        <p className="text-3xl font-semibold text-green-700">
          {currencyFormatter.format(total_savings)}
        </p>
      )}
      {unpriced_request_count > 0 && (
        <p className="text-sm text-gray-500">
          {unpriced_request_count} requests excluded — unpriced
        </p>
      )}
    </section>
  )
}
