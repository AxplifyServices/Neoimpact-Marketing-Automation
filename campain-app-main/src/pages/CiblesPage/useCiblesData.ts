import { useQuery } from '@tanstack/react-query';
import { ciblesApi } from '@/lib/api/definitions/cibles.api';
import { getApiClient } from '@/lib/api/api-client';

export interface CibleData {
  id_cible: string;
  nom_cible: string;
  source: string;
  date_creation: string;
  filtre?: Record<string, any> | string;
  chemin?: string;
  nb_leads?: number;
  locked?: boolean;
  lock_reason?: string | null;
}

export interface CibleStats {
  value: string;
  label: string;
  change: string;
  changeColor: string;
}

export function useCiblesData() {
  const apiClient = getApiClient();

  const { data: cibles = [], isLoading, error, refetch } = useQuery({
    queryKey: ['cibles'],
    queryFn: async () => {
      return await apiClient.request<CibleData[]>(
        ciblesApi.findAll()
      );
    },
  });

  // Extract locked cibles from the data itself
  const lockedCibles = cibles
    .filter(c => c.locked === true)
    .map(c => c.id_cible);

  // Calculate stats from cibles
  const stats: CibleStats[] = [
    {
      value: String(cibles.length),
      label: 'Total cibles',
      change: '+2 ce mois',
      changeColor: 'text-green-600',
    },
    {
      value: String(cibles.filter(c => c.source?.toLowerCase() === 'db').length),
      label: 'Cibles DB',
      change: 'Basées sur filtres',
      changeColor: 'text-blue-600',
    },
    {
      value: String(cibles.filter(c => c.source?.toLowerCase() === 'file').length),
      label: 'Cibles fichier',
      change: 'Importées',
      changeColor: 'text-purple-600',
    },
  ];

  return {
    cibles,
    stats,
    isLoading,
    error,
    refetch,
    lockedCibles,
  };
}
