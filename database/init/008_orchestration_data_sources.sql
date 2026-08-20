-- ============================================================
-- 008 - Orchestration-first / abstraction des sources de données
-- PostgreSQL 17
--
-- La plateforme conserve son PostgreSQL interne comme source par défaut,
-- mais une cible peut désormais référencer explicitement un datamart.
-- Les secrets de connexion ne sont JAMAIS stockés ici : secret_ref ne
-- contient que le nom d'un secret/variable d'environnement côté runtime.
-- ============================================================

CREATE TABLE IF NOT EXISTS data_sources (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    read_only       BOOLEAN NOT NULL DEFAULT TRUE,
    config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    secret_ref      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_data_sources_kind CHECK (
        kind IN ('INTERNAL_POSTGRES', 'EXTERNAL_POSTGRES')
    ),
    CONSTRAINT ck_data_sources_external_secret CHECK (
        kind = 'INTERNAL_POSTGRES'
        OR (secret_ref IS NOT NULL AND BTRIM(secret_ref) <> '')
    )
);

INSERT INTO data_sources (
    code,
    name,
    kind,
    enabled,
    read_only,
    config,
    secret_ref
)
VALUES (
    'internal',
    'PostgreSQL interne',
    'INTERNAL_POSTGRES',
    TRUE,
    FALSE,
    jsonb_build_object(
        'clients_schema', 'public',
        'clients_table', 'clients',
        'key_column', 'radical_compte',
        'rupture_status_column', 'STATUT_CLIENT'
    ),
    NULL
)
ON CONFLICT (code) DO NOTHING;

ALTER TABLE cibles
    ADD COLUMN IF NOT EXISTS data_source_code TEXT;

UPDATE cibles
SET data_source_code = 'internal'
WHERE data_source_code IS NULL OR BTRIM(data_source_code) = '';

ALTER TABLE cibles
    ALTER COLUMN data_source_code SET DEFAULT 'internal';

ALTER TABLE cibles
    ALTER COLUMN data_source_code SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_cibles_data_source'
    ) THEN
        ALTER TABLE cibles
            ADD CONSTRAINT fk_cibles_data_source
            FOREIGN KEY (data_source_code)
            REFERENCES data_sources(code)
            ON UPDATE CASCADE
            ON DELETE RESTRICT;
    END IF;
END $$;

ALTER TABLE campagnes
    ADD COLUMN IF NOT EXISTS data_source_code TEXT;

UPDATE campagnes AS cp
SET data_source_code = COALESCE(c.data_source_code, 'internal')
FROM cibles AS c
WHERE cp.id_cible = c.id_cible
  AND (cp.data_source_code IS NULL OR BTRIM(cp.data_source_code) = '');

UPDATE campagnes
SET data_source_code = 'internal'
WHERE data_source_code IS NULL OR BTRIM(data_source_code) = '';

ALTER TABLE campagnes
    ALTER COLUMN data_source_code SET DEFAULT 'internal';

ALTER TABLE campagnes
    ALTER COLUMN data_source_code SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_campagnes_data_source'
    ) THEN
        ALTER TABLE campagnes
            ADD CONSTRAINT fk_campagnes_data_source
            FOREIGN KEY (data_source_code)
            REFERENCES data_sources(code)
            ON UPDATE CASCADE
            ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_cibles_data_source_code
    ON cibles (data_source_code);

CREATE INDEX IF NOT EXISTS idx_campagnes_data_source_code
    ON campagnes (data_source_code);

ANALYZE data_sources;
ANALYZE cibles;
ANALYZE campagnes;

-- La matérialisation des cibles fichier est désormais un cache de clés local.
-- On garantit son nettoyage automatiquement à la suppression de la cible.
DELETE FROM clients_cibles AS cc
WHERE NOT EXISTS (
    SELECT 1 FROM cibles AS c WHERE c.id_cible = cc."ID_CIBLE"
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_clients_cibles_cible'
    ) THEN
        ALTER TABLE clients_cibles
            ADD CONSTRAINT fk_clients_cibles_cible
            FOREIGN KEY ("ID_CIBLE")
            REFERENCES cibles(id_cible)
            ON UPDATE CASCADE
            ON DELETE CASCADE;
    END IF;
END $$;
