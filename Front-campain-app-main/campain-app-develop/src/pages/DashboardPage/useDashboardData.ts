import { useQuery } from '@tanstack/react-query';
import { getApiClient } from '@/lib/api/api-client';
import { dashboardApi } from '@/lib/api/definitions/dashboard.api';
import type {
  DashboardFiltersResponse,
  DashboardComputeResponse,
  DashboardComputeRequest
} from '@/types/dashboard.types';

interface UseDashboardDataParams {
  selectedStates?: string[];
  appliedFilters?: DashboardComputeRequest;
}

export function useDashboardData({
  selectedStates = [],
  appliedFilters
}: UseDashboardDataParams = {}) {
  const apiClient = getApiClient();

  // Fetch dynamic filter options based on selected states
  // States filter campaigns, not the other way around
  const { data: filterOptions, isLoading: filtersLoading } = useQuery<DashboardFiltersResponse>({
    queryKey: ['dashboard-filters', selectedStates],
    queryFn: () => apiClient.request<DashboardFiltersResponse>(
      dashboardApi.filters({
        etats_campagne: selectedStates.length > 0 ? selectedStates : undefined,
      })
    ),
    staleTime: 0, // No caching - always fetch fresh data for dynamic filtering
  });

  // Compute dashboard data (triggered when filters are applied)
  const {
    data: dashboardData,
    isLoading: dataLoading,
    error,
    refetch
  } = useQuery<DashboardComputeResponse>({
    queryKey: ['dashboard-compute', appliedFilters],
    queryFn: () => apiClient.request<DashboardComputeResponse>(
      dashboardApi.compute(appliedFilters || {
        campagne_ids: [],
        etats_campagne: [],
        date_min: null,
        date_max: null,
      })
    ),
    enabled: !!appliedFilters, // Only run when filters are applied
  });

  return {
    filterOptions,
    filtersLoading,
    dashboardData,
    dataLoading,
    error,
    refetch,
  };
}
