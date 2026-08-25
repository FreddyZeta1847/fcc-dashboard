/*
 * Usage.tsx
 * Usage page. Unlike every self-fetching component from Phases 5-6a, this
 * page OWNS the selected RangeName (local useState, defaulting to
 * 'last_7_days' to match Overview's MoneySavedHeadline) and the single
 * useStats(range) call. The two VolumeChart instances mount here as
 * simple, prop-driven children that consume this SAME query result — they
 * must react to the range RangeSelector just picked, not independently
 * guess at one, so fetching is deliberately centralized here rather than
 * delegated back down.
 *
 * `isError` is checked before the `isLoading || !data` guard, same
 * panel-local-error pattern as MoneySavedHeadline.tsx/
 * RecentRequestsFeed.tsx — otherwise a failed fetch would look stuck on
 * "Loading…" forever instead of surfacing the failure.
 *
 * `ByProviderVolume`/`ByModelVolume` don't carry a `label` field directly
 * (VolumeChart's generic shape) — mapped here at the call site rather than
 * making VolumeChart aware of two different backend shapes: `provider`
 * alone for the provider chart, `"provider / model"` for the model chart
 * (both fields kept together since two providers can share a model name).
 */
import { useState } from 'react'
import { useStats } from '../hooks/useStats'
import { RangeSelector } from '../components/RangeSelector'
import { VolumeChart } from '../components/VolumeChart'
import type { RangeName } from '../api/types'

export function Usage() {
  const [range, setRange] = useState<RangeName>('last_7_days')
  const { data, isLoading, isError } = useStats(range)

  return (
    <div className="flex flex-col gap-4 p-4">
      <RangeSelector value={range} onChange={setRange} />
      {isError ? (
        <div className="p-4 text-red-600">Couldn't load usage data.</div>
      ) : isLoading || !data ? (
        <div className="p-4">Loading usage data…</div>
      ) : (
        <div className="flex flex-col gap-6">
          <VolumeChart
            data={data.volume_by_provider.map((v) => ({ label: v.provider, ...v }))}
            groupLabel="By Provider"
          />
          <VolumeChart
            data={data.volume_by_model.map((v) => ({ label: `${v.provider} / ${v.model}`, ...v }))}
            groupLabel="By Model"
          />
        </div>
      )}
    </div>
  )
}
