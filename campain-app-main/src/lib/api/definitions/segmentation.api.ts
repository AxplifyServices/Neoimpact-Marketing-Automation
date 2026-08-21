import type { ApiRequest } from '../ApiRequest';

export const segmentationApi = {
  filters: (): ApiRequest => ({
    url: '/data-tools/segmentation/filters',
    method: 'GET',
  }),

  dashboard: (params: {
    annee_mois: number;
    region?: string;
    tranche_age?: string;
  }): ApiRequest => ({
    url: '/data-tools/segmentation/dashboard',
    method: 'GET',
    params,
    timeoutMs: 60_000,
  }),
};
