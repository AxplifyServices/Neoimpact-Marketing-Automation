import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getApiClient } from '@/lib/api/api-client';
import { campaignsApi } from '@/lib/api/definitions/campaigns.api';
import type { TypeCampagne } from '@/types/campaign.types';
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

  interface CampaignChoice {
    id_campagne: string;
    nom_campagne: string;
    etat_campagne: string;
    type_campagne?: TypeCampagne | null;
  }

  interface CampaignChoicesResponse {
    items: CampaignChoice[];
    count: number;
  }

  const { data: campaigns = [], isLoading } = useQuery<
    CampaignChoicesResponse,
    unknown,
    CampaignChoice[]
  >({
    queryKey: ['campaign-meta', 'active-choices'],
    queryFn: () => apiClient.request<CampaignChoicesResponse>(campaignsApi.activeChoices()),
    select: (data) => data?.items ?? [],
    staleTime: 60_000,
  });

  const activeCampaigns = useMemo(
    () =>
      campaigns.filter(
        (c) => !typeCampagne || (c.type_campagne ?? 'sans_action_terrain') === typeCampagne
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
