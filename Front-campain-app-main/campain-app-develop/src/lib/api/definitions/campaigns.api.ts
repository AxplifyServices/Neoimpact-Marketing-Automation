import type { ApiRequest } from '../ApiRequest';

export const campaignsApi = {
  // Get all campaigns
  findAll: (): ApiRequest => ({
    url: '/campagnes',
    method: 'GET',
  }),

  // Create new campaign
  create: (data: {
    nom_campagne: string;
    id_modele: string;
    id_cible: string;
    date_debut: string;
    date_fin: string;
  }): ApiRequest => ({
    url: '/campagnes',
    method: 'POST',
    body: data,
  }),

  // Pause campaign
  pause: (id: string): ApiRequest => ({
    url: `/campagnes/${id}/pause`,
    method: 'POST',
  }),

  // Activate campaign
  activate: (id: string): ApiRequest => ({
    url: `/campagnes/${id}/activer`,
    method: 'POST',
  }),

  // Cancel campaign (replaces delete)
  cancel: (id: string): ApiRequest => ({
    url: `/campagnes/${id}/annuler`,
    method: 'POST',
  }),
};
