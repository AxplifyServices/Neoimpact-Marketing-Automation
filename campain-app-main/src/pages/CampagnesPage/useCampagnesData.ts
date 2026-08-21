import { useEffect, useMemo, useRef } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { campaignsApi } from '@/lib/api/definitions/campaigns.api';
import { getApiClient } from '@/lib/api/api-client';
import type { Campaign, CampaignAPIResponse, Stat } from '@/types/campaign.types';

interface PaginatedResponse<T> {
  items: T[];
  count: number;
  total: number;
  limit: number;
  pages: number;
  page_start: number;
  next_page_start: number | null;
}

interface CampaignCreateOptionsResponse {
  modeles: Array<{ id_modele: string; nom_modele: string }>;
  cibles: Array<{ id_cible: string; nom_cible: string }>;
}

interface ProcessingStatusItem {
  id_campagne: string;
  execution_status?: CampaignAPIResponse['execution_status'];
  population_count?: number | null;
  target_count_initial?: number | null;
  target_count_eligible?: number | null;
  preparation_finished_at?: string | null;
  execution_error?: string | null;
}

interface ProcessingStatusesResponse {
  items: ProcessingStatusItem[];
}

export interface CampaignListFilters {
  search?: string;
  statuses?: string[];
  dateMin?: string;
  dateMax?: string;
}

const PAGE_SIZE = 9;

const statusToBackend = (status: string) => {
  if (status === 'Planifié') return 'Planifiée';
  if (status === 'Terminé') return 'Terminée';
  return status;
};

