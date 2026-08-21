export interface AttritionFiltersResponse {
  annee_mois: number[];
  default_annee_mois: number | null;
  regions: string[];
  statuts: string[];
}

export interface AttritionKpis {
  clients_scores: number;
  clients_risque: number;
  taux_risque: number;
  score_moyen: number;
  score_moyen_risque: number;
  seuil_risque: number;
  date_scoring: string | null;
}

export interface AttritionRiskDistributionItem {
  risque: string;
  clients: number;
}

export interface AttritionScoreBandItem {
  tranche: string;
  clients: number;
}

export interface AttritionRegionItem {
  region: string;
  clients_scores: number;
  clients_risque: number;
  taux_risque: number;
  score_moyen: number;
}

export interface AttritionDashboardResponse {
  filters: { annee_mois: number; region: string | null; statut: string | null };
  kpis: AttritionKpis;
  risk_distribution: AttritionRiskDistributionItem[];
  score_bands: AttritionScoreBandItem[];
  regions: AttritionRegionItem[];
  variations_risque: {
    horizons: string[];
    avoirs: number[];
    flux_crediteurs: number[];
    flux_debiteurs: number[];
  };
  training: {
    rows: number;
    attritions_observees: number;
    mois_min: number | null;
    mois_max: number | null;
  };
  model: {
    exists: boolean;
    model_code: string | null;
    trained_at: string | null;
    training_rows: number | null;
    positive_rows_total: number | null;
    validation_auc: number | null;
    validation_precision: number | null;
    validation_recall: number | null;
  };
}
