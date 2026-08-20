import { useEffect } from 'react';
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

interface ChoicesResponse {
  labels: string[];
  mapping: Record<string, string>;
}

const PAGE_SIZE = 9;

const invertChoices = (response?: ChoicesResponse) => {
  const byId = new Map<string, string>();
  if (!response?.mapping) return byId;

  Object.entries(response.mapping).forEach(([label, id]) => {
    if (id) byId.set(String(id), label);
  });

  return byId;
};

export function useCampagnesData() {
  const apiClient = getApiClient();

  const campaignsQuery = useInfiniteQuery({
    queryKey: ['campaigns', 'infinite', PAGE_SIZE],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      apiClient.request<PaginatedResponse<CampaignAPIResponse>>(
        campaignsApi.findAll({ limit: PAGE_SIZE, offset: Number(pageParam), pages: 1 })
      ),
    getNextPageParam: (lastPage) => lastPage.next_page_start ?? undefined,
  });

  const { data: modeleChoices, isLoading: modelesLoading } = useQuery({
    queryKey: ['campaign-meta', 'modele-choices'],
    queryFn: () => apiClient.request<ChoicesResponse>(campaignsApi.modeleChoices()),
    staleTime: 5 * 60_000,
  });

  const { data: cibleChoices, isLoading: ciblesLoading } = useQuery({
    queryKey: ['campaign-meta', 'cible-choices'],
    queryFn: () => apiClient.request<ChoicesResponse>(campaignsApi.cibleChoices()),
    staleTime: 5 * 60_000,
  });

  const apiCampaigns = campaignsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const hasPreparingCampaign = apiCampaigns.some(
    (campaign) => campaign.execution_status === 'preparing' || campaign.execution_status === 'processing'
  );

  // Une campagne volumineuse est créée immédiatement puis préparée côté backend.
  // On ne poll que pendant cette courte phase afin que les compteurs se mettent
  // à jour sans refresh manuel et sans trafic permanent une fois le job terminé.
  useEffect(() => {
    if (!hasPreparingCampaign) return;
    const timer = window.setInterval(() => {
      void campaignsQuery.refetch();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [hasPreparingCampaign, campaignsQuery.refetch]);

  const total = campaignsQuery.data?.pages[0]?.total ?? apiCampaigns.length;
  const modelsMap = invertChoices(modeleChoices);
  const ciblesMap = invertChoices(cibleChoices);

  const campaigns: Campaign[] = apiCampaigns.map((apiCampaign) => {
    const getStatusMapping = (etatCampagne: string) => {
      switch (etatCampagne) {
        case 'En cours':
          return { status: 'En cours', statusColor: 'bg-green-100 text-green-700' };
        case 'En pause':
          return { status: 'En pause', statusColor: 'bg-orange-100 text-orange-700' };
        case 'Planifié':
        case 'Planifiée':
          return { status: 'Planifié', statusColor: 'bg-yellow-100 text-yellow-700' };
        case 'Terminé':
        case 'Terminée':
          return { status: 'Terminé', statusColor: 'bg-blue-100 text-blue-700' };
        case 'Annulée':
        case 'Annulé':
          return { status: 'Annulée', statusColor: 'bg-gray-100 text-gray-500' };
        default:
          return { status: etatCampagne, statusColor: 'bg-gray-100 text-gray-700' };
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
      change: 'Page courante',
      changeColor: 'text-blue-600',
    },
  ];

  return {
    campaigns,
    stats,
    total,
    // Do not block the campaign cards while auxiliary labels are still loading.
    // IDs are rendered as a safe fallback and labels replace them as soon as metadata arrives.
    isLoading: campaignsQuery.isLoading,
    isMetadataLoading: modelesLoading || ciblesLoading,
    isFetchingNextPage: campaignsQuery.isFetchingNextPage,
    hasNextPage: campaignsQuery.hasNextPage,
    fetchNextPage: campaignsQuery.fetchNextPage,
    error: campaignsQuery.error,
    refetch: campaignsQuery.refetch,
  };
}
