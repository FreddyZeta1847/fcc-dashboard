/*
 * CumulativeSavingsChart.test.tsx
 * Verifies the running-total math (a plain client-side reduce over
 * per-day savings, not a pricing calculation) and the empty-range
 * fallback message.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CumulativeSavingsChart } from './CumulativeSavingsChart'

describe('CumulativeSavingsChart', () => {
  it('renders the cumulative (running) total, not just the last day amount', () => {
    render(
      <CumulativeSavingsChart
        data={[
          { date: '2026-08-23', savings: 5 },
          { date: '2026-08-24', savings: 0 },
          { date: '2026-08-25', savings: 3.5 },
        ]}
      />,
    )
    // 5 + 0 + 3.5 = 8.5 -- the header total must be the running sum, not
    // the last day's own $3.50 entry.
    expect(screen.getByText('$8.50')).toBeInTheDocument()
  })

  it('renders a neutral message when there is no data', () => {
    render(<CumulativeSavingsChart data={[]} />)
    expect(screen.getByText(/no usage data/i)).toBeInTheDocument()
  })

  it('labels the chart with the first and last day in range', () => {
    render(
      <CumulativeSavingsChart
        data={[
          { date: '2026-08-19', savings: 1 },
          { date: '2026-08-20', savings: 1 },
        ]}
      />,
    )
    expect(screen.getByText('Aug 19')).toBeInTheDocument()
    expect(screen.getByText('Aug 20')).toBeInTheDocument()
  })
})
