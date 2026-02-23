import { useQuery, useQueries } from '@tanstack/react-query';
import { campaignsApi } from '@/lib/api/definitions/campaigns.api';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { ciblesApi } from '@/lib/api/definitions/cibles.api';
import { getApiClient } from '@/lib/api/api-client';
import type { Campaign, CampaignAPIResponse, Stat, CibleAPIResponse, ModeleAPIResponse } from '@/types/campaign.types';

interface PaginatedResponse<T> {
  items: T[];
  count: number;
  total: number;
  limit: number;
  pages: number;
  page_start: number;
  next_page_start: number | null;
}

export function useCampagnesData() {
  const apiClient = getApiClient();

  // Fetch campaigns from real API
  const { data: response, isLoading: campaignsLoading, error, refetch } = useQuery({
    queryKey: ['campaigns'],
    queryFn: async () => {
      return await apiClient.request<PaginatedResponse<CampaignAPIResponse>>(
        campaignsApi.findAll()
      );
    },
  });

  const apiCampaigns: CampaignAPIResponse[] = response?.items ?? [];

  // Fetch related models and cibles for each campaign
  const relatedDataQueries = useQueries({
    queries: apiCampaigns.flatMap((campaign) => [
      // Fetch model
      {
        queryKey: ['modele', campaign.id_modele],
        queryFn: async () => {
          try {
            const response = await apiClient.request<ModeleAPIResponse>(
              modelesApi.findById(campaign.id_modele)
            );
            return { campaignId: campaign.id_campagne, type: 'model', data: response };
          } catch (error) {
            console.error(`Failed to fetch model ${campaign.id_modele}:`, error);
            return { campaignId: campaign.id_campagne, type: 'model', data: null };
          }
        },
        enabled: !!campaign.id_modele,
      },
      // Fetch cible
      {
        queryKey: ['cible', campaign.id_cible],
        queryFn: async () => {
          try {
            const response = await apiClient.request<CibleAPIResponse>(
              ciblesApi.findById(campaign.id_cible)
            );
            return { campaignId: campaign.id_campagne, type: 'cible', data: response };
          } catch (error) {
            console.error(`Failed to fetch cible ${campaign.id_cible}:`, error);
            return { campaignId: campaign.id_campagne, type: 'cible', data: null };
          }
        },
        enabled: !!campaign.id_cible,
      },
    ]),
  });

  // Check if related data is still loading
  const relatedDataLoading = relatedDataQueries.some((query) => query.isLoading);
  const isLoading = campaignsLoading || relatedDataLoading;

  // Build lookup maps for models and cibles
  const modelsMap = new Map<string, string>();
  const ciblesMap = new Map<string, string>();

  relatedDataQueries.forEach((query) => {
    if (query.data) {
      const result = query.data as any;
      if (result.type === 'model' && result.data) {
        const modelId = result.data.id_modele;
        const modelName = result.data.nom_modele || `Modèle ${modelId}`;
        modelsMap.set(modelId, modelName);
      } else if (result.type === 'cible' && result.data) {
        const cibleId = result.data.id_cible || result.data.id;
        const cibleName = result.data.nom_cible || `Cible ${cibleId}`;
        if (cibleId) {
          ciblesMap.set(cibleId, cibleName);
        }
      }
    }
  });

  // Map API data to UI format with resolved names
  const campaigns: Campaign[] = apiCampaigns.map((apiCampaign) => {
    // Map API status to UI status with proper handling for all states
    const getStatusMapping = (etatCampagne: string) => {
      switch (etatCampagne) {
        case 'En cours':
          return {
            status: 'En cours',
            statusColor: 'bg-green-100 text-green-700'
          };
        case 'En pause':
          return {
            status: 'En pause',
            statusColor: 'bg-orange-100 text-orange-700'
          };
        case 'Planifié':
        case 'Planifiée':
          return {
            status: 'Planifié',
            statusColor: 'bg-yellow-100 text-yellow-700'
          };
        case 'Terminé':
        case 'Terminée':
          return {
            status: 'Terminé',
            statusColor: 'bg-blue-100 text-blue-700'
          };
        case 'Annulée':
        case 'Annulé':
          return {
            status: 'Annulée',
            statusColor: 'bg-gray-100 text-gray-500'
          };
        default:
          // Generic status for unknown states
          return {
            status: etatCampagne,
            statusColor: 'bg-gray-100 text-gray-700'
          };
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
      metrics: {
        attribues: apiCampaign.nb_attribues || 0,
        conversions: apiCampaign.nb_conversions || 0,
        contactes: apiCampaign.nb_contactes || 0,
        enTraitement: apiCampaign.nb_en_traitement || 0,
        arrivEche: apiCampaign.nb_arriv_eche || 0,
      },
    };
  });

  // Calculate stats from campaigns
  const stats: Stat[] = [
    {
      value: String(campaigns.filter(c => c.status === 'En cours').length),
      label: 'Campagnes actives',
      change: '+12%',
      changeColor: 'text-green-600',
    },
    {
      value: String(campaigns.length),
      label: 'Total campagnes',
      change: '+8%',
      changeColor: 'text-green-600',
    },
    {
      value: String(campaigns.filter(c => c.status === 'Planifié').length),
      label: 'Campagnes planifiées',
      change: '+5%',
      changeColor: 'text-blue-600',
    },
  ];

  return {
    campaigns,
    stats,
    isLoading,
    error,
    refetch,
  };
}
