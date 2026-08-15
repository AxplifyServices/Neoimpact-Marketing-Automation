BEGIN;

-- ============================================================
-- Neoimpact Marketing Automation
-- PostgreSQL initial schema
--
-- Source :
--   schéma réel de database.db
--
-- IMPORTANT :
-- - aucune donnée SQLite n'est migrée ;
-- - les types restent volontairement proches du modèle SQLite ;
-- - aucune FK n'est ajoutée à cette étape car la base SQLite
--   actuelle n'en possède aucune ;
-- - clients_campagnes reçoit une vraie clé technique "id"
--   pour remplacer le rowid implicite de SQLite.
-- ============================================================


-- ============================================================
-- 1. CLIENTS
-- ============================================================

CREATE TABLE clients (
    radical_compte TEXT PRIMARY KEY,

    "Nom" TEXT,
    "Prenom" TEXT,
    "ID_Client" TEXT UNIQUE,
    "STATUT_CLIENT" TEXT,

    "Age" INTEGER,
    "Qualite" TEXT,
    "Anciennete" INTEGER,

    "Region" TEXT,
    "Agence" TEXT,
    "Gestionnaire" TEXT,

    "Dossier_Complet" TEXT,
    "Validation_KYC" TEXT,
    "Activation_du_compte" TEXT,
    "Activation_carte" TEXT,

    "Canal_acquisition" TEXT,
    "Segment_actuel" TEXT,

    "Numero_Tel" TEXT,
    "Mail" TEXT,

    "Epargne" TEXT,
    "Carte_Actuelle" TEXT,
    "Assurance_Actuelle" TEXT,

    nb_transaction INTEGER,
    vol_transaction DOUBLE PRECISION,

    nb_retrait_gab INTEGER,
    vol_retrait_gab DOUBLE PRECISION,

    nb_transaction_ecom INTEGER,
    vol_transaction_ecom DOUBLE PRECISION,

    nb_virement INTEGER,
    vol_virement DOUBLE PRECISION,

    solde_moyen_depots DOUBLE PRECISION,
    encours_moyen DOUBLE PRECISION,
    encours_global DOUBLE PRECISION,
    encours_conso DOUBLE PRECISION,
    encours_immo DOUBLE PRECISION,

    revenu_domicilie TEXT,
    montant_revenu DOUBLE PRECISION,

    "App_instaled" TEXT,
    "Premiere_connex" TEXT,

    "carte_dispo_agence" TEXT,
    "carte_retiree" TEXT,

    "Carte_virtuelle" TEXT,
    "Etudiant" TEXT,

    "Dotation_touristique" TEXT,
    "Dotation_ecom" TEXT,

    "Compte_CIH_Mobile" TEXT,
    "Compte_MAD_convertible" TEXT,

    "MDM" TEXT,
    "Presence_maroc" TEXT,
    "BP" TEXT,

    "chequier_dispo_agence" TEXT,
    "chequier_retire" TEXT,
    "chequier_active" TEXT,

    "Nature_carte" TEXT,
    "Categorie" TEXT,

    "Nombre_transaction_inter" INTEGER,
    "Volume_transaction_inter" DOUBLE PRECISION,

    is_actif_sem TEXT,
    is_actif_mois TEXT,
    is_actif_trois_mois TEXT,
    is_actif_an TEXT,

    is_inactif_sem TEXT,
    is_inactif_mois TEXT,
    is_inactif_trois_mois TEXT,
    is_inactif_an TEXT,

    credit_conso TEXT,
    credit_immo TEXT,
    credit_autre TEXT,
    "Eligible_credit" TEXT,

    "Compte_CIH_Mobile_active" TEXT,
    "Compte_MAD_convertible_active" TEXT,
    "Carte_virtuelle_active" TEXT,

    "Nb_Operation" DOUBLE PRECISION,
    "Vol_Operation" DOUBLE PRECISION
);


-- ============================================================
-- 2. CIBLES
-- ============================================================

CREATE TABLE cibles (
    id_cible TEXT PRIMARY KEY,
    nom_cible TEXT NOT NULL,
    date_creation TEXT,
    source TEXT,
    filtre TEXT,
    chemin TEXT
);


-- ============================================================
-- 3. CLIENTS / CIBLES
-- ============================================================

CREATE TABLE clients_cibles (
    "ID_CIBLE" TEXT NOT NULL,
    "Radical_compte" TEXT NOT NULL,
    created_at TEXT
);

