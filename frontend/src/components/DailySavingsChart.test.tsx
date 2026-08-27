/*
 * DailySavingsChart.test.tsx
 * Verifies that each bar reflects that day's OWN savings (not a running
 * total), that the header still reports the range total, and the empty-range
 * fallback message.
 *
 * The bar-height assertions matter more than they look: the bug this chart
 * replaced was that a zero-savings day was visually indistinguishable from a
 * good one, because a cumulative series never goes down. So the tests check
 * that a zero day and the busiest day render at clearly different heights.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DailySavingsChart } from './DailySavingsChart'

describe('DailySavingsChart', () => {
  it('reports the range total in the header', () => {
    render(
      <DailySavingsChart
        data={[
          { date: '2026-08-23', savings: 5 },
          { date: '2026-08-24', savings: 0 },
          { date: '2026-08-25', savings: 3.5 },
        ]}
      />,
    )
    expect(screen.getByText('$8.50')).toBeInTheDocument()
    expect(screen.getByText(/range total/i)).toBeInTheDocument()
  })

  it("sizes each bar by that day's own savings, not a running total", () => {
    const { container } = render(
      <DailySavingsChart
        data={[
          { date: '2026-08-23', savings: 10 },
          { date: '2026-08-24', savings: 5 },
        ]}
      />,
    )
    const bars = Array.from(container.querySelectorAll('div[title]')) as HTMLElement[]
    expect(bars).toHaveLength(2)

    // Day 1 is the max -> full height. Day 2 is half of it -> 50%.
    // Under the old cumulative behaviour day 2 would have been the tallest
    // bar (10 + 5 = 15), so this assertion is what pins the change.
    expect(bars[0].style.height).toBe('100%')
    expect(bars[1].style.height).toBe('50%')
  })

  it('renders a zero-savings day visibly flatter than an active day', () => {
    const { container } = render(
      <DailySavingsChart
        data={[
          { date: '2026-08-23', savings: 4 },
          { date: '2026-08-24', savings: 0 },
        ]}
      />,
    )
    const bars = Array.from(container.querySelectorAll('div[title]')) as HTMLElement[]
    expect(parseFloat(bars[0].style.height)).toBeGreaterThan(
      parseFloat(bars[1].style.height),
    )
    expect(bars[1].style.height).toBe('1%')
  })

  it("labels each bar with that day's own amount", () => {
    const { container } = render(
      <DailySavingsChart data={[{ date: '2026-08-23', savings: 2.25 }]} />,
    )
    const bar = container.querySelector('div[title]') as HTMLElement
    expect(bar.title).toContain('$2.25')
    expect(bar.title).toContain('Aug 23')
  })

  it('renders a neutral message when there is no data', () => {
    render(<DailySavingsChart data={[]} />)
    expect(screen.getByText(/no usage data/i)).toBeInTheDocument()
  })

  it('labels the chart with the first and last day in range', () => {
    render(
      <DailySavingsChart
        data={[
          { date: '2026-08-19', savings: 1 },
          { date: '2026-08-20', savings: 1 },
        ]}
      />,
    )
    expect(screen.getByText('Aug 19')).toBeInTheDocument()
    expect(screen.getByText('Aug 20')).toBeInTheDocument()
  })

  it('does not divide by zero when every day is zero', () => {
    const { container } = render(
      <DailySavingsChart
        data={[
          { date: '2026-08-19', savings: 0 },
          { date: '2026-08-20', savings: 0 },
        ]}
      />,
    )
    const bars = Array.from(container.querySelectorAll('div[title]')) as HTMLElement[]
    for (const bar of bars) {
      expect(bar.style.height).toBe('1%')
    }
    expect(screen.getByText('$0.00')).toBeInTheDocument()
  })
})
