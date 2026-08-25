/*
 * Usage.tsx
 * Usage page (Task 2 skeleton — Task 3 adds the real charts). Unlike every
 * self-fetching component from Phases 5-6a, this page OWNS the selected
 * RangeName (local useState, defaulting to 'last_7_days' to match Overview's
 * MoneySavedHeadline) and the single useStats(range) call. Task 3's chart
 * components mount here as simple, prop-driven children that consume this
 * SAME query result — they must react to the range RangeSelector just
 * picked, not independently guess at one, so fetching is deliberately
 * centralized here rather than delegated back down.
 */
import { useState } from 'react'
import { useStats } from '../hooks/useStats'
import { RangeSelector } from '../components/RangeSelector'
import type { RangeName } from '../api/types'

export function Usage() {
  const [range, setRange] = useState<RangeName>('last_7_days')
  useStats(range)

  return (
    <div className="flex flex-col gap-4 p-4">
      <RangeSelector value={range} onChange={setRange} />
      <div>Charts coming in Task 3</div>
    </div>
  )
}
