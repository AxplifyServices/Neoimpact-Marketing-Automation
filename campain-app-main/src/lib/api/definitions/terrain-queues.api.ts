import type { ApiRequest } from '../ApiRequest';
import type { QueueType } from '@/types/campaign.types';

export const terrainQueuesApi = {
  getNext: (
    queue: QueueType,
    id_campagne?: string | null,
    gestionnaire?: string | null
  ): ApiRequest => ({
    url: `/terrain-queues/${queue}/next`,
    method: 'GET',
    params: {
      ...(id_campagne ? { id_campagne } : {}),
      ...(gestionnaire ? { gestionnaire } : {}),
    },
  }),

  applyResult: (
    queue: QueueType,
    data: {
      id_campagne: string;
      radical_compte: string;
      resultat: string;
    },
    gestionnaire?: string | null
  ): ApiRequest => ({
    url: `/terrain-queues/${queue}/apply-result`,
    method: 'POST',
    body: data,
    params: {
      id_campagne: data.id_campagne,
      ...(gestionnaire ? { gestionnaire } : {}),
    },
  }),

  getGestionnaires: (queue: QueueType): ApiRequest => ({
    url: `/terrain-queues/${queue}/gestionnaires`,
    method: 'GET',
  }),

  countsByGestionnaire: (
    queue: QueueType,
    id_campagne?: string | null
  ): ApiRequest => ({
    url: `/terrain-queues/${queue}/counts-by-gestionnaire`,
    method: 'GET',
    params: {
      ...(id_campagne ? { id_campagne } : {}),
    },
  }),

  getOrdered: (
    queue: QueueType,
    id_campagne?: string | null,
    gestionnaire?: string | null
  ): ApiRequest => ({
    url: `/terrain-queues/${queue}/ordered`,
    method: 'GET',
    params: {
      ...(id_campagne ? { id_campagne } : {}),
      ...(gestionnaire ? { gestionnaire } : {}),
    },
  }),
};
