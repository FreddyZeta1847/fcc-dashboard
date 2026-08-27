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
 * Like usePricing, no `refetchInterval`: this reflects FCC's configuration,
 * which only changes when the user edits it in FCC's own admin UI — not from
 * request traffic. `staleTime` is short rather than zero so that opening the
 * Settings page after changing something in FCC picks it up promptly without
 * refetching on every re-render.
 *
 * The query only errors on a transport failure. FCC being *stopped* is not an
 * error: the backend answers 200 with `available: false`, and the editor falls
 * back to manual entry.
 */
import { useQuery } from '@tanstack/react-query'
import { getFccCatalog } from '../api/client'

export function useFccCatalog() {
  return useQuery({
    queryKey: ['fcc-catalog'],
    queryFn: getFccCatalog,
    staleTime: 30_000,
  })
}
