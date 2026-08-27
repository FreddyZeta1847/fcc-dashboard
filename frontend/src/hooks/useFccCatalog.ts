/*
 * useFccCatalog.ts
 * TanStack Query hook for GET /fcc/catalog — the providers FCC currently has
 * configured, the models each can serve, and the provider values already seen
 * in our own requests table.
 *
 * Feeds the pricing editor's provider/model pickers, so the user selects
 * strings that FCC itself reports instead of typing them from memory (an
 * exact-match lookup where a typo fails silently).
 *
 * POLLING IS CONDITIONAL AND BACKS OFF. When FCC is reachable there is no
 * interval at all, matching usePricing's reasoning: this data reflects FCC's
 * configuration, which does not change from request traffic, so polling it
 * would be waste. But when FCC is *unreachable* the editor has fallen back to
 * manual entry, and the event that ends that state — FCC starting — produces
 * no signal this page would otherwise see.
 *
 * The fast rate only earns its keep in one window: the ~15s after a start,
 * where /control/start has already returned but FCC is not listening yet
 * (measured: down at t+5s and t+10s, up at t+15s). Past that window a start is
 * no longer plausibly in flight, so the interval drops to a slow heartbeat
 * rather than hammering at the same rate indefinitely.
 *
 * Three things already bound this further: React Query only runs the interval
 * while a component observes the query (so leaving Settings stops it),
 * `refetchIntervalInBackground` defaults to false (so an unfocused tab stops
 * it), and `refetchOnWindowFocus` catches an FCC that came up while the tab
 * was away. useControlStart/Stop additionally invalidate this query so a
 * dashboard-initiated change is noticed immediately.
 *
 * The query only errors on a transport failure. FCC being stopped is not an
 * error: the backend answers 200 with `available: false`.
 */
import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFccCatalog } from '../api/client'

/** While a start could plausibly be in flight — FCC takes ~15s to listen. */
const FAST_POLL_MS = 5_000

/** Once it clearly is not: enough to notice, cheap enough to leave running. */
const SLOW_POLL_MS = 30_000

/** How long the fast rate lasts after FCC first becomes unreachable. */
const FAST_WINDOW_MS = 60_000

export function useFccCatalog() {
  // When FCC first went away, or null while it is reachable. A ref rather
  // than state: it must not itself trigger a render, and the interval
  // callback reads it at tick time, not at render time.
  const unavailableSince = useRef<number | null>(null)

  const query = useQuery({
    queryKey: ['fcc-catalog'],
    queryFn: getFccCatalog,
    staleTime: 30_000,
    refetchInterval: (q) => {
      const data = q.state.data
      // No data yet means the first fetch is still in flight; nothing to poll
      // for. Reachable means stop entirely.
      if (!data || data.available) {
        return false
      }
      const since = unavailableSince.current
      if (since === null) {
        return FAST_POLL_MS
      }
      return Date.now() - since < FAST_WINDOW_MS ? FAST_POLL_MS : SLOW_POLL_MS
    },
  })

  const available = query.data?.available
  useEffect(() => {
    if (available === false) {
      // Only stamp the first transition, so the window measures how long FCC
      // has been down rather than resetting on every poll.
      if (unavailableSince.current === null) {
        unavailableSince.current = Date.now()
      }
    } else {
      unavailableSince.current = null
    }
  }, [available])

  return query
}
