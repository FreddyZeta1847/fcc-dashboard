/*
 * useControl.ts
 * TanStack Query mutation hooks for FCC process control: `useControlStart`
 * (POST /control/start) and `useControlStop` (POST /control/stop).
 *
 * Neither invalidates `/status` — its own 10s poll (useStatus.ts, Phase 5)
 * picks up the new FCC state within that window regardless.
 *
 * Both DO invalidate `['fcc-catalog']`, because that query has no such poll
 * while FCC is up, and starting or stopping FCC is exactly what changes it.
 * Concretely: with FCC down, the pricing editor falls back to manual entry;
 * starting FCC from this dashboard has to bring the provider/model pickers
 * back without a page reload.
 *
 * Invalidation alone is not sufficient for start — /control/start returns as
 * soon as the process is launched, well before FCC is listening (~15s), so the
 * refetch it triggers will usually still see FCC down. useFccCatalog's own
 * while-unavailable poll is what actually closes that gap; invalidating here
 * just makes the common case feel immediate and covers stop, where the state
 * change is instant.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { postControlStart, postControlStop } from '../api/client'

export function useControlStart() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: postControlStart,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fcc-catalog'] })
    },
  })
}

export function useControlStop() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: postControlStop,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fcc-catalog'] })
    },
  })
}
