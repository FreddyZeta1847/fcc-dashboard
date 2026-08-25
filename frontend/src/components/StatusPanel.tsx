/*
 * StatusPanel.tsx
 * Renders FCC reachability (`fcc_status`) and per-provider health from
 * useStatus(). Deliberately does NOT handle useStatus()'s `isError` case
 * (dashboard's own backend unreachable) — that is App.tsx's job (the
 * backend-unreachable resilience gate), so this panel stays reusable
 * inside a reachable-backend dashboard without duplicating a full-page
 * fallback. Owns its own query (no props) so Task 6 can compose panels
 * without prop-drilling query results.
 */
import { useStatus } from '../hooks/useStatus'
import type { ProviderHealthStatus } from '../api/types'

const PROVIDER_STATUS_LABELS: Record<ProviderHealthStatus, string> = {
  ok: 'OK',
  stale_key: 'Stale key',
  rate_limited: 'Rate limited',
  down: 'Down',
}

export function StatusPanel() {
  const { data, isLoading } = useStatus()

  if (isLoading || !data) {
    return <div>Loading status…</div>
  }

  const fccUp = data.fcc_status === 'up'

  return (
    <section>
      <h2>FCC status</h2>
      <div>
        <span
          aria-hidden="true"
          style={{
            display: 'inline-block',
            width: '0.6em',
            height: '0.6em',
            borderRadius: '50%',
            backgroundColor: fccUp ? 'green' : 'red',
            marginRight: '0.5em',
          }}
        />
        <span>{fccUp ? 'Up' : 'Down'}</span>
      </div>

      <h3>Providers</h3>
      {data.providers.length === 0 ? (
        <p>No provider issues.</p>
      ) : (
        <ul>
          {data.providers.map((provider) => (
            <li key={provider.provider}>
              <span>{provider.provider}</span>: {' '}
              <span>{PROVIDER_STATUS_LABELS[provider.status]}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
