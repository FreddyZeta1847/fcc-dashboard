/*
 * useDbTables.ts
 * TanStack Query hooks for the raw db browser: `useDbTables` (GET
 * /db/tables — the list of real table names) and `useDbTableRows` (GET
 * /db/tables/{name} — a paginated row dump of one table). `useDbTableRows`
 * is `enabled: name !== ''` because it needs a table selected first (Task
 * 3's table picker) — with no name there is nothing to fetch, and calling
 * the endpoint with an empty name would just 404 against the backend's
 * exact-match table validation.
 */
import { useQuery } from '@tanstack/react-query'
import { getDbTables, getDbTableRows } from '../api/client'

export function useDbTables() {
  return useQuery({
    queryKey: ['dbTables'],
    queryFn: getDbTables,
  })
}

export function useDbTableRows(name: string, limit: number, offset: number) {
  return useQuery({
    queryKey: ['dbTableRows', name, limit, offset],
    queryFn: () => getDbTableRows(name, limit, offset),
    enabled: name !== '',
  })
}
