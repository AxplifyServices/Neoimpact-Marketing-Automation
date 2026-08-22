export interface ProductScoringFiltersResponse {
  months: number[];
  default_annee_mois: number | null;
  regions: string[];
  statuses: string[];
  products: string[];
  cards: string[];
}

export interface ProductScoringSummary {
  scored_clients: number;
  avg_card: number;
  avg_conso: number;
  avg_immo: number;
  avg_epargne: number;
  avg_nbp_score: number;
  card_eligible_clients: number;
  epargne_eligible_clients: number;
  last_scoring?: string | null;
}

export interface ProductDistributionRow {
  product: string;
  clients: number;
  avg_score: number;
}

export interface CardRecommendationRow {
  card: string;
  clients: number;
  avg_score: number;
}

export interface CreditSegmentRow {
  segment: string;
  clients: number;
  avg_score: number;
}

export interface ProductRegionRow {
  region: string;
  clients: number;
  avg_card: number;
  avg_conso: number;
  avg_immo: number;
  avg_epargne: number;
  dominant_product: string;
}

export interface ProductModelMetadata {
  model_version?: string;
  model_code: string;
  trained_at?: string;
  trained_month?: number;
  training_rows: number;
  validation_rows?: number;
  positive_rows: number;
  validation_auc?: number | null;
  best_iteration?: number;
}

export interface ProductFeedbackSummary {
  assignments: number;
  contacted: number;
  resolved: number;
  conversions: number;
  appetent_assignments: number;
  conversion_rate: number;
}

export interface ProductScoringDashboardResponse {
  filters: {
    annee_mois: number | null;
    region?: string | null;
    statut_client?: string | null;
  };
  summary: ProductScoringSummary;
  next_best_product: ProductDistributionRow[];
  card_recommendations: CardRecommendationRow[];
  credit_segments: {
    conso: CreditSegmentRow[];
    immo: CreditSegmentRow[];
  };
  regions: ProductRegionRow[];
  models: ProductModelMetadata[];
  feedback: ProductFeedbackSummary;
}
