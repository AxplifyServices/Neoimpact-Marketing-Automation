import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { getApiClient } from '@/lib/api/api-client';

export interface ModeleData {
  id_modele: string;
  nom_modele: string;
  variable_cible: string;
  objectif: string;
  date_creation: string;
  liste_action?: string;
  ui_positions?: Record<string, unknown>;
  locked?: boolean;
}

interface PaginatedResponse {
  items: ModeleData[];
  count: number;
  total: number;
  limit: number;
  pages: number;
  page_start: number;
  next_page_start: number | null;
  stats?: { total: number; locked_total: number; unique_variables: number };
}

export function useModelesData(page: number, pageSize: number) {
  const apiClient = getApiClient();
  const query = useQuery({
    queryKey: ['modeles', 'page', page, pageSize],
    queryFn: () => apiClient.request<PaginatedResponse>(
      modelesApi.findAll({ limit: pageSize, offset: page, pages: 1 })
    ),
    placeholderData: keepPreviousData,
  });

  const response = query.data;
  const modeles = response?.items ?? [];
  const total = response?.total ?? 0;
  const lockedModels = modeles.filter((m) => m.locked === true).map((m) => m.id_modele);
  const lockedTotal = response?.stats?.locked_total ?? modeles.filter((m) => m.locked).length;
  const uniqueVariables = response?.stats?.unique_variables ?? new Set(modeles.map((m) => m.variable_cible)).size;

  return {
    modeles,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
    lockedModels,
    total,
    totalPages: Math.max(Math.ceil(total / pageSize), 1),
    usedCount: lockedTotal,
    unusedCount: Math.max(total - lockedTotal, 0),
    uniqueVariables,
  };
}
