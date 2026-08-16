import { useQuery } from '@tanstack/react-query';
import { ciblesApi } from '@/lib/api/definitions/cibles.api';
import { getApiClient } from '@/lib/api/api-client';
import type { Cible, CibleAPIResponse } from '@/types/campaign.types';

// Helper function to map API response to UI format
function mapCibleFromAPI(apiCible: CibleAPIResponse): Cible {
  const cibleId = apiCible.id_cible ?? apiCible.id ?? '';
  return {
    id: cibleId,
    code: `CI${String(cibleId).padStart(6, '0')}`,
    name: apiCible.nom_cible,
    type: apiCible.source,
    timestamp: apiCible.created_at || new Date().toISOString(),
  };
}

export function useCreationData() {
  const apiClient = getApiClient();

  // Fetch cibles from real API
  const { data: apiCibles = [], isLoading, error, refetch } = useQuery({
    queryKey: ['cibles'],
    queryFn: async () => {
      const response = await apiClient.request<CibleAPIResponse[]>(
        ciblesApi.findAll()
      );
      return response;
    },
  });

  // Map API data to UI format
  const cibles = apiCibles.map(mapCibleFromAPI);

  return {
    cibles,
    isLoading,
    error,
    refetch,
  };
}
