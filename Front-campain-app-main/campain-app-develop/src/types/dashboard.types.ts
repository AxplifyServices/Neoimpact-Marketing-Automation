// Dashboard Filter Types
export interface DashboardFilterOption {
  value: string;
  label: string;
}

export interface DashboardCampaign {
  id: string;
  label: string;
  etat: string;
  nom: string;
}

export interface DashboardFiltersResponse {
  etats: DashboardFilterOption[];
  campagnes: DashboardCampaign[];
}

// Dashboard Compute Request
export interface DashboardComputeRequest {
  campagne_ids: string[];
  etats_campagne: string[];
  date_min: string | null;
  date_max: string | null;
  gestionnaires?: string[];
}

// Dashboard KPIs
export interface DashboardKPIs {
  transmis: number;
  contactes_total: number;
  closing_total: number;
  traitements_total: number;
  taux_contact_total: number;
  taux_closing_sur_affectes: number;
  taux_closing_sur_traitements_total: number;
}

// Dashboard Tables
export interface ChannelTableRow {
  Canal: string;
  Traitements: number;
  Closing: number;
  Taux_closing_sur_traitements: number;
  Clients_contactes: number;
  Taux_contact_sur_transmis: number;
}

// Dashboard Series Data
export interface RegionData {
  Region: string;
  Transmis: number;
  Closed: number;
}

export interface FunnelData {
  ID_Action: string;
  Clients: number;
}

export interface DailyData {
  Date: string;
  Traitements: number;
  Closed: number;
}

// Campaign Graph Types
export interface CampaignGraphNode {
  id: string;
  label: string;
  count: number;
  converted_count: number;
  canal: string;
  action: string;
}

export interface CampaignGraphEdge {
  from: string;
  to: string;
}

export interface CampaignGraph {
  campaign_id: string;
  modele_id: string;
  modele_nom: string;
  nodes: CampaignGraphNode[];
  edges: CampaignGraphEdge[];
}

// Dashboard Compute Response
export interface DashboardComputeResponse {
  filters_applied: DashboardComputeRequest;
  kpis: DashboardKPIs;
  tables: {
    by_channel: ChannelTableRow[];
  };
  series: {
    region_transmit_closed: RegionData[];
    funnel_by_id_action: FunnelData[];
    daily_treatments_closed: DailyData[];
  };
  graph?: CampaignGraph; // Optional - only present when single campaign selected
}

// Per-Campaign Dashboard Data (from /dashboard/compute-by-campagne)
export interface PerCampaignData {
  campagne_id: string;
  kpis: DashboardKPIs;
  tables: {
    by_channel: ChannelTableRow[];
  };
  series: {
    region_transmit_closed: RegionData[];
    funnel_by_id_action: FunnelData[];
    daily_treatments_closed: DailyData[];
  };
  graph: CampaignGraph;
}

export interface DashboardComputeByCampaignResponse {
  filters_applied: {
    campagne_ids: string[];
    etats_campagne: string[];
    date_min: string | null;
    date_max: string | null;
  };
  kpis: DashboardKPIs;
  tables: {
    by_channel: ChannelTableRow[];
  };
  series: {
    region_transmit_closed: RegionData[];
    funnel_by_id_action: FunnelData[];
    daily_treatments_closed: DailyData[];
  };
  graph: CampaignGraph;
  by_campaign: Record<string, PerCampaignData>;
}
