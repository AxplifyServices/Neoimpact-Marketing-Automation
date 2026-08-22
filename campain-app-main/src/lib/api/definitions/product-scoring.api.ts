import type { ApiRequest } from '../ApiRequest';

export const productScoringApi = {
  filters: (): ApiRequest => ({
    url: '/data-tools/product-scoring/filters',
    method: 'GET',
  }),

  dashboard: (params?: {
    annee_mois?: number;
    region?: string;
    statut_client?: string;
  }): ApiRequest => ({
    url: '/data-tools/product-scoring/dashboard',
    method: 'GET',
    params,
  }),
};
