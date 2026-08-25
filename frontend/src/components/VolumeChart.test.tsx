/*
 * VolumeChart.test.tsx
 * Guards VolumeChart's accessible-DOM contract, not Recharts' SVG
 * internals: every entry must be independently findable as a listitem by
 * its label, and the estimated-timestamps marker must be scoped inside
 * that SAME listitem (never a page-global note) so a consumer can't
 * misattribute one entry's estimate to another. See VolumeChart.tsx for
 * how ResponsiveContainer is kept renderable under jsdom.
 */
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { VolumeChart } from './VolumeChart'

const data = [
  { label: 'deepseek', request_count: 10, input_tokens: 1000, output_tokens: 2000, estimated_count: 0 },
  { label: 'openrouter', request_count: 3, input_tokens: 300, output_tokens: 400, estimated_count: 2 },
]

describe('VolumeChart', () => {
  it('renders a bar chart with a bar per entry', () => {
    render(<VolumeChart data={data} groupLabel="Provider" />)
    // Recharts renders SVG; assert on data presence via accessible text
    // (a legend/axis label or a rendered data table fallback), not on
    // SVG internals -- your call how you expose this, but it must be
    // genuinely observable in the DOM, not just "the SVG exists."
    expect(screen.getByText('deepseek')).toBeInTheDocument()
    expect(screen.getByText('openrouter')).toBeInTheDocument()
  })

  it('marks an entry with a nonzero estimated_count as having estimated timestamps, scoped to that entry', () => {
    render(<VolumeChart data={data} groupLabel="Provider" />)
    // Each entry must be wrapped in its own accessible list item (or
    // equivalent container) carrying its label as accessible text, so
    // the estimated marker can be looked up scoped to ONE entry rather
    // than searched for anywhere on the page.
    const openrouterItem = screen.getByRole('listitem', { name: /openrouter/i })
    expect(within(openrouterItem).getByText(/2.*estimated/i)).toBeInTheDocument()
  })

  it('does not mark an entry with zero estimated_count', () => {
    render(<VolumeChart data={data} groupLabel="Provider" />)
    const deepseekItem = screen.getByRole('listitem', { name: /deepseek/i })
    expect(within(deepseekItem).queryByText(/estimated/i)).not.toBeInTheDocument()
  })

  it('renders a neutral message when data is empty', () => {
    render(<VolumeChart data={[]} groupLabel="Provider" />)
    expect(screen.getByText(/no data|no usage/i)).toBeInTheDocument()
  })
})
