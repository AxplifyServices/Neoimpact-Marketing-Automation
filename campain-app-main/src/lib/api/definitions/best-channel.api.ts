import type { ApiRequest } from '../ApiRequest';

export const bestChannelApi = {
  filters: (): ApiRequest => ({
    url: '/data-tools/best-channel/filters',
    method: 'GET',
  }),

  dashboard: (params: {
    annee_mois?: number;
    region?: string;
    statut_client?: string;
  }): ApiRequest => ({
    url: '/data-tools/best-channel/dashboard',
    method: 'GET',
    params,
    timeoutMs: 60_000,
  }),
};
