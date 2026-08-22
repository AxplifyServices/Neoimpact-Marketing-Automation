export interface BestChannelFiltersResponse {
  months: number[];
  default_annee_mois: number | null;
  regions: string[];
  statuses: string[];
  channels: string[];
}

export interface BestChannelDashboardResponse {
  filters: {
    annee_mois: number | null;
    region: string | null;
    statut_client: string | null;
  };
  summary: {
    scored_clients: number;
    non_scored: number;
    avg_top1_score: number;
    max_top1_score: number;
    last_scoring: string | null;
    sequences: number;
    converted_sequences: number;
    conversion_rate: number;
  };
  top1_distribution: Array<{
    canal: string;
    clients: number;
    avg_score: number;
  }>;
  top3_distribution: Array<{
    canal: string;
    top1: number;
    top2: number;
    top3: number;
    avg_score: number;
  }>;
  regions: Array<{
    region: string;
    clients_scores: number;
    avg_top1_score: number;
    dominant_channel: string | null;
    dominant_clients: number;
  }>;
  training: {
    interaction_rows: number;
    fake_rows: number;
    real_rows: number;
    sequences: number;
    converted_sequences: number;
    fake_sequences: number;
    real_sequences: number;
    observed_min: string | null;
    observed_max: string | null;
  };
  model: {
    exists: boolean;
    model_code: string | null;
    trained_at: string | null;
    training_rows: number | null;
    validation_rows: number | null;
    positive_rows: number | null;
    validation_auc: number | null;
    best_iteration: number | null;
  };
}
