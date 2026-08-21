BEGIN;

-- ============================================================
-- Attrition scoring - MVP
--
-- - Risque_attrition expose uniquement le dernier flag exploitable par
--   le moteur de ciblage.
-- - dm_attrition_variables historise les trois signaux financiers et
--   leurs variations relatives M1/M3/M6/M12.
-- - dm_attrition_scores historise tous les scorings mensuels.
-- ============================================================

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS "Risque_attrition" TEXT NOT NULL DEFAULT 'Non';

ALTER TABLE clients
    DROP CONSTRAINT IF EXISTS ck_clients_risque_attrition_values;

UPDATE clients
SET "Risque_attrition" = 'Non'
WHERE "Risque_attrition" IS NULL
   OR "Risque_attrition" NOT IN ('Oui', 'Non');

ALTER TABLE clients
    ADD CONSTRAINT ck_clients_risque_attrition_values
    CHECK ("Risque_attrition" IN ('Oui', 'Non'));

CREATE INDEX IF NOT EXISTS idx_clients_risque_attrition
    ON clients ("Risque_attrition");

CREATE TABLE IF NOT EXISTS dm_attrition_variables (
    radical_compte TEXT NOT NULL,
    annee_mois INTEGER NOT NULL,
    statut_client_snapshot TEXT,

    avoirs DOUBLE PRECISION NOT NULL DEFAULT 0,
    flux_crediteurs DOUBLE PRECISION NOT NULL DEFAULT 0,
    flux_debiteurs DOUBLE PRECISION NOT NULL DEFAULT 0,

    var_avoirs_1m DOUBLE PRECISION NOT NULL DEFAULT 0,
    var_avoirs_3m DOUBLE PRECISION NOT NULL DEFAULT 0,
    var_avoirs_6m DOUBLE PRECISION NOT NULL DEFAULT 0,
    var_avoirs_12m DOUBLE PRECISION NOT NULL DEFAULT 0,

    var_flux_crediteurs_1m DOUBLE PRECISION NOT NULL DEFAULT 0,
    var_flux_crediteurs_3m DOUBLE PRECISION NOT NULL DEFAULT 0,
    var_flux_crediteurs_6m DOUBLE PRECISION NOT NULL DEFAULT 0,
    var_flux_crediteurs_12m DOUBLE PRECISION NOT NULL DEFAULT 0,

    var_flux_debiteurs_1m DOUBLE PRECISION NOT NULL DEFAULT 0,
    var_flux_debiteurs_3m DOUBLE PRECISION NOT NULL DEFAULT 0,
    var_flux_debiteurs_6m DOUBLE PRECISION NOT NULL DEFAULT 0,
    var_flux_debiteurs_12m DOUBLE PRECISION NOT NULL DEFAULT 0,

    -- Cible du modèle : 1 = rupture observée ce mois, 0 = pas de rupture.
    attrition SMALLINT NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (radical_compte, annee_mois),
    CONSTRAINT ck_dm_attrition_variables_annee_mois
        CHECK (
            annee_mois BETWEEN 190001 AND 299912
            AND (annee_mois % 100) BETWEEN 1 AND 12
        ),
    CONSTRAINT ck_dm_attrition_variables_attrition
        CHECK (attrition IN (0, 1)),
    CONSTRAINT ck_dm_attrition_variables_avoirs
        CHECK (avoirs >= 0),
    CONSTRAINT ck_dm_attrition_variables_flux_crediteurs
        CHECK (flux_crediteurs >= 0),
    CONSTRAINT ck_dm_attrition_variables_flux_debiteurs
        CHECK (flux_debiteurs >= 0)
);

CREATE INDEX IF NOT EXISTS idx_dm_attrition_variables_periode
    ON dm_attrition_variables (annee_mois);

CREATE INDEX IF NOT EXISTS idx_dm_attrition_variables_target
    ON dm_attrition_variables (attrition, annee_mois);

CREATE INDEX IF NOT EXISTS idx_dm_attrition_variables_client_periode_desc
    ON dm_attrition_variables (radical_compte, annee_mois DESC);

CREATE TABLE IF NOT EXISTS dm_attrition_scores (
    radical_compte TEXT NOT NULL,
    annee_mois INTEGER NOT NULL,
    date_scoring DATE NOT NULL DEFAULT CURRENT_DATE,
    statut_client_snapshot TEXT,
    region TEXT,

    score_attrition DOUBLE PRECISION NOT NULL,
    risque_attrition TEXT NOT NULL,
    seuil_risque DOUBLE PRECISION NOT NULL,
    modele TEXT NOT NULL DEFAULT 'attrition_xgboost_v1',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (radical_compte, annee_mois),
    CONSTRAINT ck_dm_attrition_scores_annee_mois
        CHECK (
            annee_mois BETWEEN 190001 AND 299912
            AND (annee_mois % 100) BETWEEN 1 AND 12
        ),
    CONSTRAINT ck_dm_attrition_scores_score
        CHECK (score_attrition >= 0 AND score_attrition <= 1),
    CONSTRAINT ck_dm_attrition_scores_risque
        CHECK (risque_attrition IN ('Oui', 'Non')),
    CONSTRAINT ck_dm_attrition_scores_seuil
        CHECK (seuil_risque >= 0 AND seuil_risque <= 1)
);

CREATE INDEX IF NOT EXISTS idx_dm_attrition_scores_periode
    ON dm_attrition_scores (annee_mois);

CREATE INDEX IF NOT EXISTS idx_dm_attrition_scores_risque_periode
    ON dm_attrition_scores (risque_attrition, annee_mois);

CREATE INDEX IF NOT EXISTS idx_dm_attrition_scores_region_periode
    ON dm_attrition_scores (region, annee_mois);

COMMIT;
