BEGIN;

-- ============================================================
-- Engagement digital + créneau de connexion - MVP
--
-- - Deux valeurs courantes dans clients pour ciblage/objectif.
-- - Datamart mensuel de variables (max 15 mois/client côté moteur).
-- - Historique des scores mensuels.
-- ============================================================

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS "Engagement_digital" TEXT NOT NULL DEFAULT 'non_score';

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS "Creneau_connexion" TEXT NOT NULL DEFAULT 'non_score';

UPDATE clients
SET "Engagement_digital" = 'non_score'
WHERE "Engagement_digital" IS NULL
   OR "Engagement_digital" NOT IN ('Faible', 'Modere', 'Eleve', 'non_score');

UPDATE clients
SET "Creneau_connexion" = 'non_score'
WHERE "Creneau_connexion" IS NULL
   OR "Creneau_connexion" NOT IN ('Matin', 'Apres-midi', 'Soir', 'non_score');

ALTER TABLE clients
    DROP CONSTRAINT IF EXISTS ck_clients_engagement_digital_values;
ALTER TABLE clients
    ADD CONSTRAINT ck_clients_engagement_digital_values
    CHECK ("Engagement_digital" IN ('Faible', 'Modere', 'Eleve', 'non_score'));

ALTER TABLE clients
    DROP CONSTRAINT IF EXISTS ck_clients_creneau_connexion_values;
ALTER TABLE clients
    ADD CONSTRAINT ck_clients_creneau_connexion_values
    CHECK ("Creneau_connexion" IN ('Matin', 'Apres-midi', 'Soir', 'non_score'));

CREATE INDEX IF NOT EXISTS idx_clients_engagement_digital
    ON clients ("Engagement_digital");
CREATE INDEX IF NOT EXISTS idx_clients_creneau_connexion
    ON clients ("Creneau_connexion");


-- Créneau choisi dans les blocs de modèle. Il est propagé vers la ligne
-- clients_campagnes afin que les dispatchers puissent l'appliquer.
ALTER TABLE clients_campagnes
    ADD COLUMN IF NOT EXISTS "Creneau" TEXT NOT NULL DEFAULT 'Indifferent';

UPDATE clients_campagnes
SET "Creneau" = 'Indifferent'
WHERE "Creneau" IS NULL
   OR "Creneau" NOT IN ('Indifferent', 'Matin', 'Apres-midi', 'Soir');

ALTER TABLE clients_campagnes
    DROP CONSTRAINT IF EXISTS ck_clients_campagnes_creneau;
ALTER TABLE clients_campagnes
    ADD CONSTRAINT ck_clients_campagnes_creneau
    CHECK ("Creneau" IN ('Indifferent', 'Matin', 'Apres-midi', 'Soir'));

