import type { ApiRequest } from '../ApiRequest';

export const digitalEngagementApi = {
  filters: (): ApiRequest => ({
    url: '/data-tools/digital-engagement/filters',
    method: 'GET',
  }),
  dashboard: (params: {
    annee_mois?: number;
    region?: string;
    statut_client?: string;
  }): ApiRequest => ({
    url: '/data-tools/digital-engagement/dashboard',
    method: 'GET',
    params,
  }),
};
