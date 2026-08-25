/*
 * useStatus.ts
 * TanStack Query hook for GET /status — FCC reachability and per-provider
 * health. `isError` here means the dashboard's own backend is unreachable,
 * never "FCC is down" (see BACKEND--api / routes_status.py: /status is
 * designed to never fail while the backend itself is running — that fact
 * degrades gracefully into a successful `fcc_status: "down"` response
 * instead of a thrown error). Consumed by StatusPanel and by App's
 * backend-unreachable gate (Task 3).
 */
import { useQuery } from '@tanstack/react-query'
import { getStatus } from '../api/client'

export function useStatus() {
  return useQuery({
    queryKey: ['status'],
    queryFn: getStatus,
    staleTime: 10_000,
    refetchInterval: 10_000,
  })
}
