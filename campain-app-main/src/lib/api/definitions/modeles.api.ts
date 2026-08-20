import type { ApiRequest } from '../ApiRequest';

export const modelesApi = {
  // Get all modeles
  findAll: (params?: { limit?: number; offset?: number; pages?: number; q?: string; locked?: boolean; date_min?: string; date_max?: string; variable?: string; sort_by?: string; sort_dir?: 'asc' | 'desc' }): ApiRequest => ({
    url: '/modeles',
    method: 'GET',
    params,
  }),

  // Get modele by ID
  findById: (id: string): ApiRequest => ({
    url: `/modeles/${id}`,
    method: 'GET',
  }),

  // Get edit payload for modele
  getEditPayload: (id: string): ApiRequest => ({
    url: `/modeles/${id}/edit-payload`,
    method: 'GET',
  }),

  // Save modele (create or update)
  save: (data: {
    is_editing: boolean;
    id_modele: string;
    nom_modele: string;
    variable_cible: string;
    objectif_value_for_store: string;
    blocks: any[];
    ui_positions?: Record<string, unknown>;
  }): ApiRequest => ({
    url: '/modeles/save',
    method: 'POST',
    body: data,
  }),

  // Delete modele
  delete: (id: string): ApiRequest => ({
    url: `/modeles/${id}`,
    method: 'DELETE',
  }),

  // Get locked modeles
  getLocked: (): ApiRequest => ({
    url: '/modeles/locked',
    method: 'GET',
  }),
};
