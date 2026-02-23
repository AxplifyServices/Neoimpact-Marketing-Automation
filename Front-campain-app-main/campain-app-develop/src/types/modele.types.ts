export type ConditionType = 'days_since_last' | 'flag_resultat' | 'counter' | 'client_filter' | 'campaign_field' | 'client_field';

export interface BlockCondition {
  id: string;
  type: ConditionType;
  operator?: string;
  daysSinceLastAction?: number;
  flagResultat?: string;
  counterValue?: number;
  column?: string;
  min?: string;
  max?: string;
  values?: string[];
  campaignField?: string;
  campaignFieldValue?: number;
  clientField?: string;
  clientFieldValue?: string;
  nextBlockId: string | null;
}

export interface Block {
  id: string;
  canal: string;
  delai: number;
  parents: string[];
  objet?: string;
  contenu?: string;
  conditionsByParent: Record<string, BlockCondition[]>;
  isObjectif: boolean;
  valideObjectif?: 'Oui' | 'Non';
  objectiveConditions: BlockCondition[];
  objectiveOperator: 'AND' | 'OR';
}

export interface CampaignConditionField {
  field: string;
  db_field: string;
  type: 'numeric';
}

export interface CanauxMetadata {
  canaux: string[];
  actions_by_canal: Record<string, string>;
  resultats_by_canal: Record<string, string[]>;
  compteur_by_canal: Record<string, string>;
}

export interface EditPayload {
  id_modele: string;
  nom_modele: string;
  variable_cible: string;
  objectif?: string;
  objectif_value_for_store?: string | Record<string, unknown> | null;
  liste_action?: string;
  blocks?: any[] | string;
}

export interface DuplicateState {
  duplicateId?: string;
}

export type ConditionMetaResponse = Record<string, string[] | 'Numérique'>;
