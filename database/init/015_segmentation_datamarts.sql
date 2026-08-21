BEGIN;

-- ============================================================
-- Segmentation client - MVP
--
-- Deux tables :
-- 1) dm_segmentation_variables : profondeur glissante de 15 mois.
-- 2) dm_segmentation_resultats : historique des segmentations.
--
-- radical_compte reste l'identifiant client canonique : aucune nouvelle
-- clé client n'est introduite.
-- ============================================================

CREATE TABLE IF NOT EXISTS dm_segmentation_variables (
    radical_compte TEXT NOT NULL,
    annee_mois INTEGER NOT NULL,

    -- Variables mensuelles brutes attendues par le code historique.
    flux_crediteur_m DOUBLE PRECISION NOT NULL DEFAULT 0,
    moyenne_10pc_plus_petits DOUBLE PRECISION NOT NULL DEFAULT 0,
    encours_m_moyen DOUBLE PRECISION NOT NULL DEFAULT 0,

    -- Ancienneté au mois observé. Cette valeur est utilisée pour la fenêtre
    -- de détection salarié/non-salarié et pour l'éligibilité >= 3 mois.
    anciennete_mois INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (radical_compte, annee_mois),

    CONSTRAINT ck_dm_segmentation_variables_annee_mois
        CHECK (
            annee_mois BETWEEN 190001 AND 299912
            AND (annee_mois % 100) BETWEEN 1 AND 12
        ),
    CONSTRAINT ck_dm_segmentation_variables_anciennete
        CHECK (anciennete_mois >= 0),
    CONSTRAINT ck_dm_segmentation_variables_flux
        CHECK (flux_crediteur_m >= 0),
    CONSTRAINT ck_dm_segmentation_variables_q10
        CHECK (moyenne_10pc_plus_petits >= 0),
    CONSTRAINT ck_dm_segmentation_variables_encours
        CHECK (encours_m_moyen >= 0)
);

CREATE INDEX IF NOT EXISTS idx_dm_segmentation_variables_periode
    ON dm_segmentation_variables (annee_mois);

CREATE INDEX IF NOT EXISTS idx_dm_segmentation_variables_client_periode_desc
    ON dm_segmentation_variables (radical_compte, annee_mois DESC);


CREATE TABLE IF NOT EXISTS dm_segmentation_resultats (
    radical_compte TEXT NOT NULL,
    annee_mois INTEGER NOT NULL,
    date_segmentation DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Photographie des variables clients utilisées au moment du calcul.
    age INTEGER,
    tranche_age TEXT,
    region TEXT,
    bp TEXT,
    anciennete_mois INTEGER,

    -- Diagnostic salarié / non-salarié repris du notebook historique.
    freq_prop DOUBLE PRECISION,
    meets_freq BOOLEAN,
    mean_trim_10_90 DOUBLE PRECISION,
    std_trim_10_90 DOUBLE PRECISION,
    ratio_std_over_mean DOUBLE PRECISION,
    meets_regularity BOOLEAN,
    statut_salarie TEXT,

    -- Variables lissées utilisées pour la segmentation.
    flux_crediteur_moy_3m DOUBLE PRECISION,
    moyenne_10pc_plus_petit_3m DOUBLE PRECISION,
    encours_m_moyen_3m DOUBLE PRECISION,
    encours_selon_statut DOUBLE PRECISION,

    -- Médianes de référence de la région / tranche d'âge du mois courant.
    mediane_flux DOUBLE PRECISION,
    mediane_avoirs DOUBLE PRECISION,

    -- Valeur métier finale : Mass Market / Medium / Haut de gamme /
    -- Premium / Banque privée / Non segmenté.
    segment TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (radical_compte, annee_mois),

    CONSTRAINT ck_dm_segmentation_resultats_annee_mois
        CHECK (
            annee_mois BETWEEN 190001 AND 299912
            AND (annee_mois % 100) BETWEEN 1 AND 12
        )
);

CREATE INDEX IF NOT EXISTS idx_dm_segmentation_resultats_last_client
    ON dm_segmentation_resultats (radical_compte, date_segmentation DESC);

CREATE INDEX IF NOT EXISTS idx_dm_segmentation_resultats_periode_segment
    ON dm_segmentation_resultats (annee_mois, segment);

CREATE INDEX IF NOT EXISTS idx_dm_segmentation_resultats_region_periode
    ON dm_segmentation_resultats (region, annee_mois);

COMMIT;
