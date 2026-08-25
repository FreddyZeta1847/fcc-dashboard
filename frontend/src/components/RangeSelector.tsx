/*
 * RangeSelector.tsx
 * Controlled 4-way range toggle (today / last 7 days / last 30 days / all
 * time) for the Usage page. Stateless like Nav.tsx: the parent (Usage.tsx)
 * owns the selected RangeName and passes it down along with onChange, so
 * Usage's useStats(range) call always reflects exactly what's on screen.
 * Active/inactive styling mirrors Nav.tsx's button pattern.
 */
import type { RangeName } from '../api/types'

const RANGES: { id: RangeName; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'last_7_days', label: 'Last 7 days' },
  { id: 'last_30_days', label: 'Last 30 days' },
  { id: 'all_time', label: 'All time' },
]

interface RangeSelectorProps {
  value: RangeName
  onChange: (range: RangeName) => void
}

export function RangeSelector({ value, onChange }: RangeSelectorProps) {
  return (
    <div className="flex gap-2">
      {RANGES.map(({ id, label }) => {
        const isActive = id === value
        return (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            className={
              isActive
                ? 'px-3 py-1.5 rounded bg-blue-600 text-white font-semibold'
                : 'px-3 py-1.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200'
            }
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
