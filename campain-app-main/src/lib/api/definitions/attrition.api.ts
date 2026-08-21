import type { ApiRequest } from '../ApiRequest';

export const attritionApi = {
  filters: (): ApiRequest => ({
    url: '/data-tools/attrition/filters',
    method: 'GET',
  }),

  dashboard: (params: { annee_mois: number; region?: string; statut?: string }): ApiRequest => ({
    url: '/data-tools/attrition/dashboard',
    method: 'GET',
    params,
    timeoutMs: 60_000,
  }),
};
