/*
 * usePricingMutations.ts
 * TanStack Query mutation hooks for writing pricing state: `usePutPricing`
 * (PUT /pricing — overwrite the full config document) and
 * `usePricingRefresh` (POST /pricing/refresh — fetch a best-effort diff
 * against LiteLLM/OpenRouter without writing anything). Only `usePutPricing`
 * invalidates the `['pricing']` query cache on success — it actually
 * changed the stored document, so the cache used by usePricing.ts would
 * otherwise keep serving pre-write data for up to that hook's 10s
 * `staleTime`. `usePricingRefresh` doesn't touch the pricing document at
 * all (its response is a diff for the caller to review/act on), so there
 * is nothing to invalidate.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { postPricingRefresh, putPricing } from '../api/client'

export function usePutPricing() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: putPricing,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pricing'] })
    },
  })
}

export function usePricingRefresh() {
  return useMutation({
    mutationFn: postPricingRefresh,
  })
}
