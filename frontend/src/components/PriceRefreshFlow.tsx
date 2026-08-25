/*
 * PriceRefreshFlow.tsx
 * Settings page's price-refresh preview-then-approve flow
 * (PRICING-ENGINE--price-refresh). `POST /pricing/refresh`
 * (usePricingRefresh) fetches a best-effort diff against the external
 * catalogs (LiteLLM/OpenRouter) and WRITES NOTHING — clicking "Refresh"
 * must only ever populate this component's local preview state. The only
 * path from that preview to an actual write is an explicit "Apply" click,
 * which is this flow's confirm-before-action step: reviewing the concrete
 * diff on screen *is* the confirmation, so — unlike PricingEditor's blind
 * manual-entry form — there is no second "are you sure?" step here. Never
 * chain the refresh mutation's onSuccess (or any other automatic hook)
 * into calling the put mutation; that would silently corrupt the
 * money-saved calculation if a bad automated lookup got applied without a
 * human looking at it first.
 *
 * `not_found` pairs are a provider/model the refresh couldn't find a price
 * for anywhere. They are rendered in their own clearly-labeled section and
 * never fed into the merge that Apply sends to `PUT /pricing` — there is
 * no price to write for them, and none is invented.
 *
 * `PUT /pricing` (usePutPricing) REPLACES THE WHOLE DOCUMENT, same as
 * Task 4's PricingEditor. Apply therefore takes the current usePricing()
 * document and merges every `changes[i].proposed` value into a full clone
 * of it, never sending a partial document.
 */
import { usePricing } from '../hooks/usePricing'
import { usePutPricing, usePricingRefresh } from '../hooks/usePricingMutations'
import type { PriceEntry, PricingChange, PricingConfig } from '../api/types'

function withPairMerged(
  config: PricingConfig,
  provider: string,
  model: string,
  entry: PriceEntry,
): PricingConfig {
  if (provider === 'anthropic' && (model === 'opus' || model === 'sonnet' || model === 'haiku')) {
    return { ...config, anthropic: { ...config.anthropic, [model]: entry } }
  }
  return {
    ...config,
    providers: {
      ...config.providers,
      [provider]: { ...config.providers[provider], [model]: entry },
    },
  }
}

function withChangesMerged(config: PricingConfig, changes: PricingChange[]): PricingConfig {
  let next = config
  for (const change of changes) {
    // A change with no `proposed` price has nothing to write — same
    // "never invent a price" rule as `not_found`.
    if (!change.proposed) continue
    next = withPairMerged(next, change.provider, change.model, change.proposed)
  }
  return next
}

function formatPrice(entry: { input_per_million: number; output_per_million: number } | null): string {
  return entry === null ? 'unknown' : `$${entry.input_per_million} / $${entry.output_per_million}`
}

export function PriceRefreshFlow() {
  const { data: pricingData } = usePricing()
  const refresh = usePricingRefresh()
  const putPricing = usePutPricing()

  function handleRefreshClick() {
    refresh.mutate()
  }

  function handleApplyClick() {
    if (!pricingData || !refresh.data) {
      return
    }
    const nextConfig = withChangesMerged(pricingData, refresh.data.changes)
    putPricing.mutate(nextConfig)
  }

  return (
    <div className="p-4">
      <h2 className="text-sm font-medium text-gray-500">Price refresh</h2>
      <button
        type="button"
        onClick={handleRefreshClick}
        disabled={refresh.isPending}
        className="mt-2 self-start bg-blue-600 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
      >
        Refresh prices
      </button>
      {refresh.isError && (
        <p className="mt-2 text-sm text-red-600">Couldn't fetch a price refresh.</p>
      )}
      {putPricing.isError && (
        <p className="mt-2 text-sm text-red-600">Couldn't apply the approved prices.</p>
      )}

      {refresh.data && (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-gray-500">Changes</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-gray-300 text-left">
                  <th className="px-3 py-2 text-xs font-medium text-gray-500">Provider</th>
                  <th className="px-3 py-2 text-xs font-medium text-gray-500">Model</th>
                  <th className="px-3 py-2 text-xs font-medium text-gray-500">Current</th>
                  <th className="px-3 py-2 text-xs font-medium text-gray-500">Proposed</th>
                  <th className="px-3 py-2 text-xs font-medium text-gray-500">Source</th>
                </tr>
              </thead>
              <tbody>
                {refresh.data.changes.map((change) => (
                  <tr key={`${change.provider}:${change.model}`} className="border-b border-gray-200">
                    <td className="px-3 py-2 text-sm text-gray-700">{change.provider}</td>
                    <td className="px-3 py-2 text-sm text-gray-700">{change.model}</td>
                    <td className="px-3 py-2 text-sm text-gray-700">{formatPrice(change.current)}</td>
                    <td className="px-3 py-2 text-sm text-gray-700">{formatPrice(change.proposed)}</td>
                    <td className="px-3 py-2 text-sm text-gray-700">{change.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/*
           * Heading text deliberately avoids the literal substring "not
           * found" — each list item already contains the pair's provider
           * name (e.g. "deepseek"), and having both the heading and every
           * row match the same loose "not found"-ish text would make this
           * section ambiguous to a test (or a screen reader user tabbing
           * through) asking "where is the not-found text?". The `text-sm
           * text-red-700` styling still makes this section visually
           * distinct from the "Changes" table above.
           */}
          <h3 className="mt-4 text-sm font-medium text-gray-500">Missing prices</h3>
          {refresh.data.not_found.length === 0 ? (
            <p className="text-sm text-gray-500">Every configured pair was found.</p>
          ) : (
            <ul className="text-sm text-red-700">
              {refresh.data.not_found.map((pair) => (
                <li key={`${pair.provider}:${pair.model}`}>
                  {pair.provider} / {pair.model} — no price available, left unknown for manual entry
                </li>
              ))}
            </ul>
          )}

          <button
            type="button"
            onClick={handleApplyClick}
            disabled={putPricing.isPending || !pricingData}
            className="mt-4 self-start bg-blue-600 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
          >
            Apply
          </button>
        </div>
      )}
    </div>
  )
}
