/*
 * PricingEditor.tsx
 * Settings page's pricing config editor. Two parts: (1) a read-only view
 * of every currently-configured (provider, model) price pair — the 3
 * Anthropic tiers from `config.anthropic` plus everything nested under
 * `config.providers` — and (2) a small manual add/edit form.
 *
 * `PUT /pricing` (usePutPricing) REPLACES THE WHOLE DOCUMENT — there is no
 * partial-update endpoint. Submitting the form therefore always builds a
 * full clone of the current usePricing() data with only the one edited
 * pair changed, never a document containing just that pair, or every other
 * provider's prices would be silently deleted on write (see BACKEND--api).
 *
 * Save is two-step (this project's confirm-before-write rule,
 * FRONTEND--security): clicking "Save" only stages the pending pair and
 * flips the form into a "Confirm?" state; usePutPricing().mutate is called
 * only from the follow-up "Confirm" click. "Cancel" discards the staged
 * pair without writing anything.
 *
 * A (provider, model) pair that has no price entry anywhere in the config
 * renders as "unknown" (never blank or $0). Nothing this component
 * currently displays can actually be in that state — every row it builds
 * comes from a key that exists in the config, so a lookup always succeeds
 * — but `formatPrice` is written to hold for a future caller (e.g. a table
 * page joining live request data against pricing) that can feed it an
 * unconfigured pair.
 */
import { useId, useState } from 'react'
import { usePricing } from '../hooks/usePricing'
import { usePutPricing } from '../hooks/usePricingMutations'
import type { PriceEntry, PricingConfig } from '../api/types'

interface PricingRow {
  provider: string
  model: string
  entry: PriceEntry | undefined
}

function buildRows(config: PricingConfig): PricingRow[] {
  const rows: PricingRow[] = [
    { provider: 'anthropic', model: 'opus', entry: config.anthropic.opus },
    { provider: 'anthropic', model: 'sonnet', entry: config.anthropic.sonnet },
    { provider: 'anthropic', model: 'haiku', entry: config.anthropic.haiku },
  ]
  for (const [provider, models] of Object.entries(config.providers)) {
    for (const [model, entry] of Object.entries(models)) {
      rows.push({ provider, model, entry })
    }
  }
  return rows
}

function formatPrice(value: number | undefined): string {
  return value === undefined ? 'unknown' : `$${value}`
}

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

export function PricingEditor() {
  const { data, isLoading, isError } = usePricing()
  const putPricing = usePutPricing()

  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [inputPrice, setInputPrice] = useState('')
  const [outputPrice, setOutputPrice] = useState('')
  const [pendingConfirm, setPendingConfirm] = useState(false)

  const providerId = useId()
  const modelId = useId()
  const inputPriceId = useId()
  const outputPriceId = useId()

  if (isError) {
    return <div className="p-4 text-red-600">Couldn't load pricing config.</div>
  }
  if (isLoading || !data) {
    return <div className="p-4">Loading pricing…</div>
  }

  const rows = buildRows(data)

  function handleSaveClick() {
    setPendingConfirm(true)
  }

  function handleCancelClick() {
    setPendingConfirm(false)
  }

  function handleConfirmClick() {
    if (!data) {
      return
    }
    const entry: PriceEntry = {
      input_per_million: Number(inputPrice),
      output_per_million: Number(outputPrice),
    }
    const nextConfig = withPairMerged(data, provider, model, entry)
    putPricing.mutate(nextConfig, {
      onSuccess: () => {
        setProvider('')
        setModel('')
        setInputPrice('')
        setOutputPrice('')
        setPendingConfirm(false)
      },
    })
  }

  return (
    <div className="p-4">
      <h2 className="text-sm font-medium text-gray-500">Pricing</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="border-b border-gray-300 text-left">
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Provider</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Model</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Input / M</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Output / M</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.provider}:${row.model}`} className="border-b border-gray-200">
                <td className="px-3 py-2 text-sm text-gray-700">{row.provider}</td>
                <td className="px-3 py-2 text-sm text-gray-700">{row.model}</td>
                <td className="px-3 py-2 text-sm text-gray-700">
                  {formatPrice(row.entry?.input_per_million)}
                </td>
                <td className="px-3 py-2 text-sm text-gray-700">
                  {formatPrice(row.entry?.output_per_million)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="mt-4 text-sm font-medium text-gray-500">Add / edit a price</h3>
      <form
        className="mt-2 flex flex-col gap-2"
        onSubmit={(event) => event.preventDefault()}
      >
        <div>
          <label htmlFor={providerId} className="block text-xs text-gray-500">
            Provider
          </label>
          <input
            id={providerId}
            type="text"
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
            className="border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label htmlFor={modelId} className="block text-xs text-gray-500">
            Model
          </label>
          <input
            id={modelId}
            type="text"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            className="border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label htmlFor={inputPriceId} className="block text-xs text-gray-500">
            Input price per million
          </label>
          <input
            id={inputPriceId}
            type="number"
            value={inputPrice}
            onChange={(event) => setInputPrice(event.target.value)}
            className="border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label htmlFor={outputPriceId} className="block text-xs text-gray-500">
            Output price per million
          </label>
          <input
            id={outputPriceId}
            type="number"
            value={outputPrice}
            onChange={(event) => setOutputPrice(event.target.value)}
            className="border border-gray-300 px-2 py-1 text-sm"
          />
        </div>

        {!pendingConfirm ? (
          <button
            type="button"
            onClick={handleSaveClick}
            className="self-start bg-blue-600 px-3 py-1 text-sm font-semibold text-white"
          >
            Save
          </button>
        ) : (
          <div className="flex gap-2">
            <span className="text-sm text-gray-700">Overwrite the full pricing config?</span>
            <button
              type="button"
              onClick={handleConfirmClick}
              className="bg-blue-600 px-3 py-1 text-sm font-semibold text-white"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={handleCancelClick}
              className="px-3 py-1 text-sm text-gray-600"
            >
              Cancel
            </button>
          </div>
        )}
      </form>
    </div>
  )
}
