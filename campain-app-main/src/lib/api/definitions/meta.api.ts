import type { ApiRequest } from '../ApiRequest';

/**
 * Meta API endpoints for retrieving system metadata
 * Base URL: http://51.75.252.139:8000/api/meta
 */
export const metaApi = {
  /**
   * Get all available canaux (channels) and their related configurations
   * GET /meta/canaux
   *
   * Returns:
   * - canaux: List of available channels
   * - actions_by_canal: Action label for each channel
   * - resultats_by_canal: Possible results for each channel
   * - compteur_by_canal: Counter field name for each channel
   */
  getCanaux: (): ApiRequest => ({
    url: '/meta/canaux',
    method: 'GET',
  }),

  /**
   * Get all available variables and their configurations
   * GET /meta/variables
   *
   * Returns:
   * - variable_choices: All available variables
   * - categorical_cols_allowed: Variables that can be used for categorical filtering
   * - numeric_cols: Variables that are numeric
   */
  getVariables: (): ApiRequest => ({
    url: '/meta/variables',
    method: 'GET',
  }),

  /**
   * Get modalités (allowed values) for a specific variable
   * GET /meta/modalites/{variable}
   *
   * Returns:
   * - modalites: List of allowed values for this variable
   */
  getModalites: (variable: string): ApiRequest => ({
    url: `/meta/modalites/${encodeURIComponent(variable)}`,
    method: 'GET',
  }),

  /**
   * Get client table fields for condition building
   * GET /meta/conditions/clients-fields
   *
   * Returns:
   * - fields: Array of { col: string, type: 'TEXT' | 'REAL' | 'INTEGER', is_numeric: '0' | '1' }
   */
  getClientFields: (): ApiRequest => ({
    url: '/meta/conditions/clients-fields',
    method: 'GET',
  }),

  /**
   * Get cible metadata with all fields and their possible values
   * GET /meta/cible
   *
   * Returns:
   * - Record<string, string[] | "Numérique">
   *   - string[] for categorical fields with their possible values
   *   - "Numérique" for numeric fields
   */
  getCibleMeta: (): ApiRequest => ({
    url: '/meta/cible',
    method: 'GET',
    params: { limit: 5000 },
  }),

  /**
   * Get condition metadata with all fields and their possible values
   * GET /meta/condition
   *
   * Returns:
   * - Record<string, string[] | "Numérique">
   *   - string[] for categorical fields with their possible values
   *   - "Numérique" for numeric fields
   */
  getConditionMeta: (): ApiRequest => ({
    url: '/meta/condition',
    method: 'GET',
    params: { limit: 5000 },
  }),

  /**
   * Get objectif metadata with variables and their allowed values
   * GET /meta/objectif
   *
   * Returns:
   * - Record<string, string[]>
   *   - Keys are objectif variable names
   *   - Values are arrays of allowed objectif values
   */
  getObjectifMeta: (): ApiRequest => ({
    url: '/meta/objectif',
    method: 'GET',
    params: { limit: 5000 },
  }),

  /**
   * Get client form metadata with field types and allowed values
   * GET /meta/formulaire-client
   *
   * Returns:
   * - Record<string, "Text" | "Numérique" | string[]>
   *   - "Text" for text fields
   *   - "Numérique" for numeric fields
   *   - string[] for categorical fields with their allowed values
   */
  getClientFormMetadata: (): ApiRequest => ({
    url: '/meta/formulaire-client',
    method: 'GET',
    params: { limit: 5000 },
  }),

  /**
   * Get campaign condition fields from clients_campagnes table
   * GET /meta/conditions/clients-campagnes-fields
   *
   * Returns:
   * - fields: Array of { field: string, db_field: string, type: 'numeric' }
   */
  getCampaignConditionFields: (): ApiRequest => ({
    url: '/meta/conditions/clients-campagnes-fields',
    method: 'GET',
  }),

  /**
   * Build multi-objective JSON for model creation
   * POST /meta/objectif/build-multi
   *
   * Returns:
   * - objectif_json: string - Ready-to-use JSON string for objectif field
   */
  buildMultiObjectif: (data: {
    op: 'AND' | 'OR';
    items: Array<{
      variable: string;
      type: 'cat' | 'num';
      value?: string;
      min?: number;
      max?: number;
    }>;
  }): ApiRequest => ({
    url: '/meta/objectif/build-multi',
    method: 'POST',
    body: data,
  }),
};
