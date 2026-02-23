import type { ApiRequest } from '../ApiRequest';

export const modelesApi = {
  // Get all modeles
  findAll: (): ApiRequest => ({
    url: '/modeles',
    method: 'GET',
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
