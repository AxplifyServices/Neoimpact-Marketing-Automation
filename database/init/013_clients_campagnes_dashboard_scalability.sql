-- ============================================================
-- 013 - clients_campagnes + dashboard scalability
-- PostgreSQL 17
--
-- IMPORTANT : pas de BEGIN/COMMIT explicite : les index CONCURRENTLY doivent
-- pouvoir être créés sans verrou d'écriture long sur les grosses tables.
-- ============================================================

-- Etat propre à la relation client/campagne.
-- 0 = actif dans la campagne, 1 = neutralisé (ex. rupture de relation).
-- L'état global de la campagne reste exclusivement dans campagnes.etat_campagne.
ALTER TABLE clients_campagnes
    ADD COLUMN IF NOT EXISTS row_status SMALLINT NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'clients_campagnes_row_status_chk'
    ) THEN
        ALTER TABLE clients_campagnes
            ADD CONSTRAINT clients_campagnes_row_status_chk
            CHECK (row_status IN (0, 1)) NOT VALID;
    END IF;
END $$;

-- Backfill ciblé uniquement des anciennes lignes explicitement neutralisées.
UPDATE clients_campagnes
SET row_status = 1
WHERE row_status = 0
  AND (
      COALESCE("Etat_campagne", '') = 'Canceled'
      OR COALESCE("Action", '') = 'Canceled'
      OR COALESCE("Canal", '') = 'Canceled'
  );

ALTER TABLE clients_campagnes
    VALIDATE CONSTRAINT clients_campagnes_row_status_chk;

-- Parseur ISO immuable utilisé par le dashboard et ses index sans réécrire la
-- table pour ajouter deux colonnes DATE matérialisées.
CREATE OR REPLACE FUNCTION neoimpact_iso_date(value TEXT)
RETURNS DATE
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
RETURNS NULL ON NULL INPUT
AS $$
BEGIN
    IF value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN
        RETURN NULL;
    END IF;
    BEGIN
        RETURN make_date(
            substring(value FROM 1 FOR 4)::integer,
            substring(value FROM 6 FOR 2)::integer,
            substring(value FROM 9 FOR 2)::integer
        );
    EXCEPTION WHEN OTHERS THEN
        RETURN NULL;
    END;
END
$$;


-- Les moteurs travaillent par campagne et ne doivent plus dépendre d'une copie
-- de campagnes.etat_campagne sur des millions de lignes.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cc_active_campaign_id
    ON clients_campagnes ("ID_CAMPAGNE", id)
    WHERE row_status = 0;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cc_active_campaign_workflow
    ON clients_campagnes ("ID_CAMPAGNE", conversion, "Action", "ID_Action", id)
    INCLUDE ("Canal", "Radical_compte")
    WHERE row_status = 0;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cc_active_outbound
    ON clients_campagnes ("ID_CAMPAGNE", "Canal", "Action", conversion, id)
    INCLUDE ("ID_Action", "Radical_compte", action_execution_seq, outbound_enqueued_key)
    WHERE row_status = 0;

-- Accélère les filtres temporels du dashboard sans conversion TEXT->DATE sur
-- toutes les lignes à chaque affichage.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cc_dashboard_campaign_last_day
    ON clients_campagnes ("ID_CAMPAGNE", neoimpact_iso_date("Date_last_action"));

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cc_dashboard_campaign_conversion_day
    ON clients_campagnes ("ID_CAMPAGNE", neoimpact_iso_date(conversion_date))
    WHERE conversion = 1;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cc_dashboard_campaign_action
    ON clients_campagnes ("ID_CAMPAGNE", "ID_Action");

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cc_dashboard_campaign_conversion_action
    ON clients_campagnes ("ID_CAMPAGNE", conversion_id_action)
    WHERE conversion = 1;

-- Les anciennes colonnes Etat_campagne/Nom_campagne restent en place pour
-- compatibilité et historique ; elles ne sont plus une source de vérité active.
COMMENT ON COLUMN clients_campagnes."Etat_campagne" IS
    'Legacy snapshot. Etat global courant = campagnes.etat_campagne; row_status porte la neutralisation client.';
COMMENT ON COLUMN clients_campagnes."Nom_campagne" IS
    'Legacy snapshot. Nom courant = campagnes.nom_campagne.';
COMMENT ON COLUMN clients_campagnes.row_status IS
    '0=actif dans la campagne; 1=neutralisé au niveau client (ex. rupture de relation).';

-- Table très mutable : réserver un peu d'espace pour les HOT updates des
-- compteurs non indexés et déclencher VACUUM/ANALYZE bien avant que 10-20 %
-- d'une table de plusieurs dizaines de millions de lignes ne soient obsolètes.
-- Ces paramètres sont locaux à clients_campagnes et n'imposent aucun réglage
-- global PostgreSQL au serveur du client.
ALTER TABLE clients_campagnes SET (
    fillfactor = 90,
    autovacuum_vacuum_scale_factor = 0.01,
    autovacuum_vacuum_threshold = 10000,
    autovacuum_analyze_scale_factor = 0.005,
    autovacuum_analyze_threshold = 5000,
    autovacuum_vacuum_insert_scale_factor = 0.02,
    autovacuum_vacuum_insert_threshold = 10000
);

-- Aide le planner sur les prédicats fortement corrélés des moteurs : une
-- campagne donnée a peu de combinaisons état/action/canal réellement actives.
CREATE STATISTICS IF NOT EXISTS st_cc_campaign_workflow
    (dependencies, mcv, ndistinct)
    ON "ID_CAMPAGNE", row_status, conversion, "Canal", "Action", "ID_Action"
    FROM clients_campagnes;

-- Index historiques devenus contre-productifs depuis que l'état global n'est
-- plus dupliqué dans clients_campagnes. Les supprimer réduit le coût de chaque
-- UPDATE de workflow et l'espace disque à très gros volume.
DROP INDEX CONCURRENTLY IF EXISTS idx_cc_campaign_action_state_conversion;
DROP INDEX CONCURRENTLY IF EXISTS idx_cc_active_campaign_block;
DROP INDEX CONCURRENTLY IF EXISTS idx_cc_batch_waiting_keyset;
DROP INDEX CONCURRENTLY IF EXISTS idx_cc_mail_dispatch_keyset;

-- Doublon exact de l'index historique idx_cc_idcamp créé dans 001_schema.sql.
DROP INDEX CONCURRENTLY IF EXISTS idx_clients_campagnes_campaign;
DROP INDEX CONCURRENTLY IF EXISTS idx_cc_conversion_date;

-- Rafraîchit les statistiques après création/suppression d'index et la nouvelle
-- statistique multicolonne. ANALYZE ne réécrit pas les données métier.
ANALYZE clients_campagnes;
ANALYZE campagnes;
