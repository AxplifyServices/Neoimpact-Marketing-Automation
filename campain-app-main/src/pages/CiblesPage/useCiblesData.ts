import { keepPreviousData, useQuery } from '@tanstack/react-query';
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

interface PaginatedResponse {
  items: CibleData[];
  count: number;
  total: number;
  limit: number;
  pages: number;
  page_start: number;
  next_page_start: number | null;
  stats?: { total: number; locked_total: number; db_total: number; file_total: number };
}

export function useCiblesData(page: number, pageSize: number) {
  const apiClient = getApiClient();
  const query = useQuery({
    queryKey: ['cibles', 'page', page, pageSize],
    queryFn: () => apiClient.request<PaginatedResponse>(
      ciblesApi.findAll({ limit: pageSize, offset: page, pages: 1 })
    ),
    placeholderData: keepPreviousData,
  });

  const response = query.data;
  const cibles = response?.items ?? [];
  const total = response?.total ?? 0;
  const lockedCibles = cibles.filter((c) => c.locked === true).map((c) => c.id_cible);

  return {
    cibles,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
    lockedCibles,
    total,
    totalPages: Math.max(Math.ceil(total / pageSize), 1),
    usedCount: response?.stats?.locked_total ?? cibles.filter((c) => c.locked).length,
    dbCount: response?.stats?.db_total ?? cibles.filter((c) => c.source?.toLowerCase() === 'db').length,
    fileCount: response?.stats?.file_total ?? cibles.filter((c) => c.source?.toLowerCase() === 'file').length,
  };
}