CREATE OR REPLACE FUNCTION marketing_message_available_at(
    p_creneau TEXT,
    p_now TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TIMESTAMPTZ
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    local_now TIMESTAMP;
    target_local TIMESTAMP;
    slot TEXT;
    h INTEGER;
BEGIN
    slot := LOWER(BTRIM(COALESCE(p_creneau, 'Indifferent')));
    IF slot = '' OR slot = 'indifferent' THEN
        RETURN p_now;
    END IF;

    local_now := p_now AT TIME ZONE 'Africa/Casablanca';
    h := EXTRACT(HOUR FROM local_now)::INTEGER;

    IF slot = 'matin' THEN
        IF h >= 5 AND h < 12 THEN
            RETURN p_now;
        ELSIF h < 5 THEN
            target_local := date_trunc('day', local_now) + INTERVAL '5 hours';
        ELSE
            target_local := date_trunc('day', local_now) + INTERVAL '1 day 5 hours';
        END IF;
    ELSIF slot IN ('apres-midi', 'après-midi') THEN
        IF h >= 12 AND h < 18 THEN
            RETURN p_now;
        ELSIF h < 12 THEN
            target_local := date_trunc('day', local_now) + INTERVAL '12 hours';
        ELSE
            target_local := date_trunc('day', local_now) + INTERVAL '1 day 12 hours';
        END IF;
    ELSIF slot = 'soir' THEN
        IF h >= 18 OR h < 5 THEN
            RETURN p_now;
        ELSE
            target_local := date_trunc('day', local_now) + INTERVAL '18 hours';
        END IF;
    ELSE
        RETURN p_now;
    END IF;

    RETURN target_local AT TIME ZONE 'Africa/Casablanca';
END;
$$;

ALTER TABLE cibles
    ADD COLUMN IF NOT EXISTS pct_engagement_digital_eleve DOUBLE PRECISION;

ALTER TABLE cibles
    DROP CONSTRAINT IF EXISTS ck_cibles_pct_engagement_digital_eleve;
ALTER TABLE cibles
    ADD CONSTRAINT ck_cibles_pct_engagement_digital_eleve
    CHECK (
        pct_engagement_digital_eleve IS NULL
        OR (pct_engagement_digital_eleve >= 0 AND pct_engagement_digital_eleve <= 100)
    );

CREATE TABLE IF NOT EXISTS dm_engagement_digital_variables (
    radical_compte TEXT NOT NULL,
    annee_mois INTEGER NOT NULL,
    statut_client_snapshot TEXT,
    region TEXT,

    nb_connexions_mois INTEGER NOT NULL DEFAULT 0,
    moyenne_connexions_jour DOUBLE PRECISION NOT NULL DEFAULT 0,
    heure_moyenne_ponderee DOUBLE PRECISION,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (radical_compte, annee_mois),

    CONSTRAINT ck_dm_engagement_variables_annee_mois
        CHECK (
            annee_mois BETWEEN 190001 AND 299912
            AND (annee_mois % 100) BETWEEN 1 AND 12
        ),
    CONSTRAINT ck_dm_engagement_variables_nb_connexions
        CHECK (nb_connexions_mois >= 0),
    CONSTRAINT ck_dm_engagement_variables_moyenne
        CHECK (moyenne_connexions_jour >= 0),
    CONSTRAINT ck_dm_engagement_variables_heure
        CHECK (
            heure_moyenne_ponderee IS NULL
            OR (heure_moyenne_ponderee >= 0 AND heure_moyenne_ponderee < 24)
        )
);

CREATE INDEX IF NOT EXISTS idx_dm_engagement_variables_periode
    ON dm_engagement_digital_variables (annee_mois);
CREATE INDEX IF NOT EXISTS idx_dm_engagement_variables_client_periode_desc
    ON dm_engagement_digital_variables (radical_compte, annee_mois DESC);
CREATE INDEX IF NOT EXISTS idx_dm_engagement_variables_region_periode
    ON dm_engagement_digital_variables (region, annee_mois);

CREATE TABLE IF NOT EXISTS dm_engagement_digital_resultats (
    radical_compte TEXT NOT NULL,
    annee_mois INTEGER NOT NULL,
    date_calcul DATE NOT NULL DEFAULT CURRENT_DATE,
    statut_client_snapshot TEXT,
    region TEXT,

    nb_connexions_mois INTEGER NOT NULL DEFAULT 0,
    moyenne_connexions_jour DOUBLE PRECISION NOT NULL DEFAULT 0,
    mediane_connexions_jour DOUBLE PRECISION NOT NULL DEFAULT 0,

    engagement_digital TEXT NOT NULL,
    heure_moyenne_ponderee DOUBLE PRECISION,
    creneau_connexion TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (radical_compte, annee_mois),

    CONSTRAINT ck_dm_engagement_resultats_annee_mois
        CHECK (
            annee_mois BETWEEN 190001 AND 299912
            AND (annee_mois % 100) BETWEEN 1 AND 12
        ),
    CONSTRAINT ck_dm_engagement_resultats_engagement
        CHECK (engagement_digital IN ('Faible', 'Modere', 'Eleve')),
    CONSTRAINT ck_dm_engagement_resultats_creneau
        CHECK (creneau_connexion IN ('Matin', 'Apres-midi', 'Soir', 'non_score')),
    CONSTRAINT ck_dm_engagement_resultats_moyenne
        CHECK (moyenne_connexions_jour >= 0),
    CONSTRAINT ck_dm_engagement_resultats_mediane
        CHECK (mediane_connexions_jour >= 0)
);

CREATE INDEX IF NOT EXISTS idx_dm_engagement_resultats_periode_engagement
    ON dm_engagement_digital_resultats (annee_mois, engagement_digital);
CREATE INDEX IF NOT EXISTS idx_dm_engagement_resultats_periode_creneau
    ON dm_engagement_digital_resultats (annee_mois, creneau_connexion);
CREATE INDEX IF NOT EXISTS idx_dm_engagement_resultats_region_periode
    ON dm_engagement_digital_resultats (region, annee_mois);

COMMIT;
