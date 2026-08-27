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
 * POLLING IS CONDITIONAL, and the condition is the point. When FCC is
 * reachable this behaves like usePricing: no interval at all, because the
 * data reflects FCC's configuration, which does not change from request
 * traffic. But when FCC is *unreachable* the editor has fallen back to manual
 * entry, and the event that ends that state — FCC starting up — produces no
 * signal this page would otherwise notice. So while `available` is false the
 * hook polls, and stops the moment FCC answers.
 *
 * That covers FCC being started from anywhere: this dashboard's own Start
 * button, FCC's admin UI, or a terminal. `useControlStart` additionally
 * invalidates this query so a dashboard-initiated start feels immediate
 * rather than waiting for the next tick; the poll is what makes the other
 * routes work, and what covers FCC taking ~15s to finish booting after
 * /control/start has already returned.
 *
 * The query only errors on a transport failure. FCC being stopped is not an
 * error: the backend answers 200 with `available: false`.
 */
import { useQuery } from '@tanstack/react-query'
import { getFccCatalog } from '../api/client'

/** How often to re-check while FCC is unreachable. */
const UNAVAILABLE_POLL_MS = 5_000

export function useFccCatalog() {
  return useQuery({
    queryKey: ['fcc-catalog'],
    queryFn: getFccCatalog,
    staleTime: 30_000,
    refetchInterval: (query) => {
      // Poll only while FCC is down. `available === true` stops the interval;
      // so does having no data yet (the initial fetch is already in flight).
      const data = query.state.data
      if (!data) {
        return false
      }
      return data.available ? false : UNAVAILABLE_POLL_MS
    },
  })
}
