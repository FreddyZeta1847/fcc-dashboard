/*
 * Nav.test.tsx
 * Behavioral spec for the tab navigation bar: renders all four tabs,
 * reports clicks via onTabChange, and visually marks the active tab.
 * Written before Nav.tsx exists (TDD).
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Nav } from './Nav'

describe('Nav', () => {
  it('renders all four tabs', () => {
    render(<Nav activeTab="overview" onTabChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /overview/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /usage/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /settings/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /database/i })).toBeInTheDocument()
  })

  it('calls onTabChange with the clicked tab', async () => {
    const onTabChange = vi.fn()
    render(<Nav activeTab="overview" onTabChange={onTabChange} />)
    await userEvent.click(screen.getByRole('button', { name: /settings/i }))
    expect(onTabChange).toHaveBeenCalledWith('settings')
  })

  it('visually distinguishes the active tab from inactive ones', () => {
    render(<Nav activeTab="database" onTabChange={vi.fn()} />)
    const active = screen.getByRole('button', { name: /database/i })
    const inactive = screen.getByRole('button', { name: /overview/i })
    expect(active.className).not.toBe(inactive.className)
  })
})
