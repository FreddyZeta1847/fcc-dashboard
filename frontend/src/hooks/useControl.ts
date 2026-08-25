/*
 * useControl.ts
 * TanStack Query mutation hooks for FCC process control: `useControlStart`
 * (POST /control/start) and `useControlStop` (POST /control/stop). Neither
 * invalidates any query on success — Task 6 decides what, if anything, to
 * refetch after a control action; `/status`'s own 10s poll (useStatus.ts,
 * Phase 5) will pick up the new FCC state on its own within that window
 * regardless.
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
