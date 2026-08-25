/*
 * Usage.tsx
 * Usage page. Unlike self-fetching panel components elsewhere, this page
 * OWNS the selected RangeName (local useState, defaulting to
 * 'last_7_days' to match Overview's MoneySavedHeadline) and the single
 * useStats(range) call. CumulativeSavingsChart and both VolumeChart
 * instances mount here as simple, prop-driven children that consume this
 * SAME query result — they must react to the range RangeSelector just
 * picked, not independently guess at one, so fetching is deliberately
 * centralized here rather than delegated back down.
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
import { CumulativeSavingsChart } from '../components/CumulativeSavingsChart'
import { Card } from '../components/Card'
import type { RangeName } from '../api/types'

export function Usage() {
  const [range, setRange] = useState<RangeName>('last_7_days')
  const { data, isLoading, isError } = useStats(range)

  return (
    <div style={{ maxWidth: 1060 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 20, marginBottom: 28, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-.02em' }}>Usage</div>
          <div style={{ color: 'var(--muted)' }}>Request and token volume over time</div>
        </div>
        <RangeSelector value={range} onChange={setRange} />
      </div>

      {isError ? (
        <Card accent="red">
          <p style={{ color: 'var(--red)' }}>Couldn't load usage data.</p>
        </Card>
      ) : isLoading || !data ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <Card style={{ height: 220 }} />
          <Card style={{ height: 260 }} />
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <Card accent="green">
            <CumulativeSavingsChart data={data.daily_savings} />
          </Card>
          <Card accent="violet">
            <VolumeChart
              data={data.volume_by_provider.map((v) => ({ label: v.provider, ...v }))}
              groupLabel="By Provider"
            />
          </Card>
          <Card accent="amber">
            <VolumeChart
              data={data.volume_by_model.map((v) => ({ label: `${v.provider} / ${v.model}`, ...v }))}
              groupLabel="By Model"
            />
          </Card>
        </div>
      )}
    </div>
  )
}
