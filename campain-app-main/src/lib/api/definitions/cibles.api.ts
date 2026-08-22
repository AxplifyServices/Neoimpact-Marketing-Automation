import type { ApiRequest } from '../ApiRequest';

export const ciblesApi = {
  // Get all cibles
  findAll: (params?: { limit?: number; offset?: number; pages?: number; q?: string; source?: string; locked?: boolean; date_min?: string; date_max?: string; objectif_mode?: 'atteint' | 'non_atteint' | 'none'; objectif_campaign?: string; sort_by?: string; sort_dir?: 'asc' | 'desc' }): ApiRequest => ({
    url: '/cibles',
    method: 'GET',
    params,
  }),


  // Lightweight campaigns used by cible objective filters
  getObjectiveCampaigns: (): ApiRequest => ({
    url: '/cibles/objective-campaigns',
    method: 'GET',
  }),

  // Get cible by ID
  findById: (id: string): ApiRequest => ({
    url: `/cibles/${id}`,
    method: 'GET',
  }),

  // Create cible from database with filters
  createFromDB: (data: {
    nom_cible: string;
    filtre: Record<string, any>;
  }): ApiRequest => ({
    url: '/cibles/db',
    method: 'POST',
    body: data,
  }),

  // Create cible from uploaded file
  createFromFile: (nomCible: string, file: File): ApiRequest => {
    const formData = new FormData();
    formData.append('nom_cible', nomCible);
    formData.append('file', file);
    return {
      url: '/cibles/file',
      method: 'POST',
      body: formData,
    };
  },

  // Delete cible
  delete: (id: string): ApiRequest => ({
    url: `/cibles/${id}`,
    method: 'DELETE',
  }),

  // Update cible
  update: (id: string, data: {
    id_cible: string;
    nom_cible: string;
    source: string;
    date_creation: string;
    filtre?: Record<string, any>;
    chemin?: string;
  }): ApiRequest => ({
    url: `/cibles/${id}`,
    method: 'PUT',
    body: data,
  }),

  // Get cible filter configuration
  getFiltre: (id: string): ApiRequest => ({
    url: `/cibles/${id}/filtre`,
    method: 'GET',
  }),

  // Get locked cibles
  getLocked: (): ApiRequest => ({
    url: '/cibles/locked',
    method: 'GET',
  }),

  // Engagement digital composition of a cible
  engagementSummary: (id: string): ApiRequest => ({
    url: `/cibles/${id}/engagement-summary`,
    method: 'GET',
  }),

  // Répartition du canal Top 1 dans la cible
  bestChannelSummary: (id: string): ApiRequest => ({
    url: `/cibles/${id}/best-channel-summary`,
    method: 'GET',
  }),

  // Répartition dynamique de la pression commerciale dans la cible
  commercialPressureSummary: (id: string): ApiRequest => ({
    url: `/cibles/${id}/commercial-pressure-summary`,
    method: 'GET',
  }),

  // Preview cible data
  preview: (id: string, limit: number = 200): ApiRequest => ({
    url: `/cibles/${id}/preview`,
    method: 'GET',
    params: { limit },
  }),
};
