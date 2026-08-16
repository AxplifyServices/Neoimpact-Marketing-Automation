import type { ApiRequest } from '../ApiRequest';
import type { TypeCampagne, VisitMode, VisitPurpose } from '@/types/campaign.types';

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
    description?: string;
    type_campagne?: TypeCampagne;
    visitMode?: VisitMode | null;
    visitPurpose?: VisitPurpose | null;
  }): ApiRequest => ({
    url: '/campagnes',
    method: 'POST',
    body: data,
    // Une création de campagne peut affecter plusieurs centaines de milliers de clients.
    // Le backend est bulk PostgreSQL, mais on évite un faux timeout navigateur à 30 s.
    timeoutMs: 120000,
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