CREATE UNIQUE INDEX uq_clients_cibles
    ON clients_cibles ("ID_CIBLE", "Radical_compte");

CREATE INDEX idx_clients_cibles_cible
    ON clients_cibles ("ID_CIBLE");

CREATE INDEX idx_clients_cibles_rad
    ON clients_cibles ("Radical_compte");


-- ============================================================
-- 4. MODELES
-- ============================================================

CREATE TABLE modeles (
    id_modele TEXT PRIMARY KEY,
    nom_modele TEXT NOT NULL,
    variable_cible TEXT,
    objectif TEXT,
    date_creation TEXT,
    liste_action TEXT,
    graphe_json TEXT,
    ui_positions TEXT
);

CREATE INDEX idx_modeles_date
    ON modeles (date_creation);


-- ============================================================
-- 5. CAMPAGNES
-- ============================================================

CREATE TABLE campagnes (
    id_campagne TEXT PRIMARY KEY,
    nom_campagne TEXT NOT NULL,
    id_modele TEXT NOT NULL,
    id_cible TEXT NOT NULL,

    date_creation TEXT,
    date_debut TEXT,
    date_fin TEXT,

    etat_campagne TEXT,

    description TEXT,

    type_campagne TEXT DEFAULT 'sans_action_terrain',

    "visitMode" TEXT,
    "visitPurpose" TEXT
);


-- ============================================================
-- 6. CLIENTS / CAMPAGNES
--
-- SQLite utilisait ici rowid implicitement.
-- PostgreSQL n'en possède pas.
--
-- On introduit donc une vraie clé technique.
-- Toutes les 21 colonnes métier existantes sont conservées.
-- ============================================================

CREATE TABLE clients_campagnes (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    "Nom_campagne" TEXT,
    "ID_CAMPAGNE" TEXT,
    "Radical_compte" TEXT,

    "Etat_campagne" TEXT,
    "NB_jour_campagne" INTEGER,

    "ID_Action" TEXT,
    "Canal" TEXT,
    "Action" TEXT,

    "Last_action" TEXT,
    "Resultat_last_action" TEXT,
    "Date_last_action" TEXT,

    "NB_jour_last_action" INTEGER,

    "NB_appel" INTEGER,
    "NB_mail" INTEGER,
    "NB_sms" INTEGER,
    "NB_message" INTEGER,
    "NB_approche_commercial" INTEGER,

    arriv_eche TEXT DEFAULT 'Non',

    date_debut_campagne TEXT,
    nb_jour_debut_campagne INTEGER,

    conversion INTEGER DEFAULT 0
);

CREATE INDEX idx_cc_idcamp
    ON clients_campagnes ("ID_CAMPAGNE");

CREATE INDEX idx_cc_radical
    ON clients_campagnes ("Radical_compte");


-- ============================================================
-- 7. CRC INPUT
-- ============================================================

CREATE TABLE crc_input (
    "ID_CAMPAGNE" TEXT NOT NULL,
    "Radical_compte" TEXT NOT NULL,

    "Numero_Tel" TEXT,
    "Mail" TEXT,

    date_creation_campagne TEXT,
    date_last_action TEXT,

    "ID_Action" TEXT,
    "Canal" TEXT,
    "Action" TEXT,

    "Etat_campagne" TEXT,

    statut_avant_campagne TEXT,
    statut_actuel TEXT,

    PRIMARY KEY ("ID_CAMPAGNE", "Radical_compte")
);


-- ============================================================
-- 8. VERS CC
-- ============================================================

CREATE TABLE vers_cc (
    "ID_CAMPAGNE" TEXT NOT NULL,
    "Radical_compte" TEXT NOT NULL,

    "Numero_Tel" TEXT,
    "Mail" TEXT,

    date_creation_campagne TEXT,
    date_last_action TEXT,

    "ID_Action" TEXT,
    "Canal" TEXT,
    "Action" TEXT,

    "Etat_campagne" TEXT,

    statut_avant_campagne TEXT,
    statut_actuel TEXT,

    PRIMARY KEY ("ID_CAMPAGNE", "Radical_compte")
);


-- ============================================================
-- 9. VERS DA
-- ============================================================

