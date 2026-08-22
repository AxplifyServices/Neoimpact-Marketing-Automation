BEGIN;

-- ============================================================
-- Appétences produits / Next Best Product
-- ============================================================

ALTER TABLE clients ADD COLUMN IF NOT EXISTS "Appetence_carte" DOUBLE PRECISION;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS "Carte_recommandee" TEXT NOT NULL DEFAULT 'non_score';
ALTER TABLE clients ADD COLUMN IF NOT EXISTS "Appetence_conso" DOUBLE PRECISION;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS "Appetence_immo" DOUBLE PRECISION;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS "Appetence_epargne" DOUBLE PRECISION;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS "Next_best_product" TEXT NOT NULL DEFAULT 'non_score';
ALTER TABLE clients ADD COLUMN IF NOT EXISTS "Next_best_product_score" DOUBLE PRECISION;

ALTER TABLE clients DROP CONSTRAINT IF EXISTS ck_clients_appetence_carte;
ALTER TABLE clients ADD CONSTRAINT ck_clients_appetence_carte CHECK ("Appetence_carte" IS NULL OR "Appetence_carte" BETWEEN 0 AND 1);
ALTER TABLE clients DROP CONSTRAINT IF EXISTS ck_clients_appetence_conso;
ALTER TABLE clients ADD CONSTRAINT ck_clients_appetence_conso CHECK ("Appetence_conso" IS NULL OR "Appetence_conso" BETWEEN 0 AND 1);
ALTER TABLE clients DROP CONSTRAINT IF EXISTS ck_clients_appetence_immo;
ALTER TABLE clients ADD CONSTRAINT ck_clients_appetence_immo CHECK ("Appetence_immo" IS NULL OR "Appetence_immo" BETWEEN 0 AND 1);
ALTER TABLE clients DROP CONSTRAINT IF EXISTS ck_clients_appetence_epargne;
ALTER TABLE clients ADD CONSTRAINT ck_clients_appetence_epargne CHECK ("Appetence_epargne" IS NULL OR "Appetence_epargne" BETWEEN 0 AND 1);
ALTER TABLE clients DROP CONSTRAINT IF EXISTS ck_clients_nbp_score;
ALTER TABLE clients ADD CONSTRAINT ck_clients_nbp_score CHECK ("Next_best_product_score" IS NULL OR "Next_best_product_score" BETWEEN 0 AND 1);
ALTER TABLE clients DROP CONSTRAINT IF EXISTS ck_clients_carte_recommandee;
ALTER TABLE clients ADD CONSTRAINT ck_clients_carte_recommandee CHECK ("Carte_recommandee" IN ('Silver','Titanium','Platinium','Infinite','non_score'));
ALTER TABLE clients DROP CONSTRAINT IF EXISTS ck_clients_nbp;
ALTER TABLE clients ADD CONSTRAINT ck_clients_nbp CHECK ("Next_best_product" IN ('Carte','Credit conso','Credit immo','Epargne','non_score'));

CREATE INDEX IF NOT EXISTS idx_clients_appetence_carte ON clients ("Appetence_carte");
CREATE INDEX IF NOT EXISTS idx_clients_appetence_conso ON clients ("Appetence_conso");
CREATE INDEX IF NOT EXISTS idx_clients_appetence_immo ON clients ("Appetence_immo");
CREATE INDEX IF NOT EXISTS idx_clients_appetence_epargne ON clients ("Appetence_epargne");
CREATE INDEX IF NOT EXISTS idx_clients_nbp ON clients ("Next_best_product");

