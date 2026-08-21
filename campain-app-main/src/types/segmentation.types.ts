export interface SegmentationFiltersResponse {
  annee_mois: number[];
  default_annee_mois: number | null;
  regions: string[];
  tranches_age: string[];
}

export interface SegmentationKpis {
  clients_segmentes: number;
  taux_salaries: number;
  flux_moyen_3m: number;
  avoir_moyen_3m: number;
  frequence_flux_moyenne: number;
  taux_haut_potentiel: number;
  calculs_periode: number;
  derniere_date_segmentation: string | null;
}

export interface SegmentDistributionItem {
  segment: string;
  clients: number;
  part: number;
}

export interface SalaryDistributionItem {
  statut: string;
  clients: number;
}

export interface SegmentationMedianRow {
  region: string;
  tranche_age: string;
  mediane_flux: number;
  mediane_avoirs: number;
  observations: number;
}

export interface SegmentationDashboardResponse {
  filters: {
    annee_mois: number;
    region: string | null;
    tranche_age: string | null;
  };
  kpis: SegmentationKpis;
  segments: SegmentDistributionItem[];
  statuts_salarie: SalaryDistributionItem[];
  medianes: SegmentationMedianRow[];
}
