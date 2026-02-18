import { useState, useEffect } from 'react';
import { Filter, RefreshCw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { MultiSelect } from '@/components/ui/multi-select';
import { useApiQuery } from '@/lib/api/hooks/use-api-query';
import { queuesApi } from '@/lib/api/definitions/queues.api';
import type { DashboardFiltersResponse, DashboardComputeRequest } from '@/types/dashboard.types';

const STATE_OPTIONS = [
  { value: 'En cours', label: 'En cours' },
  { value: 'Terminée', label: 'Terminée' },
];

interface DashboardFiltersProps {
  filterOptions?: DashboardFiltersResponse;
  onApplyFilters: (filters: DashboardComputeRequest) => void;
  onSelectionChange: (campaigns: string[], states: string[]) => void;
  isLoading?: boolean;
}

export default function DashboardFilters({
  filterOptions,
  onApplyFilters,
  onSelectionChange,
  isLoading = false
}: DashboardFiltersProps) {
  const [selectedCampaigns, setSelectedCampaigns] = useState<string[]>([]);
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [selectedGestionnaires, setSelectedGestionnaires] = useState<string[]>([]);
  const [initialized, setInitialized] = useState(false);

  // Fetch gestionnaires list
  const { data: gestionnairesData } = useApiQuery<{ gestionnaires: string[] }>(
    ['gestionnaires'],
    queuesApi.getGestionnaires()
  );

  // Initialize selected states from API (options remain hardcoded)
  useEffect(() => {
    if (initialized || !filterOptions) {
      return;
    }

    const allowedStates = new Set(STATE_OPTIONS.map(option => option.value));
    const apiStates = filterOptions.etats
      .map(option => option.value)
      .filter(value => allowedStates.has(value));
    const nextStates = apiStates.length > 0
      ? apiStates
      : STATE_OPTIONS.map(option => option.value);

    setSelectedStates(nextStates);
    setInitialized(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterOptions, initialized]);

  // Separate effect to notify parent after initialization AND auto-apply filters
  useEffect(() => {
    if (initialized && selectedStates.length > 0) {
      onSelectionChange([], selectedStates);
      // Auto-compute with all states selected by default
      onApplyFilters({
        campagne_ids: [],
        etats_campagne: selectedStates,
        date_min: null,
        date_max: null,
        gestionnaires: undefined,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialized]);

  // Sync campaign selections with available options (auto-remove invalid campaigns)
  useEffect(() => {
    if (filterOptions && initialized) {
      const availableCampaignIds = filterOptions.campagnes.map(c => c.id);
      const validCampaigns = selectedCampaigns.filter(id => availableCampaignIds.includes(id));

      // Only update if there are invalid selections to remove
      if (validCampaigns.length !== selectedCampaigns.length) {
        setSelectedCampaigns(validCampaigns);
      }
    }
  }, [filterOptions, selectedCampaigns, initialized]);

  const handleApply = () => {
    onApplyFilters({
      campagne_ids: selectedCampaigns,
      etats_campagne: selectedStates,
      date_min: null,
      date_max: null,
      gestionnaires: selectedGestionnaires.length > 0 ? selectedGestionnaires : undefined,
    });
  };

  const handleReset = () => {
    setSelectedCampaigns([]);
    setSelectedGestionnaires([]);
    // Reset to all states selected (default state)
    const allowedStates = new Set(STATE_OPTIONS.map(option => option.value));
    const apiStates = filterOptions?.etats
      ?.map(option => option.value)
      .filter(value => allowedStates.has(value)) || [];
    const nextStates = apiStates.length > 0
      ? apiStates
      : STATE_OPTIONS.map(option => option.value);
    setSelectedStates(nextStates);
    onSelectionChange([], nextStates);
  };

  const toggleCampaign = (campaignId: string) => {
    setSelectedCampaigns(prev =>
      prev.includes(campaignId)
        ? prev.filter(id => id !== campaignId)
        : [...prev, campaignId]
    );
    // Note: Campaign selection does NOT trigger filter refetch
    // Campaigns are filtered by states, not the other way around
  };

  const handleStatesChange = (newStates: string[]) => {
    setSelectedStates(newStates);
    // State change triggers filter update to show matching campaigns
    onSelectionChange([], newStates);
    // Clear campaign selections when states change
    setSelectedCampaigns([]);
  };

  const handleCampaignsChange = (newCampaigns: string[]) => {
    setSelectedCampaigns(newCampaigns);
    // Campaign selection does NOT trigger filter refetch
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-700" />
          <h2 className="text-base font-semibold text-gray-900">Filtres</h2>
        </div>
        <div className="flex items-center gap-3">
          {isLoading && (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <RefreshCw className="w-3 h-3 animate-spin" />
              <span>Chargement...</span>
            </div>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={isLoading}
            className="h-8"
          >
            <X className="w-3 h-3 mr-1" />
            Réinitialiser
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleApply}
            disabled={isLoading}
            className="bg-slate-900 text-white hover:bg-slate-800 h-8"
          >
            {isLoading ? (
              <>
                <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
                Chargement...
              </>
            ) : (
              <>
                <Filter className="w-3 h-3 mr-1" />
                Appliquer
              </>
            )}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* 1. States Filter */}
        <div>
          <Label className="text-xs font-medium text-gray-700 mb-1.5 block">
            États
          </Label>
          <MultiSelect
            options={STATE_OPTIONS}
            selected={selectedStates}
            onChange={handleStatesChange}
            placeholder="États..."
            disabled={isLoading}
          />
        </div>

        {/* 2. Campaigns Filter */}
        <div>
          <Label className="text-xs font-medium text-gray-700 mb-1.5 block">
            Campagnes
          </Label>
          <MultiSelect
            options={
              filterOptions?.campagnes.map((c) => ({
                value: c.id,
                label: `${c.nom} (${c.etat})`,
              })) || []
            }
            selected={selectedCampaigns}
            onChange={handleCampaignsChange}
            placeholder="Campagnes..."
            disabled={isLoading}
          />
        </div>

        {/* 3. Gestionnaires Filter */}
        <div>
          <Label className="text-xs font-medium text-gray-700 mb-1.5 block">
            Gestionnaires
          </Label>
          <MultiSelect
            options={
              gestionnairesData?.gestionnaires.map((g) => ({
                value: g,
                label: g,
              })) || []
            }
            selected={selectedGestionnaires}
            onChange={setSelectedGestionnaires}
            placeholder="Gestionnaires..."
            disabled={isLoading}
          />
        </div>
      </div>
    </div>
  );
}
