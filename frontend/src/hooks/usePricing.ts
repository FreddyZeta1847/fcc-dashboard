/*
 * usePricing.ts
 * TanStack Query hook for GET /pricing — the current pricing config
 * document (Anthropic tiers + provider overrides).
 *
 * Deliberately deviates from Phase 5's uniform-polling hooks (useStatus,
 * useStats): no `refetchInterval` here. Every other hook in this codebase
 * polls every 10s because its underlying data changes from outside events
 * (FCC processing requests, provider health flapping). Pricing data has no
 * such outside source — it only changes when a user explicitly edits it
 * (usePutPricing) or explicitly triggers a refresh (usePricingRefresh) on
 * this same page, both of which invalidate the `['pricing']` query
 * themselves (see usePricingMutations.ts). Polling a document that can only
 * change via an action this hook's own consumer just took would be pure
 * waste — an unconditional network call for a "did it change?" question
 * this session already knows the answer to.
 */
import { useQuery } from '@tanstack/react-query'
import { getPricing } from '../api/client'

export function usePricing() {
  return useQuery({
    queryKey: ['pricing'],
    queryFn: getPricing,
    staleTime: 10_000,
  })
}
