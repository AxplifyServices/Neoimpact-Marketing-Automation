// Client interface matching all fields from /data/read response
export interface Client {
  // Mandatory fields
  ID_Client: string;
  Numero_Tel: string;
  Mail: string;

  // Optional text fields
  Nom?: string;
  Prenom?: string;
  Qualite?: string;
  Region?: string;
  Agence?: string;
  Gestionnaire?: string;
  STATUT_CLIENT?: string;
  Canal_acquisition?: string;
  Segment_actuel?: string;
  Carte_Actuelle?: string;
  Assurance_Actuelle?: string;

  // Optional Yes/No fields
  Dossier_Complet?: 'OUI' | 'NON' | '';
  Validation_KYC?: 'OUI' | 'NON' | '';
  Activation_du_compte?: 'OUI' | 'NON' | '';
  Activation_carte?: 'OUI' | 'NON' | '';
  Epargne?: 'OUI' | 'NON' | '';
  revenu_domicilie?: 'Oui' | 'Non' | '';

  // Optional numeric fields
  Age?: number;
  Anciennete?: number;
  nb_transaction?: number;
  vol_transaction?: number;
  nb_retrait_gab?: number;
  vol_retrait_gab?: number;
  nb_transaction_ecom?: number;
  vol_transaction_ecom?: number;
  nb_virement?: number;
  vol_virement?: number;
  solde_moyen_depots?: number;
  encours_moyen?: number;
  encours_global?: number;
  encours_conso?: number;
  encours_immo?: number;
  montant_revenu?: number;
}

// Form state type - all fields as strings for controlled inputs
export interface ClientFormData {
  // Mandatory fields
  ID_Client: string;
  Numero_Tel: string;
  Mail: string;

  // Optional text fields
  Nom: string;
  Prenom: string;
  Qualite: string;
  Region: string;
  Agence: string;
  Gestionnaire: string;
  STATUT_CLIENT: string;
  Canal_acquisition: string;
  Segment_actuel: string;
  Carte_Actuelle: string;
  Assurance_Actuelle: string;

  // Optional Yes/No fields (as strings for radio button values)
  Dossier_Complet: string;
  Validation_KYC: string;
  Activation_du_compte: string;
  Activation_carte: string;
  Epargne: string;
  revenu_domicilie: string;

  // Optional numeric fields (as strings for input values)
  Age: string;
  Anciennete: string;
  nb_transaction: string;
  vol_transaction: string;
  nb_retrait_gab: string;
  vol_retrait_gab: string;
  nb_transaction_ecom: string;
  vol_transaction_ecom: string;
  nb_virement: string;
  vol_virement: string;
  solde_moyen_depots: string;
  encours_moyen: string;
  encours_global: string;
  encours_conso: string;
  encours_immo: string;
  montant_revenu: string;
}

// API response type
export interface ClientAPIResponse extends Client {
  id?: string;
  radical_compte?: string;
  __rowid__?: number;
  date_creation?: string;
}
