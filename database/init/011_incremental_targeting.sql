-- ============================================================
-- 011 - Targeting incrémental
-- PostgreSQL 17
--
-- Objectifs :
-- - ne plus rescanner toute la table clients pour chaque campagne à chaque batch ;
-- - garder uniquement la dernière version de changement par client ;
-- - suivre un watermark indépendant par campagne ;
-- - capter aussi les changements de conversion utilisés par les filtres objectifs ;
-- - conserver un rescan complet unique pour les campagnes historiques ou après
--   modification d'une définition de cible.
-- ============================================================

CREATE SEQUENCE IF NOT EXISTS targeting_change_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE IF NOT EXISTS targeting_client_changes (
    radical_compte TEXT PRIMARY KEY,
    change_seq BIGINT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'client'
);

CREATE TABLE IF NOT EXISTS campaign_target_sync_state (
    id_campagne TEXT PRIMARY KEY REFERENCES campagnes(id_campagne) ON DELETE CASCADE,
    initialized BOOLEAN NOT NULL DEFAULT FALSE,
    watermark BIGINT NOT NULL DEFAULT 0,
    last_sync_at TIMESTAMPTZ,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO campaign_target_sync_state (id_campagne)
SELECT id_campagne
FROM campagnes
ON CONFLICT (id_campagne) DO NOTHING;

-- Capture set-based des INSERT/UPDATE de la table clients. Les transition
-- tables évitent un appel PL/pgSQL par ligne lors d'un import de plusieurs
-- millions de clients.
CREATE OR REPLACE FUNCTION neoimpact_capture_clients_target_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM campagnes
        WHERE etat_campagne IN ('En cours','En pause','Planifiée')
          AND COALESCE(execution_status, 'ready') NOT IN ('failed','cancelled')
    ) THEN
        RETURN NULL;
    END IF;

    INSERT INTO targeting_client_changes (
        radical_compte, change_seq, changed_at, source
    )
    SELECT
        BTRIM(n.radical_compte::text),
        nextval('targeting_change_seq'),
        NOW(),
        'client'
    FROM new_rows AS n
    WHERE BTRIM(COALESCE(n.radical_compte::text, '')) <> ''
    ON CONFLICT (radical_compte)
    DO UPDATE SET
        change_seq = EXCLUDED.change_seq,
        changed_at = EXCLUDED.changed_at,
        source = EXCLUDED.source;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_clients_target_changes_insert ON clients;
CREATE TRIGGER trg_clients_target_changes_insert
AFTER INSERT ON clients
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION neoimpact_capture_clients_target_changes();

DROP TRIGGER IF EXISTS trg_clients_target_changes_update ON clients;
CREATE TRIGGER trg_clients_target_changes_update
AFTER UPDATE ON clients
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION neoimpact_capture_clients_target_changes();

-- Certaines cibles utilisent l'atteinte d'un objectif d'une autre campagne.
-- Une conversion est donc un changement de ciblage même si la fiche client n'a
-- pas changé. Ici le trigger ligne-à-ligne est volontaire : les conversions
-- sont des événements ponctuels, contrairement aux imports clients massifs.
CREATE OR REPLACE FUNCTION neoimpact_capture_conversion_target_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_radical TEXT;
    v_seq BIGINT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF COALESCE(NEW.conversion, 0) <> 1 THEN
            RETURN NEW;
        END IF;
        v_radical := BTRIM(COALESCE(NEW."Radical_compte"::text, ''));
    ELSE
        IF OLD.conversion IS NOT DISTINCT FROM NEW.conversion THEN
            RETURN NEW;
        END IF;
        v_radical := BTRIM(COALESCE(NEW."Radical_compte"::text, ''));
    END IF;

    IF v_radical = '' OR NOT EXISTS (
        SELECT 1
        FROM campagnes
        WHERE etat_campagne IN ('En cours','En pause','Planifiée')
          AND COALESCE(execution_status, 'ready') NOT IN ('failed','cancelled')
    ) THEN
        RETURN NEW;
    END IF;

    v_seq := nextval('targeting_change_seq');
    INSERT INTO targeting_client_changes (
        radical_compte, change_seq, changed_at, source
    ) VALUES (
        v_radical, v_seq, NOW(), 'conversion'
    )
    ON CONFLICT (radical_compte)
    DO UPDATE SET
        change_seq = EXCLUDED.change_seq,
        changed_at = EXCLUDED.changed_at,
        source = EXCLUDED.source;

    RETURN NEW;
END;
$$;

-- Pas de trigger INSERT : les nouvelles lignes de campagne démarrent à
-- conversion=0. Cela évite un coût row-level inutile lors du peuplement de
-- plusieurs millions de clients. Le passage ultérieur à conversion=1 est
-- capté par le trigger UPDATE ci-dessous.
DROP TRIGGER IF EXISTS trg_clients_campagnes_target_conversion_insert ON clients_campagnes;

DROP TRIGGER IF EXISTS trg_clients_campagnes_target_conversion_update ON clients_campagnes;
CREATE TRIGGER trg_clients_campagnes_target_conversion_update
AFTER UPDATE OF conversion ON clients_campagnes
FOR EACH ROW
EXECUTE FUNCTION neoimpact_capture_conversion_target_change();

-- Une modification réelle des critères de cible rend le watermark précédent
-- invalide : un rescan complet unique sera effectué au prochain passage.
CREATE OR REPLACE FUNCTION neoimpact_invalidate_target_sync_on_cible_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.filtre IS NOT DISTINCT FROM NEW.filtre
       AND OLD.source IS NOT DISTINCT FROM NEW.source
       AND OLD.chemin IS NOT DISTINCT FROM NEW.chemin
       AND OLD.data_source_code IS NOT DISTINCT FROM NEW.data_source_code THEN
        RETURN NEW;
    END IF;

    INSERT INTO campaign_target_sync_state (
        id_campagne, initialized, watermark, last_error, updated_at
    )
    SELECT c.id_campagne, FALSE, 0, NULL, NOW()
    FROM campagnes AS c
    WHERE c.id_cible = NEW.id_cible
      AND c.etat_campagne IN ('En cours','En pause','Planifiée')
    ON CONFLICT (id_campagne)
    DO UPDATE SET
        initialized = FALSE,
        watermark = 0,
        last_error = NULL,
        updated_at = NOW();

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_cibles_invalidate_target_sync ON cibles;
CREATE TRIGGER trg_cibles_invalidate_target_sync
AFTER UPDATE OF filtre, source, chemin, data_source_code ON cibles
FOR EACH ROW
EXECUTE FUNCTION neoimpact_invalidate_target_sync_on_cible_change();

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_targeting_client_changes_seq
    ON targeting_client_changes (change_seq, radical_compte);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_campaign_target_sync_watermark
    ON campaign_target_sync_state (initialized, watermark, id_campagne);

ANALYZE targeting_client_changes;
ANALYZE campaign_target_sync_state;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_campagnes_cible_target_sync
    ON campagnes (id_cible, etat_campagne, execution_status, id_campagne);

ANALYZE campagnes;
