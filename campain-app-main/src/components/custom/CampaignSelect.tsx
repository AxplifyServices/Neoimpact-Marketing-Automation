import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getApiClient } from '@/lib/api/api-client';
import { campaignsApi } from '@/lib/api/definitions/campaigns.api';
import type { CampaignAPIResponse, TypeCampagne } from '@/types/campaign.types';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface CampaignSelectProps {
  value: string | null;
  onValueChange: (value: string | null) => void;
  placeholder?: string;
  className?: string;
  allowAll?: boolean;
  typeCampagne?: TypeCampagne;
}

export default function CampaignSelect({
  value,
  onValueChange,
  placeholder = 'Toutes les campagnes',
  className,
  allowAll = true,
  typeCampagne,
}: CampaignSelectProps) {
  const apiClient = getApiClient();

  interface PaginatedResponse<T> {
    items: T[];
    count: number;
    total: number;
    limit: number;
    pages: number;
    page_start: number;
    next_page_start: number | null;
  }

  // Shares cache with useCampagnesData (same key) so this select reuses the fetched list
  const { data: campaigns = [], isLoading } = useQuery<
    PaginatedResponse<CampaignAPIResponse>,
    unknown,
    CampaignAPIResponse[]
  >({
    queryKey: ['campaigns'],
    queryFn: () => apiClient.request<PaginatedResponse<CampaignAPIResponse>>(campaignsApi.findAll()),
    select: (data) => data?.items ?? [],
    staleTime: 60_000,
  });

  const activeCampaigns = useMemo(
    () =>
      campaigns.filter(
        (c) =>
          c.etat_campagne === 'En cours' &&
          (!typeCampagne || (c.type_campagne ?? 'sans_action_terrain') === typeCampagne)
      ),
    [campaigns, typeCampagne]
  );

  return (
    <Select
      value={value || 'all'}
      onValueChange={(val) => onValueChange(val === 'all' ? null : val)}
      disabled={isLoading}
    >
      <SelectTrigger className={className}>
        <SelectValue placeholder={isLoading ? 'Chargement...' : placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowAll && (
          <SelectItem value="all">Toutes les campagnes</SelectItem>
        )}
        {activeCampaigns.length === 0 && !isLoading && (
          <SelectItem value="none" disabled>
            Aucune campagne active
          </SelectItem>
        )}
        {activeCampaigns.map((campaign) => (
          <SelectItem key={campaign.id_campagne} value={campaign.id_campagne}>
            {campaign.nom_campagne}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
