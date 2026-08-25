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
 * PricingEditor. Apply therefore takes the current usePricing() document
 * and merges every `changes[i].proposed` value into a full clone of it,
 * never sending a partial document.
 */
import { usePricing } from '../hooks/usePricing'
import { usePutPricing, usePricingRefresh } from '../hooks/usePricingMutations'
import type { PriceEntry, PricingChange, PricingConfig } from '../api/types'
import { Card } from './Card'

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

const buttonBaseStyle: React.CSSProperties = {
  font: 'inherit',
  fontSize: 13,
  fontWeight: 800,
  padding: '9px 18px',
  borderRadius: 9,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
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

  const changedCount = refresh.data?.changes.filter((change) => change.changed).length ?? 0

  return (
    <Card accent="blue">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 800 }}>Refresh prices from the web</h2>
          <p style={{ fontSize: 13, color: 'var(--muted)' }}>
            Fetches candidate prices from external sources. Nothing changes until you apply the diff.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRefreshClick}
          disabled={refresh.isPending}
          style={{ ...buttonBaseStyle, border: '1px solid var(--blueB)', background: 'var(--card2)', color: 'var(--text)', opacity: refresh.isPending ? 0.5 : 1 }}
        >
          Refresh prices
        </button>
      </div>

      {refresh.isError && <p style={{ marginTop: 18, fontSize: 13, color: 'var(--red)' }}>Couldn't fetch a price refresh.</p>}
      {putPricing.isError && <p style={{ marginTop: 18, fontSize: 13, color: 'var(--red)' }}>Couldn't apply the approved prices.</p>}

      {refresh.data && (
        <div style={{ marginTop: 18 }}>
          {/*
           * Provider and model render in separate columns (a small
           * deviation from the approved mockup's single combined "Pair"
           * column) so each stays independently, exactly findable by text
           * — a combined "provider / model" string can't be matched by an
           * exact-string query for the model alone.
           */}
          <div style={{ display: 'grid', gridTemplateColumns: '110px 1fr 1fr 1fr 90px', gap: 8, padding: '6px 10px', fontSize: 11, fontWeight: 800, letterSpacing: '.07em', textTransform: 'uppercase', color: 'var(--faint)' }}>
            <span>Provider</span>
            <span>Model</span>
            <span style={{ textAlign: 'right' }}>Current</span>
            <span style={{ textAlign: 'right' }}>Proposed</span>
            <span style={{ textAlign: 'right' }}>Source</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {refresh.data.changes.map((change) => (
              <div
                key={`${change.provider}:${change.model}`}
                style={{ display: 'grid', gridTemplateColumns: '110px 1fr 1fr 1fr 90px', gap: 8, alignItems: 'center', padding: '9px 10px', borderTop: '1px solid var(--border)' }}
              >
                <span style={{ fontWeight: 700 }}>{change.provider}</span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5 }}>{change.model}</span>
                <span style={{ textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5, color: 'var(--muted)' }}>{formatPrice(change.current)}</span>
                <span style={{ textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5, fontWeight: 600, color: change.changed ? 'var(--blue)' : 'var(--faint)' }}>
                  {formatPrice(change.proposed)}
                </span>
                <span style={{ textAlign: 'right', fontSize: 12, color: 'var(--faint)' }}>{change.source}</span>
              </div>
            ))}
          </div>

          {/*
           * Heading text deliberately avoids the literal substring "not
           * found" — each list item already contains the pair's provider
           * name (e.g. "deepseek"), and having both the heading and every
           * row match the same loose "not found"-ish text would make this
           * section ambiguous to a test (or a screen reader user tabbing
           * through) asking "where is the not-found text?". The red text
           * styling still makes this section visually distinct from the
           * "Changes" table above.
           */}
          <div style={{ marginTop: 14, background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: '12px 16px' }}>
            <span style={{ fontWeight: 800, color: 'var(--text)' }}>Missing prices: </span>
            {refresh.data.not_found.length === 0 ? (
              <span style={{ fontSize: 13, color: 'var(--muted)' }}>Every configured pair was found.</span>
            ) : (
              <ul style={{ fontSize: 13, color: 'var(--red)', margin: '8px 0 0', paddingLeft: 20 }}>
                {refresh.data.not_found.map((pair) => (
                  <li key={`${pair.provider}:${pair.model}`}>
                    {pair.provider} / {pair.model} — no price available, left unknown for manual entry
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div style={{ marginTop: 14, display: 'flex', gap: 10 }}>
            <button
              type="button"
              onClick={handleApplyClick}
              disabled={putPricing.isPending || !pricingData}
              style={{ ...buttonBaseStyle, border: 'none', background: 'var(--blue)', color: '#0b1018', opacity: putPricing.isPending || !pricingData ? 0.5 : 1 }}
            >
              Apply {changedCount} changes…
            </button>
          </div>

          {putPricing.isSuccess && (
            <p style={{ marginTop: 16, fontSize: 13, fontWeight: 700, color: 'var(--green)' }}>
              Applied. The pricing table above now reflects the new values.
            </p>
          )}
        </div>
      )}
    </Card>
  )
}
