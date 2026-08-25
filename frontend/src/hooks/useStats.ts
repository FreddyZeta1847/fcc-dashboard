/*
 * useStats.ts
 * TanStack Query hook for GET /stats — aggregate counts, token totals, and
 * savings for a named time range. `range` is a caller-supplied parameter
 * (not defaulted here) so it stays part of the query key: switching range
 * in the UI (Task 4) is then just a re-render with a new `range` argument,
 * and TanStack Query treats it as a distinct cached query rather than
 * something this hook has to invalidate manually.
 */
import { useQuery } from '@tanstack/react-query'
import { getStats } from '../api/client'
import type { RangeName } from '../api/types'

export function useStats(range: RangeName) {
  return useQuery({
    queryKey: ['stats', range],
    queryFn: () => getStats(range),
    staleTime: 10_000,
    refetchInterval: 10_000,
  })
}
