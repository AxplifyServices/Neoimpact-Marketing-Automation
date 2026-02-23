import type { ApiRequest } from '../ApiRequest';

export const queuesApi = {
  // Get next contact from queue
  getNext: (queue: 'crc' | 'da' | 'cc', id_campagne?: string | null, gestionnaire?: string | null): ApiRequest => ({
    url: `/queues/${queue}/next`,
    method: 'GET',
    params: {
      ...(id_campagne ? { id_campagne } : {}),
      ...(gestionnaire ? { gestionnaire } : {}),
    },
  }),

  // Apply result to current contact
  applyResult: (
    queue: 'crc' | 'da' | 'cc',
    data: {
      id_campagne: string;
      radical_compte: string;
      resultat: string;
    },
    gestionnaire?: string | null
  ): ApiRequest => ({
    url: `/queues/${queue}/apply-result`,
    method: 'POST',
    body: data,
    params: {
      id_campagne: data.id_campagne,
      ...(gestionnaire ? { gestionnaire } : {}),
    },
  }),

  // Skip current contact
  skip: (
    queue: 'crc' | 'da' | 'cc',
    data: {
      id_campagne: string;
      radical_compte: string;
    }
  ): ApiRequest => ({
    url: `/queues/${queue}/skip`,
    method: 'POST',
    body: data,
  }),

  // Initiate call (CRC only)
  initiateCall: (): ApiRequest => ({
    url: '/queues/crc/call',
    method: 'POST',
  }),

  // Get list of gestionnaires (CRC)
  getGestionnaires: (): ApiRequest => ({
    url: '/queues/crc/gestionnaires',
    method: 'GET',
  }),
};
