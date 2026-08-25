/*
 * RangeSelector.tsx
 * Controlled 4-way range toggle (today / last 7 days / last 30 days / all
 * time) for the Usage page. Stateless like Sidebar.tsx: the parent
 * (Usage.tsx) owns the selected RangeName and passes it down along with
 * onChange, so Usage's useStats(range) call always reflects exactly
 * what's on screen. A pill-button group inside a rounded outer container,
 * matching the approved design mockup.
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
    <div
      style={{
        display: 'flex',
        gap: 4,
        background: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: 4,
      }}
    >
      {RANGES.map(({ id, label }) => {
        const isActive = id === value
        return (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            style={{
              font: 'inherit',
              fontSize: 13,
              fontWeight: 700,
              padding: '7px 14px',
              border: 'none',
              borderRadius: 9,
              cursor: 'pointer',
              background: isActive ? 'var(--card2)' : 'transparent',
              color: isActive ? 'var(--text)' : 'var(--muted)',
              whiteSpace: 'nowrap',
            }}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
