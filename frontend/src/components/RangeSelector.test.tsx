/*
 * RangeSelector.test.tsx
 * Behavioral tests for RangeSelector: all 4 range buttons render, clicking
 * a button calls onChange with the matching RangeName, and the active
 * range is visually distinguished from inactive ones. Active/inactive is
 * expressed via inline style (CSS custom properties), not a Tailwind
 * className, so the check compares the rendered `style` attribute.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RangeSelector } from './RangeSelector'

describe('RangeSelector', () => {
  it('renders all 4 range options', () => {
    render(<RangeSelector value="last_7_days" onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /today/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /last 7 days/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /last 30 days/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /all time/i })).toBeInTheDocument()
  })

  it('calls onChange with the clicked range', async () => {
    const onChange = vi.fn()
    render(<RangeSelector value="last_7_days" onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: /last 30 days/i }))
    expect(onChange).toHaveBeenCalledWith('last_30_days')
  })

  it('visually distinguishes the selected range', () => {
    render(<RangeSelector value="today" onChange={vi.fn()} />)
    const active = screen.getByRole('button', { name: /^today$/i })
    const inactive = screen.getByRole('button', { name: /last 7 days/i })
    expect(active.getAttribute('style')).not.toBe(inactive.getAttribute('style'))
  })
})
