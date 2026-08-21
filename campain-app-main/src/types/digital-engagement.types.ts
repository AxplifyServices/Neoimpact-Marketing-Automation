export interface DigitalEngagementFiltersResponse {
  months: number[];
  regions: string[];
  statuses: string[];
  engagements: string[];
  creneaux: string[];
}

export interface DigitalEngagementDashboardResponse {
  annee_mois: number | null;
  summary: {
    scored_clients: number;
    high_clients: number;
    high_rate: number;
    avg_daily_connections: number;
    median_daily_connections: number;
    avg_weighted_hour: number | null;
  };
  engagement_distribution: Array<{ label: string; clients: number }>;
  creneau_distribution: Array<{ label: string; clients: number }>;
  regions: Array<{
    region: string;
    clients: number;
    high_clients: number;
    avg_daily_connections: number;
  }>;
}
