import type { ApiRequest } from '../ApiRequest';
import type { TypeCampagne, VisitMode, VisitPurpose } from '@/types/campaign.types';

export const campaignsApi = {
  // Get campaigns with server-side pagination. `offset` is the backend page index.
  findAll: (params?: { limit?: number; offset?: number; pages?: number; etat?: string; q?: string; etats?: string; date_min?: string; date_max?: string }): ApiRequest => ({
    url: '/campagnes',
    method: 'GET',
    params,
  }),


  // Ultra-light polling while one or more campaigns are being prepared.
  processingStatuses: (ids: string[]): ApiRequest => ({
    url: '/campagnes/processing-statuses',
    method: 'GET',
    params: { ids },
  }),

  // Lightweight label/id lookups used by campaign cards.
  modeleChoices: (): ApiRequest => ({
    url: '/campagnes/meta/modele-choices',
    method: 'GET',
  }),

  cibleChoices: (): ApiRequest => ({
    url: '/campagnes/meta/cible-choices',
    method: 'GET',
  }),

  // Lightweight options used by the campaign creation modal.
  createOptions: (): ApiRequest => ({
    url: '/campagnes/meta/create-options',
    method: 'GET',
  }),

  // Lightweight active campaigns for selectors (CRC / Terrain).
  activeChoices: (): ApiRequest => ({
    url: '/campagnes/meta/active-choices',
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
    timeoutMs: 15000,
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