export function useCampagnesData(filters: CampaignListFilters = {}) {
  const apiClient = getApiClient();
  const backendStatuses = useMemo(
    () => (filters.statuses ?? []).map(statusToBackend),
    [filters.statuses]
  );

  const campaignsQuery = useInfiniteQuery({
    queryKey: [
      'campaigns',
      'infinite',
      PAGE_SIZE,
      filters.search ?? '',
      backendStatuses.join('|'),
      filters.dateMin ?? '',
      filters.dateMax ?? '',
    ],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      apiClient.request<PaginatedResponse<CampaignAPIResponse>>(
        campaignsApi.findAll({
          limit: PAGE_SIZE,
          offset: Number(pageParam),
          pages: 1,
          q: filters.search?.trim() || undefined,
          etats: backendStatuses.length ? backendStatuses.join(',') : undefined,
          date_min: filters.dateMin || undefined,
          date_max: filters.dateMax || undefined,
        })
      ),
    getNextPageParam: (lastPage) => lastPage.next_page_start ?? undefined,
    placeholderData: (previousData) => previousData,
  });

  // One shared request powers both card labels and the create-campaign modal.
  // Hovering the "Nouvelle campagne" button prefetches this same cache entry.
  const { data: createOptions, isLoading: metadataLoading } = useQuery({
    queryKey: ['campaign-meta', 'create-options'],
    queryFn: () => apiClient.request<CampaignCreateOptionsResponse>(campaignsApi.createOptions()),
    staleTime: 5 * 60_000,
  });

  const baseCampaigns = campaignsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const preparingIds = useMemo(
    () => baseCampaigns
      .filter((campaign) => campaign.execution_status === 'preparing' || campaign.execution_status === 'processing')
      .map((campaign) => campaign.id_campagne)
      .sort(),
    [baseCampaigns]
  );

  const processingQuery = useQuery({
    queryKey: ['campaigns', 'processing-statuses', preparingIds],
    queryFn: () => apiClient.request<ProcessingStatusesResponse>(campaignsApi.processingStatuses(preparingIds)),
    enabled: preparingIds.length > 0,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      if (!items.length) return 2500;
      return items.some((item) => item.execution_status === 'preparing' || item.execution_status === 'processing')
        ? 2500
        : false;
    },
    staleTime: 0,
  });

  const processingById = useMemo(
    () => new Map((processingQuery.data?.items ?? []).map((item) => [item.id_campagne, item])),
    [processingQuery.data]
  );

  const effectiveApiCampaigns = useMemo(
    () => baseCampaigns.map((campaign) => {
      const live = processingById.get(campaign.id_campagne);
      if (!live) return campaign;
      return {
        ...campaign,
        execution_status: live.execution_status ?? campaign.execution_status,
        nb_attribues:
          (live.population_count && live.population_count > 0 ? live.population_count : null)
          ?? (live.target_count_eligible && live.target_count_eligible > 0 ? live.target_count_eligible : null)
          ?? (live.target_count_initial && live.target_count_initial > 0 ? live.target_count_initial : null)
          ?? campaign.nb_attribues,
      };
    }),
    [baseCampaigns, processingById]
  );

  // When the tiny status poll tells us all jobs finished, refresh the visible
  // pages once to obtain final KPI values. No repeated full-list polling.
  const completionRefreshDone = useRef(false);
  const stillPreparing = effectiveApiCampaigns.some(
    (campaign) => campaign.execution_status === 'preparing' || campaign.execution_status === 'processing'
  );
  useEffect(() => {
    if (preparingIds.length === 0) {
      completionRefreshDone.current = false;
      return;
    }
    if (!stillPreparing && processingQuery.data && !completionRefreshDone.current) {
      completionRefreshDone.current = true;
      void campaignsQuery.refetch();
    }
  }, [preparingIds.length, stillPreparing, processingQuery.data, campaignsQuery.refetch]);

  const total = campaignsQuery.data?.pages[0]?.total ?? effectiveApiCampaigns.length;
  const modelsMap = new Map((createOptions?.modeles ?? []).map((item) => [item.id_modele, item.nom_modele || item.id_modele]));
  const ciblesMap = new Map((createOptions?.cibles ?? []).map((item) => [item.id_cible, item.nom_cible || item.id_cible]));

  const campaigns: Campaign[] = effectiveApiCampaigns.map((apiCampaign) => {
    const getStatusMapping = (etatCampagne: string) => {
      switch (etatCampagne) {
        case 'En cours': return { status: 'En cours', statusColor: 'bg-green-100 text-green-700' };
        case 'En pause': return { status: 'En pause', statusColor: 'bg-orange-100 text-orange-700' };
        case 'Planifié':
        case 'Planifiée': return { status: 'Planifié', statusColor: 'bg-yellow-100 text-yellow-700' };
        case 'Terminé':
        case 'Terminée': return { status: 'Terminé', statusColor: 'bg-blue-100 text-blue-700' };
        case 'Annulée':
        case 'Annulé': return { status: 'Annulée', statusColor: 'bg-gray-100 text-gray-500' };
        default: return { status: etatCampagne, statusColor: 'bg-gray-100 text-gray-700' };
      }
    };

    const { status, statusColor } = getStatusMapping(apiCampaign.etat_campagne);
    return {
      id: apiCampaign.id_campagne,
      code: apiCampaign.id_campagne,
      title: apiCampaign.nom_campagne,
      description: apiCampaign.description || '',
      image: '',
      status,
      statusColor,
      startDate: apiCampaign.date_debut,
      endDate: apiCampaign.date_fin,
      target: ciblesMap.get(apiCampaign.id_cible) || apiCampaign.id_cible,
      model: modelsMap.get(apiCampaign.id_modele) || apiCampaign.id_modele,
      id_modele: apiCampaign.id_modele,
      id_cible: apiCampaign.id_cible,
      type_campagne: apiCampaign.type_campagne,
      visitMode: apiCampaign.visitMode,
      visitPurpose: apiCampaign.visitPurpose,
      execution_status: apiCampaign.execution_status,
      isPreparing: apiCampaign.execution_status === 'preparing' || apiCampaign.execution_status === 'processing',
      preparationCount: apiCampaign.nb_attribues > 0 ? apiCampaign.nb_attribues : null,
      metrics: {
        attribues: apiCampaign.nb_attribues || 0,
        conversions: apiCampaign.nb_conversions || 0,
        contactes: apiCampaign.nb_contactes || 0,
        enTraitement: apiCampaign.nb_en_traitement || 0,
        arrivEche: apiCampaign.nb_arriv_eche || 0,
      },
    };
  });

  const stats: Stat[] = [
    {
      value: String(campaigns.filter((c) => c.status === 'En cours').length),
      label: 'Actives chargées',
      change: `${campaigns.length} chargées`,
      changeColor: 'text-green-600',
    },
    {
      value: String(total),
      label: 'Total campagnes',
      change: `${campaigns.length} affichables`,
      changeColor: 'text-green-600',
    },
    {
      value: String(campaigns.filter((c) => c.status === 'Planifié').length),
      label: 'Planifiées chargées',
      change: 'Résultat courant',
      changeColor: 'text-blue-600',
    },
  ];

  return {
    campaigns,
    stats,
    total,
    isLoading: campaignsQuery.isLoading,
    isMetadataLoading: metadataLoading,
    isFetchingNextPage: campaignsQuery.isFetchingNextPage,
    hasNextPage: campaignsQuery.hasNextPage,
    fetchNextPage: campaignsQuery.fetchNextPage,
    error: campaignsQuery.error,
    refetch: campaignsQuery.refetch,
  };
}
