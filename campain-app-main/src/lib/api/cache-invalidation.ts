import type { QueryClient } from '@tanstack/react-query';

/**
 * Invalidate caches whose content depends on campaign lifecycle/state.
 *
 * Only active queries refetch immediately. Inactive queries are marked stale
 * and refresh the next time the user opens the corresponding screen.
 */
export async function invalidateCampaignCaches(queryClient: QueryClient) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['campaigns'] }),
    queryClient.invalidateQueries({ queryKey: ['campaign-meta', 'active-choices'] }),
    queryClient.invalidateQueries({ queryKey: ['dashboard-filters'] }),
    queryClient.invalidateQueries({ queryKey: ['dashboard-compute'] }),
  ]);
}

/**
 * Model/cible names and availability feed the lightweight campaign selectors.
 * Invalidate the whole campaign-meta namespace after those references change.
 */
export async function invalidateCampaignReferenceCaches(queryClient: QueryClient) {
  await queryClient.invalidateQueries({ queryKey: ['campaign-meta'] });
}
