/*
 * useControl.ts
 * TanStack Query mutation hooks for FCC process control: `useControlStart`
 * (POST /control/start) and `useControlStop` (POST /control/stop).
 *
 * Neither invalidates `/status` here — its own 10s poll (useStatus.ts, Phase 5)
 * picks up the new FCC state within that window, and `Sidebar` additionally
 * invalidates `['status']` at the call site so the Run/Stop button flips
 * immediately rather than after the next tick.
 *
 * Neither invalidates `['fcc-catalog']` either, and that is deliberate rather
 * than an omission. The catalog is FCC's *configuration*, not its running
 * state: it does not change because FCC started or stopped, only because the
 * user edited FCC's own config. `useFccCatalog` therefore fetches until it has
 * a catalog and then stops for good — invalidating here would force exactly
 * the refetch that policy exists to avoid, to re-learn something already known.
 *
 * A genuine FCC config change is picked up on the next page load, since nothing
 * else invalidates that query.
 */
import { useMutation } from '@tanstack/react-query'
import { postControlStart, postControlStop } from '../api/client'

export function useControlStart() {
  return useMutation({
    mutationFn: postControlStart,
  })
}

export function useControlStop() {
  return useMutation({
    mutationFn: postControlStop,
  })
}
