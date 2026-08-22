export interface CommercialPressureFiltersResponse {
  months: number[];
  default_annee_mois: number | null;
  regions: string[];
  statuses: string[];
  levels: string[];
}

export interface CommercialPressureSummary {
  scored_clients: number;
  high_clients: number;
  high_rate: number;
  avg_score: number;
  avg_actions_7d: number;
  avg_actions_30d: number;
  avg_channels_7d: number;
  last_scoring?: string | null;
}

export interface CommercialPressureDistributionRow {
  niveau: string;
  clients: number;
  avg_score: number;
  avg_actions_30d: number;
}

export interface CommercialPressureRegionRow {
  region: string;
  clients: number;
  high_clients: number;
  high_rate: number;
  avg_score: number;
  avg_actions_30d: number;
}

export interface CommercialPressureRuleRow {
  regle: string;
  clients: number;
}

export interface CommercialPressureDashboardResponse {
  filters: {
    annee_mois: number | null;
    region?: string | null;
    statut_client?: string | null;
    niveau?: string | null;
  };
  summary: CommercialPressureSummary;
  distribution: CommercialPressureDistributionRow[];
  regions: CommercialPressureRegionRow[];
  rules: CommercialPressureRuleRow[];
  thresholds: Record<string, number>;
}

export interface CibleCommercialPressureSummary {
  supported: boolean;
  total: number;
  eleve: number;
  pct_eleve: number;
  warning_threshold_pct: number;
  warning: boolean;
  distribution: Array<{ niveau: string; clients: number; pct: number }>;
}
