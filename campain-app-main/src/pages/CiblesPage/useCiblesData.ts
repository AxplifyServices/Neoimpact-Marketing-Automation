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
  pct_engagement_digital_eleve?: number | null;
  locked?: boolean;
  lock_reason?: string | null;
}

export interface CibleListFilters {
  search?: string;
  source?: string;
  status?: 'locked' | 'available' | '';
  dateMin?: string;
  dateMax?: string;
  objectifMode?: 'atteint' | 'non_atteint' | 'none' | '';
  objectifCampaign?: string;
  sortBy?: string;
  sortDir?: 'asc' | 'desc';
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

export function useCiblesData(page: number, pageSize: number, filters: CibleListFilters = {}) {
  const apiClient = getApiClient();
  const query = useQuery({
    queryKey: ['cibles', 'page', page, pageSize, filters],
    queryFn: () => apiClient.request<PaginatedResponse>(
      ciblesApi.findAll({
        limit: pageSize,
        offset: page,
        pages: 1,
        q: filters.search?.trim() || undefined,
        source: filters.source || undefined,
        locked: filters.status ? filters.status === 'locked' : undefined,
        date_min: filters.dateMin || undefined,
        date_max: filters.dateMax || undefined,
        objectif_mode: filters.objectifMode || undefined,
        objectif_campaign: filters.objectifCampaign || undefined,
        sort_by: filters.sortBy || undefined,
        sort_dir: filters.sortDir || undefined,
      })
    ),
    placeholderData: keepPreviousData,
  });

  const response = query.data;
  const cibles = response?.items ?? [];
  const filteredTotal = response?.total ?? 0;
  const total = response?.stats?.total ?? filteredTotal;
  const lockedCibles = cibles.filter((c) => c.locked === true).map((c) => c.id_cible);

  return {
    cibles,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
    lockedCibles,
    total,
    totalPages: Math.max(Math.ceil(filteredTotal / pageSize), 1),
    usedCount: response?.stats?.locked_total ?? cibles.filter((c) => c.locked).length,
    dbCount: response?.stats?.db_total ?? cibles.filter((c) => c.source?.toLowerCase() === 'db').length,
    fileCount: response?.stats?.file_total ?? cibles.filter((c) => c.source?.toLowerCase() === 'file').length,
  };
}
