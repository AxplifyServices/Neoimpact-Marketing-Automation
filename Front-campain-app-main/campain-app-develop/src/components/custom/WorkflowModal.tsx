import { useMemo, useCallback } from 'react';
import { X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { dashboardApi } from '@/lib/api/definitions/dashboard.api';
import { getApiClient } from '@/lib/api/api-client';
import { normalizeBlocks } from '@/lib/modele-normalization';
import { getBlockDisplayNumber } from '@/lib/block-utils';
import type { Block } from '@/types/modele.types';
import WorkflowPreview from './WorkflowPreview';
import LoadingSpinner from '../LoadingSpinner';

interface ModeleDetail {
  id_modele: string;
  nom_modele: string;
  date_creation: string;
  liste_action?: string;
  blocks?: unknown;
}

function parseArrayJson(value: string): any[] | null {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function resolveBlocks(modele: ModeleDetail | undefined): Block[] {
  if (!modele) return [];

  if (Array.isArray(modele.blocks)) {
    return normalizeBlocks(modele.blocks);
  }

  if (typeof modele.blocks === 'string' && modele.blocks.trim() !== '') {
    const parsedBlocks = parseArrayJson(modele.blocks);
    if (parsedBlocks) return normalizeBlocks(parsedBlocks);
  }

  if (typeof modele.liste_action === 'string' && modele.liste_action.trim() !== '') {
    const parsedLegacy = parseArrayJson(modele.liste_action);
    if (parsedLegacy) return normalizeBlocks(parsedLegacy);
  }

  return [];
}

interface WorkflowModalProps {
  isOpen: boolean;
  onClose: () => void;
  modelId: string;
  campaignId?: string;
}

export default function WorkflowModal({
  isOpen,
  onClose,
  modelId,
  campaignId,
}: WorkflowModalProps) {
  const apiClient = getApiClient();

  const { data: modele, isLoading: modeleLoading } = useQuery<ModeleDetail>({
    queryKey: ['modele', modelId],
    queryFn: () => apiClient.request<ModeleDetail>(modelesApi.findById(modelId)),
    enabled: isOpen && !!modelId,
  });

  const { isLoading: analyticsLoading } = useQuery({
    queryKey: ['campaign-analytics-by-campaign', campaignId],
    queryFn: () => apiClient.request(
      dashboardApi.computeByCampaign({ campagne_ids: campaignId ? [campaignId] : [] })
    ),
    enabled: isOpen && !!campaignId,
  });

  const isLoading = modeleLoading || analyticsLoading;

  const blocks = useMemo(() => resolveBlocks(modele), [modele]);

  const blockDisplayNumber = useCallback((blockId: string) => {
    return getBlockDisplayNumber(blocks, blockId);
  }, [blocks]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl relative"
        style={{ width: '95vw', height: '95vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 z-10 p-2 bg-white/80 hover:bg-white rounded-full shadow-sm transition-colors cursor-pointer"
          aria-label="Fermer"
        >
          <X className="w-6 h-6 text-gray-600" />
        </button>

        <div style={{ width: '100%', height: '100%' }}>
          {isLoading ? (
            <div className="h-full flex items-center justify-center">
              <LoadingSpinner size="lg" />
            </div>
          ) : blocks.length === 0 ? (
            <div className="h-full bg-gray-100 rounded-2xl flex items-center justify-center">
              <span className="text-gray-400 text-sm">Aucun workflow disponible</span>
            </div>
          ) : (
            <WorkflowPreview
              blocks={blocks}
              getBlockDisplayNumber={blockDisplayNumber}
              campaignId={campaignId}
              showHeader={false}
              showFrame={false}
              height="calc(95vh - 40px)"
              containerClassName="rounded-2xl"
            />
          )}
        </div>
      </div>
    </div>
  );
}
