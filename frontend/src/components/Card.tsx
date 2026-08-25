/*
 * Card.tsx
 * Shared panel container used across every page — a subtly tinted
 * gradient background plus a matching border per accent color, the one
 * visual pattern this whole design repeats (money = green, status = blue,
 * process control = violet, refresh/warning = amber, error = red).
 * `accent="none"` renders a flat, untinted card for neutral containers
 * (e.g. the Database table view). Deliberately uses inline styles reading
 * CSS custom properties (index.css) rather than Tailwind utility classes,
 * since the accent color and its two derived tokens (…T for the tint,
 * …B for the border) are picked at render time from a prop, not from a
 * fixed set of Tailwind classes.
 */
import type { CSSProperties, ReactNode } from 'react'

export type CardAccent = 'green' | 'blue' | 'violet' | 'amber' | 'red' | 'none'

interface CardProps {
  accent?: CardAccent
  dashed?: boolean
  style?: CSSProperties
  className?: string
  children?: ReactNode
}

export function Card({ accent = 'none', dashed = false, style, className, children }: CardProps) {
  const background =
    accent === 'none' ? 'var(--card)' : `linear-gradient(150deg, var(--${accent}T), var(--card) 88%)`
  const borderColor = accent === 'none' ? 'var(--border)' : `var(--${accent}B)`

  return (
    <div
      className={className}
      style={{
        background,
        border: `${dashed ? '1.5px dashed' : '1px solid'} ${borderColor}`,
        borderRadius: 18,
        padding: '24px 28px',
        ...style,
      }}
    >
      {children}
    </div>
  )
}
