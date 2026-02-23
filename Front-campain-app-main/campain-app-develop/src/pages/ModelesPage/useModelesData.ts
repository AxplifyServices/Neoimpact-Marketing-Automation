import { useQuery } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { getApiClient } from '@/lib/api/api-client';

interface PaginatedResponse<T> {
  items: T[];
  count: number;
  total: number;
  limit: number;
  pages: number;
  page_start: number;
  next_page_start: number | null;
}

export interface ModeleData {
  id_modele: string;
  nom_modele: string;
  variable_cible: string;
  objectif: string;
  date_creation: string;
  liste_action?: string;
  graphe_json?: string;
  locked?: boolean;
}

export interface ModeleStats {
  value: string;
  label: string;
  change: string;
  changeColor: string;
}

export function useModelesData() {
  const apiClient = getApiClient();

  const { data: response, isLoading, error, refetch } = useQuery({
    queryKey: ['modeles'],
    queryFn: async () => {
      return await apiClient.request<PaginatedResponse<ModeleData>>(
        modelesApi.findAll()
      );
    },
  });

  // Extract items from paginated response
  const modeles: ModeleData[] = response?.items ?? [];

  // Extract locked models from the data itself
  const lockedModels = modeles
    .filter(m => m.locked === true)
    .map(m => m.id_modele);

  // Calculate used/unused counts
  const usedCount = modeles.filter(m => lockedModels.includes(m.id_modele)).length;
  const unusedCount = modeles.length - usedCount;

  // Calculate stats from modeles
  const stats: ModeleStats[] = [
    {
      value: String(modeles.length),
      label: 'Total modèles',
      change: '+3 ce mois',
      changeColor: 'text-green-600',
    },
    {
      value: String(new Set(modeles.map(m => m.variable_cible)).size),
      label: 'Variables uniques',
      change: 'Variété de cibles',
      changeColor: 'text-purple-600',
    },
  ];

  return {
    modeles,
    stats,
    isLoading,
    error,
    refetch,
    lockedModels,
    usedCount,
    unusedCount,
  };
}
