import type { ApiRequest } from '../ApiRequest';
import type { DashboardComputeRequest } from '@/types/dashboard.types';

export const dashboardApi = {
  // Get filter options with dynamic filtering
  filters: (params?: { campagne_ids?: string[], etats_campagne?: string[] }): ApiRequest => ({
    url: '/dashboard/filters',
    method: 'GET',
    params: params,
  }),

  // Compute dashboard (POST method - preferred)
  compute: (filters: DashboardComputeRequest): ApiRequest => ({
    url: '/dashboard/compute',
    method: 'POST',
    body: filters,
  }),

  // Compute dashboard with per-campaign breakdown and graph data
  computeByCampaign: (filters: { campagne_ids: string[]; etats_campagne?: string[]; date_min?: string | null; date_max?: string | null }): ApiRequest => ({
    url: '/dashboard/compute-by-campagne',
    method: 'POST',
    body: filters,
  }),

  // Legacy endpoint for backward compatibility
  getCampaignOptions: (): ApiRequest => ({
    url: '/dashboard/campagnes-options',
    method: 'GET',
  }),
};