-- Une ligne mensuelle utilisée pour l'entraînement. Les mois fake sont un
-- bootstrap MVP uniquement ; les mois réels sont alimentés progressivement.
CREATE TABLE IF NOT EXISTS dm_product_training_monthly (
    radical_compte TEXT NOT NULL,
    annee_mois INTEGER NOT NULL,
    observed_on DATE NOT NULL,
    source TEXT NOT NULL DEFAULT 'real',

    statut_client TEXT,
    age INTEGER,
    region TEXT,
    segment TEXT,
    qualite TEXT,

    nb_transaction DOUBLE PRECISION NOT NULL DEFAULT 0,
    vol_transaction DOUBLE PRECISION NOT NULL DEFAULT 0,
    nb_retrait_gab DOUBLE PRECISION NOT NULL DEFAULT 0,
    vol_retrait_gab DOUBLE PRECISION NOT NULL DEFAULT 0,
    nb_transaction_ecom DOUBLE PRECISION NOT NULL DEFAULT 0,
    vol_transaction_ecom DOUBLE PRECISION NOT NULL DEFAULT 0,
    nb_virement DOUBLE PRECISION NOT NULL DEFAULT 0,
    vol_virement DOUBLE PRECISION NOT NULL DEFAULT 0,
    solde_moyen_depots DOUBLE PRECISION NOT NULL DEFAULT 0,
    encours_global DOUBLE PRECISION NOT NULL DEFAULT 0,
    encours_conso DOUBLE PRECISION NOT NULL DEFAULT 0,
    encours_immo DOUBLE PRECISION NOT NULL DEFAULT 0,
    montant_revenu DOUBLE PRECISION NOT NULL DEFAULT 0,
    app_installed INTEGER NOT NULL DEFAULT 0,
    premiere_connex INTEGER NOT NULL DEFAULT 0,

    carte_actuelle TEXT,
    card_rank INTEGER NOT NULL DEFAULT 0,
    epargne_active INTEGER NOT NULL DEFAULT 0,
    credit_conso_state TEXT NOT NULL DEFAULT 'never',
    credit_immo_state TEXT NOT NULL DEFAULT 'never',

    delta_transactions DOUBLE PRECISION NOT NULL DEFAULT 0,
    delta_depots DOUBLE PRECISION NOT NULL DEFAULT 0,
    delta_revenu DOUBLE PRECISION NOT NULL DEFAULT 0,
    delta_encours_conso DOUBLE PRECISION NOT NULL DEFAULT 0,
    delta_encours_immo DOUBLE PRECISION NOT NULL DEFAULT 0,

    feedback_carte_contacts_12m INTEGER NOT NULL DEFAULT 0,
    feedback_carte_conversions_12m INTEGER NOT NULL DEFAULT 0,
    feedback_conso_contacts_12m INTEGER NOT NULL DEFAULT 0,
    feedback_conso_conversions_12m INTEGER NOT NULL DEFAULT 0,
    feedback_immo_contacts_12m INTEGER NOT NULL DEFAULT 0,
    feedback_immo_conversions_12m INTEGER NOT NULL DEFAULT 0,
    feedback_epargne_contacts_12m INTEGER NOT NULL DEFAULT 0,
    feedback_epargne_conversions_12m INTEGER NOT NULL DEFAULT 0,

    target_card_silver INTEGER,
    target_card_titanium INTEGER,
    target_card_platinium INTEGER,
    target_card_infinite INTEGER,
    target_conso INTEGER,
    target_immo INTEGER,
    target_epargne INTEGER,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (radical_compte, annee_mois)
);
CREATE INDEX IF NOT EXISTS idx_product_training_month_source ON dm_product_training_monthly (annee_mois, source);
CREATE INDEX IF NOT EXISTS idx_product_training_credit_states ON dm_product_training_monthly (annee_mois, credit_conso_state, credit_immo_state);

