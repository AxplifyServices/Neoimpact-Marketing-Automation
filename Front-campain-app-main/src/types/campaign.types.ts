// API Response Types (from backend)
export interface CampaignAPIResponse {
  id_campagne: string;
  nom_campagne: string;
  id_modele: string;
  id_cible: string;
  date_creation: string;
  date_debut: string;
  date_fin: string;
  etat_campagne: string;
  description?: string;
  // Campaign metrics
  nb_attribues: number;
  nb_conversions: number;
  nb_contactes: number;
  nb_en_traitement: number;
  nb_arriv_eche: number;
}

export interface ModeleAPIResponse {
  id: string;
  id_modele: string;
  nom_modele: string;
  variable_cible: string;
  objectif: string;
  date_creation: string;
  liste_action?: string;
  graphe_json?: string;
}

export interface CibleAPIResponse {
  id?: string;
  id_cible?: string;
  nom_cible: string;
  source: 'DB' | 'FILE';
  created_at?: string;
}

export interface QueueRow {
  row: Record<string, any>;
  context: Record<string, any>;
  resultats: string[];
}

// Campaign types (from useCampagnesData)
export interface Campaign {
  id: string;
  code: string;
  title: string;
  description: string;
  image: string;
  status: string; // Can be: 'En cours', 'En pause', 'Planifié', 'Terminé', or any other value from API
  statusColor: string;
  startDate: string;
  endDate: string;
  target: string;
  model: string;
  id_modele: string;
  id_cible: string;
  // Model visualization data
  modelData?: {
    listeAction: string;
    variableCible: string;
    objectif: string;
  };
  // Campaign metrics
  metrics: {
    attribues: number;
    conversions: number;
    contactes: number;
    enTraitement: number;
    arrivEche: number;
  };
}

export interface Stat {
  value: string;
  label: string;
  change: string;
  changeColor: string;
}

// Creation types (from useCreationData)
export interface Cible {
  id: string;
  code: string;
  name: string;
  type: string;
  timestamp: string;
}

// Historique types (from useHistoriqueData)
export interface HistoryRecord {
  id: string;
  idCampagne: string;
  relatedCompte: string;
  statutAvantCampagne: string;
  statutActual: string;
  titleCampagne: string;
  nbJourCampagne: number;
  idAction: number;
  action: string;
  lastAction: string;
  resultatLastAction: string;
  dateLastAction: string;
  nbAppel: string;
  nbSms: string;
  nbMail: string;
  nbMessage: string;
}

// CRC types (from useCRCData)
export interface Action {
  id: string;
  calloutContact: string;
  campaignId: string;
  dateAffectation: string;
  nbJourAffecte: number;
  nom: string;
  prenom: string;
  numeroTel: string;
  adresseMail: string;
  region: string;
  agence: string;
  personnalite: string;
  colonne: string;
  objectif: string;
  traitement: string;
}

export interface QueueContact {
  row: {
    ID_CAMPAGNE?: string;
    id_campagne?: string;
    Radical_compte?: string;
    radical_compte?: string;
    [key: string]: any;  // Other dynamic fields
  } | null;  // Can be null when queue is empty
  context: {
    nom?: string;
    prenom?: string;
    nom_campagne?: string;
    variable_cible?: string;
    valeur_cible?: string;
    objectif?: string;
    statut_actuel?: string;
    [key: string]: any;  // Other dynamic context fields
  } | null;  // Can be null when queue is empty
  resultats: string[];  // Available result options
  flags?: {
    arriv_eche?: boolean;  // Deadline approaching flag
    [key: string]: any;  // Other dynamic flags
  };
}

// Dashboard types (from useDashboardData)
export interface StatCard {
  icon?: React.ReactElement;
  title: string;
  value: string;
  secondaryValue: string;
  secondaryLabel: string;
  bgColor: string;
  iconColor: string;
}

export interface ChartDataPoint {
  name: string;
  value: number;
  [key: string]: string | number;  // Index signature for Recharts compatibility
}

export interface PerformanceDataPoint {
  name: string;
  value: number;
}

// Dashboard Compute API Response
export interface DashboardKPIs {
  clients_transmis: number;
  clients_contactes: number;
  objectifs_atteints: number;
  clients_en_attente: number;
  clients_en_attente_en_traitement: number;
  nb_appel: number;
  nb_mail: number;
  nb_sms: number;
  nb_message: number;
  taux_reussite: number;
  taux_contact: number;
}

export interface SuccessByChannel {
  Canal: string;
  Clients: number;
  Closed: number;
  Taux_reussite: number;
}

export interface DailyAction {
  Date: string;
  Actions: number;
}

export interface BacklogOverTime {
  Date: string;
  Backlog_non_traite: number;
}

export interface CallsBeforeSuccess {
  n_closed: number;
  moy_appels_closed: number;
}

export interface DashboardComputeResponse {
  ok: boolean;
  empty: boolean;
  kpis: DashboardKPIs;
  series: {
    success_by_channel: SuccessByChannel[];
    daily_actions: DailyAction[];
    backlog_over_time: BacklogOverTime[];
    calls_before_success: CallsBeforeSuccess;
  };
}
