import type { ApiRequest } from '../ApiRequest';

export const ciblesApi = {
  // Get all cibles
  findAll: (): ApiRequest => ({
    url: '/cibles',
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

  // Preview cible data
  preview: (id: string, limit: number = 200): ApiRequest => ({
    url: `/cibles/${id}/preview`,
    method: 'GET',
    params: { limit },
  }),
};