CREATE TABLE vers_da (
    "ID_CAMPAGNE" TEXT NOT NULL,
    "Radical_compte" TEXT NOT NULL,

    "Numero_Tel" TEXT,
    "Mail" TEXT,

    date_creation_campagne TEXT,
    date_last_action TEXT,

    "ID_Action" TEXT,
    "Canal" TEXT,
    "Action" TEXT,

    "Etat_campagne" TEXT,

    statut_avant_campagne TEXT,
    statut_actuel TEXT,

    PRIMARY KEY ("ID_CAMPAGNE", "Radical_compte")
);


-- ============================================================
-- 10. VERS CC TERRAIN
-- ============================================================

CREATE TABLE vers_cc_terrain (
    "ID_CAMPAGNE" TEXT NOT NULL,
    "Radical_compte" TEXT NOT NULL,

    "Numero_Tel" TEXT,
    "Mail" TEXT,

    date_creation_campagne TEXT,
    date_last_action TEXT,

    "ID_Action" TEXT,
    "Canal" TEXT,
    "Action" TEXT,

    "Etat_campagne" TEXT,

    statut_avant_campagne TEXT,
    statut_actuel TEXT,

    PRIMARY KEY ("ID_CAMPAGNE", "Radical_compte")
);


-- ============================================================
-- 11. VERS DA TERRAIN
-- ============================================================

CREATE TABLE vers_da_terrain (
    "ID_CAMPAGNE" TEXT NOT NULL,
    "Radical_compte" TEXT NOT NULL,

    "Numero_Tel" TEXT,
    "Mail" TEXT,

    date_creation_campagne TEXT,
    date_last_action TEXT,

    "ID_Action" TEXT,
    "Canal" TEXT,
    "Action" TEXT,

    "Etat_campagne" TEXT,

    statut_avant_campagne TEXT,
    statut_actuel TEXT,

    PRIMARY KEY ("ID_CAMPAGNE", "Radical_compte")
);


-- ============================================================
-- 12. TRAITEMENT MAIL
-- ============================================================

CREATE TABLE traitement_mail (
    id_campagne TEXT NOT NULL,
    radical_compte TEXT NOT NULL,

    nom TEXT,
    prenom TEXT,
    mail TEXT,

    colonne TEXT,
    objectif TEXT,
    statut_actuel TEXT,

    PRIMARY KEY (id_campagne, radical_compte)
);

CREATE INDEX idx_traitement_mail_camp
    ON traitement_mail (id_campagne);

CREATE INDEX idx_traitement_mail_rc
    ON traitement_mail (radical_compte);


-- ============================================================
-- 13. ACTION VERS CC
-- ============================================================

CREATE TABLE action_vers_cc (
    id_campagne TEXT NOT NULL,
    radical_compte TEXT NOT NULL,

    date_affectation TEXT,
    nb_jour_affecte INTEGER,

    nom TEXT,
    prenom TEXT,
    numero_tel TEXT,

    region TEXT,
    agence TEXT,
    gestionnaire TEXT,

    colonne TEXT,
    objectif TEXT,
    statut_actuel TEXT,

    PRIMARY KEY (id_campagne, radical_compte)
);


-- ============================================================
-- 14. ACTION VERS DA
-- ============================================================

CREATE TABLE action_vers_da (
    id_campagne TEXT NOT NULL,
    radical_compte TEXT NOT NULL,

    date_affectation TEXT,
    nb_jour_affecte INTEGER,

    nom TEXT,
    prenom TEXT,
    numero_tel TEXT,

    region TEXT,
    agence TEXT,
    gestionnaire TEXT,

    colonne TEXT,
    objectif TEXT,
    statut_actuel TEXT,

    PRIMARY KEY (id_campagne, radical_compte)
);


-- ============================================================
-- 15. TERRAIN LOGS
-- ============================================================

CREATE TABLE terrain_logs (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    id_campagne TEXT,
    radical_compte TEXT,

    queue TEXT,
    action TEXT,
    resultat TEXT,
    source TEXT,

    date_event TEXT
);


-- ============================================================
-- 16. EXTERNAL VISIT DISPATCHES
-- ============================================================

CREATE TABLE external_visit_dispatches (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    id_campagne TEXT NOT NULL,
    radical_compte TEXT NOT NULL,
    block_id TEXT NOT NULL,

    queue TEXT,
    payload_json TEXT,

    status TEXT NOT NULL DEFAULT 'sent',
    error TEXT,
    sent_at TEXT,

    UNIQUE (id_campagne, radical_compte, block_id)
);


COMMIT;