BEGIN;

-- ============================================================
-- Création client O(1) : remplace MAX()+regex sur 500k+ lignes.
-- ============================================================
CREATE SEQUENCE IF NOT EXISTS client_radical_seq START WITH 1 INCREMENT BY 1;

DO $$
DECLARE
    current_seq BIGINT;
    max_rc BIGINT;
BEGIN
    SELECT last_value INTO current_seq FROM client_radical_seq;

    SELECT COALESCE(MAX(CAST(SUBSTRING(radical_compte FROM 3) AS BIGINT)), 0)
      INTO max_rc
    FROM clients
    WHERE radical_compte ~ '^RC[0-9]+$';

    IF max_rc >= current_seq THEN
        PERFORM setval('client_radical_seq', max_rc, true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_clients_id_client
    ON clients ("ID_Client");

-- ============================================================
-- Queue terrain asynchrone et retry.
-- ============================================================
ALTER TABLE external_visit_dispatches
    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_attempt_at TEXT,
    ADD COLUMN IF NOT EXISTS last_attempt_at TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TEXT;

CREATE INDEX IF NOT EXISTS idx_external_visit_dispatch_status_retry
    ON external_visit_dispatches (status, next_attempt_at, id);

CREATE INDEX IF NOT EXISTS idx_external_visit_dispatch_campaign_status
    ON external_visit_dispatches (id_campagne, status);

-- ============================================================
-- Batch : accès rapides aux lignes actives par action/bloc.
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_cc_active_campaign_block
    ON clients_campagnes ("ID_CAMPAGNE", "Etat_campagne", conversion, "ID_Action");

COMMIT;
