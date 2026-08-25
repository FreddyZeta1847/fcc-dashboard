/*
 * StatusPanel.tsx
 * Renders FCC reachability (`fcc_status`) and per-provider health from
 * useStatus(). Deliberately does NOT handle useStatus()'s `isError` case
 * (dashboard's own backend unreachable) — that is App.tsx's job (the
 * backend-unreachable resilience gate), so this panel stays reusable
 * inside a reachable-backend dashboard without duplicating a full-page
 * fallback. Owns its own query (no props) so Overview can compose panels
 * without prop-drilling query results.
 */
import { useStatus } from '../hooks/useStatus'
import type { ProviderHealthStatus } from '../api/types'
import { Card } from './Card'
import { Skeleton } from './Skeleton'

const PROVIDER_STATUS_LABELS: Record<ProviderHealthStatus, string> = {
  ok: 'OK',
  stale_key: 'Stale key',
  rate_limited: 'Rate limited',
  down: 'Down',
}

const PROVIDER_STATUS_COLORS: Record<ProviderHealthStatus, string> = {
  ok: 'var(--green)',
  stale_key: 'var(--amber)',
  rate_limited: 'var(--violet)',
  down: 'var(--red)',
}

const PROVIDER_STATUS_TINTS: Record<ProviderHealthStatus, string> = {
  ok: 'var(--greenT)',
  stale_key: 'var(--amberT)',
  rate_limited: 'var(--violetT)',
  down: 'var(--redT)',
}

export function StatusPanel() {
  const { data, isLoading } = useStatus()

  if (isLoading || !data) {
    return (
      <Card accent="blue" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Skeleton width="45%" height={16} />
        <Skeleton width="90%" height={12} delay={0.15} />
        <Skeleton width="85%" height={12} delay={0.3} />
        <Skeleton width="88%" height={12} delay={0.45} />
      </Card>
    )
  }

  const fccUp = data.fcc_status === 'up'

  return (
    <Card accent="blue">
      <h2 style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.07em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 12 }}>
        FCC status
      </h2>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span
          aria-hidden="true"
          style={{
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: fccUp ? 'var(--green)' : 'var(--red)',
            boxShadow: `0 0 0 4px ${fccUp ? 'var(--greenT)' : 'var(--redT)'}`,
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: 16, fontWeight: 800 }}>{fccUp ? 'FCC is up' : 'FCC is down'}</span>
      </div>

      {data.providers.length === 0 ? (
        <p style={{ color: 'var(--faint)' }}>No provider issues.</p>
      ) : (
        <ul style={{ display: 'flex', flexDirection: 'column', listStyle: 'none', margin: 0, padding: 0 }}>
          {data.providers.map((provider) => (
            <li
              key={provider.provider}
              aria-label={provider.provider}
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0,1fr) auto auto',
                gap: 10,
                alignItems: 'center',
                padding: '9px 0',
                borderTop: '1px solid var(--border)',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                <span
                  aria-hidden="true"
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: PROVIDER_STATUS_COLORS[provider.status],
                    flexShrink: 0,
                  }}
                />
                <span style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {provider.provider}
                </span>
              </span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  padding: '2px 9px',
                  borderRadius: 999,
                  background: PROVIDER_STATUS_TINTS[provider.status],
                  color: PROVIDER_STATUS_COLORS[provider.status],
                  whiteSpace: 'nowrap',
                }}
              >
                {PROVIDER_STATUS_LABELS[provider.status]}
              </span>
              <span style={{ fontSize: 11.5, color: 'var(--faint)', textAlign: 'right', whiteSpace: 'nowrap' }}>
                {provider.last_error_at ?? ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
