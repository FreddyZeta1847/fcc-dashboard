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
 * FETCH UNTIL WE HAVE IT, THEN STOP. The whole policy is one rule:
 *
 *     if we do not have a catalog yet -> try again on the next tick
 *     once we have one                -> never fetch again
 *
 * The reasoning is that this data is *configuration, not state*. FCC's provider
 * list does not change because FCC stopped — it changes when the user edits
 * FCC's own config. So a catalog we already hold stays valid whether FCC is up
 * or down, and re-fetching it to learn something we already know is exactly the
 * waste `usePricing` argues against.
 *
 * The practical payoff: once the list has loaded, the pricing editor keeps
 * working with FCC stopped. Prices live in *our* config file, not FCC's, so
 * there is no reason adding a pair should require FCC to be running.
 *
 * `staleTime: Infinity` is what stops the refetch-on-focus/mount/reconnect
 * defaults from firing once we hold a catalog; `refetchInterval` is what keeps
 * retrying while we do not. They are the two halves of the same rule.
 *
 * Scope note: the cache is in-memory, so "never again" means for this page
 * session. A reload starts over — which is also how a changed FCC config gets
 * picked up, since nothing else invalidates this query.
 *
 * The query only errors on a transport failure. FCC being stopped is not an
 * error: the backend answers 200 with `available: false`, which simply reads
 * here as "still nothing to show, keep trying".
 */
import { useQuery } from '@tanstack/react-query'
import { getFccCatalog } from '../api/client'
import type { FccCatalogResponse } from '../api/types'

/*
 * Matches useStatus's cadence deliberately. While the catalog is missing this
 * is a second request alongside that poll; keeping them on one rhythm makes
 * the pair predictable instead of interleaving at drifting offsets.
 */
const RETRY_INTERVAL_MS = 10_000

/**
 * A catalog is only useful once FCC reported at least one configured provider.
 * `available: true` with an empty list means FCC answered but has nothing
 * configured (or has not discovered it yet), which is not something to settle
 * on — so that keeps retrying too.
 */
function hasUsableCatalog(data: FccCatalogResponse | undefined): boolean {
  return data?.available === true && data.providers.length > 0
}

export function useFccCatalog() {
  return useQuery({
    queryKey: ['fcc-catalog'],
    queryFn: getFccCatalog,
    // Never goes stale: once held, focus/mount/reconnect must not refetch it.
    staleTime: Infinity,
    gcTime: Infinity,
    refetchInterval: (query) =>
      hasUsableCatalog(query.state.data) ? false : RETRY_INTERVAL_MS,
  })
}
