/*
 * Skeleton.tsx
 * Pulsing placeholder bar for loading states, replacing plain "Loading…"
 * text across every redesigned panel. `delay` staggers a group of
 * skeleton bars (e.g. a fake heading + a fake value) so they don't all
 * pulse perfectly in sync, matching the approved design mockup. Uses the
 * `fccPulse` keyframe defined in index.css.
 */
interface SkeletonProps {
  width?: string | number
  height?: string | number
  delay?: number
}

export function Skeleton({ width = '100%', height = 14, delay = 0 }: SkeletonProps) {
  return (
    <div
      style={{
        width,
        height,
        borderRadius: 6,
        background: 'var(--card2)',
        animation: `fccPulse 1.2s ${delay}s infinite`,
      }}
    />
  )
}
