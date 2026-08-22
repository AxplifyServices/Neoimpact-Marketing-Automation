import type { ApiRequest } from '../ApiRequest';

export const commercialPressureApi = {
  filters: (): ApiRequest => ({
    url: '/data-tools/commercial-pressure/filters',
    method: 'GET',
  }),

  dashboard: (params?: {
    annee_mois?: number;
    region?: string;
    statut_client?: string;
    niveau?: string;
  }): ApiRequest => ({
    url: '/data-tools/commercial-pressure/dashboard',
    method: 'GET',
    params,
  }),
};
