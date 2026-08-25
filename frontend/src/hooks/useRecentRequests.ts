/*
 * useRecentRequests.ts
 * TanStack Query hook for GET /requests — the most recent request rows,
 * capped at `limit`. `limit` is a caller-supplied parameter, kept in the
 * query key for the same reason as useStats's `range`: a different limit
 * (e.g. a paginated or "load more" view in a later task) is a distinct
 * cached query, not a value this hook has to manage internally.
 */
import { useQuery } from '@tanstack/react-query'
import { getRecentRequests } from '../api/client'

export function useRecentRequests(limit: number) {
  return useQuery({
    queryKey: ['recentRequests', limit],
    queryFn: () => getRecentRequests(limit),
    staleTime: 10_000,
    refetchInterval: 10_000,
  })
}