-- Historique officiel des scores : une ligne par client et par mois.
CREATE TABLE IF NOT EXISTS dm_product_scores (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    radical_compte TEXT NOT NULL,
    date_scoring DATE NOT NULL,
    annee_mois INTEGER NOT NULL,
    statut_client_snapshot TEXT,
    region TEXT,

    score_card_silver DOUBLE PRECISION,
    score_card_titanium DOUBLE PRECISION,
    score_card_platinium DOUBLE PRECISION,
    score_card_infinite DOUBLE PRECISION,
    card_eligible_silver BOOLEAN NOT NULL DEFAULT FALSE,
    card_eligible_titanium BOOLEAN NOT NULL DEFAULT FALSE,
    card_eligible_platinium BOOLEAN NOT NULL DEFAULT FALSE,
    card_eligible_infinite BOOLEAN NOT NULL DEFAULT FALSE,
    appetence_carte DOUBLE PRECISION,
    carte_recommandee TEXT NOT NULL DEFAULT 'non_score',

    appetence_conso DOUBLE PRECISION,
    conso_model_segment TEXT,
    appetence_immo DOUBLE PRECISION,
    immo_model_segment TEXT,
    appetence_epargne DOUBLE PRECISION,

    next_best_product TEXT NOT NULL DEFAULT 'non_score',
    next_best_product_score DOUBLE PRECISION,

    model_version_cards TEXT,
    model_version_conso TEXT,
    model_version_immo TEXT,
    model_version_epargne TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_product_scores_client_month UNIQUE (radical_compte, annee_mois),
    CONSTRAINT ck_product_scores_card CHECK (appetence_carte IS NULL OR appetence_carte BETWEEN 0 AND 1),
    CONSTRAINT ck_product_scores_conso CHECK (appetence_conso IS NULL OR appetence_conso BETWEEN 0 AND 1),
    CONSTRAINT ck_product_scores_immo CHECK (appetence_immo IS NULL OR appetence_immo BETWEEN 0 AND 1),
    CONSTRAINT ck_product_scores_epargne CHECK (appetence_epargne IS NULL OR appetence_epargne BETWEEN 0 AND 1),
    CONSTRAINT ck_product_scores_nbp CHECK (next_best_product_score IS NULL OR next_best_product_score BETWEEN 0 AND 1)
);
CREATE INDEX IF NOT EXISTS idx_product_scores_month ON dm_product_scores (annee_mois, next_best_product);
CREATE INDEX IF NOT EXISTS idx_product_scores_client ON dm_product_scores (radical_compte, annee_mois DESC);
CREATE INDEX IF NOT EXISTS idx_product_scores_region ON dm_product_scores (annee_mois, region, next_best_product);

-- Lien score au lancement d'une campagne -> résultat de l'objectif.
CREATE TABLE IF NOT EXISTS dm_product_campaign_feedback (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    score_id BIGINT REFERENCES dm_product_scores(id) ON DELETE SET NULL,
    id_campagne TEXT NOT NULL,
    id_modele TEXT,
    radical_compte TEXT NOT NULL,
    product_code TEXT NOT NULL,
    objective_id_action TEXT NOT NULL DEFAULT '',
    score_at_launch DOUBLE PRECISION,
    appetent_at_launch BOOLEAN NOT NULL DEFAULT FALSE,
    next_best_product_at_launch TEXT,
    campaign_assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    was_contacted BOOLEAN NOT NULL DEFAULT FALSE,
    contacted_at TIMESTAMPTZ,
    objective_achieved SMALLINT,
    objective_result_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_product_feedback_product CHECK (product_code IN ('card','conso','immo','epargne')),
    CONSTRAINT ck_product_feedback_result CHECK (objective_achieved IS NULL OR objective_achieved IN (0,1)),
    CONSTRAINT uq_product_feedback_campaign_client_objective UNIQUE (id_campagne, radical_compte, product_code, objective_id_action)
);
CREATE INDEX IF NOT EXISTS idx_product_feedback_client_product ON dm_product_campaign_feedback (radical_compte, product_code, campaign_assigned_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_feedback_campaign ON dm_product_campaign_feedback (id_campagne, product_code, objective_achieved);
CREATE INDEX IF NOT EXISTS idx_product_feedback_score ON dm_product_campaign_feedback (score_id);

COMMIT;
