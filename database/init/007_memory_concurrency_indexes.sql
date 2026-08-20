-- ============================================================
-- 007 - Scalabilité mémoire / concurrence
-- PostgreSQL 17
--
-- IMPORTANT : ne pas entourer ce fichier d'un BEGIN/COMMIT.
-- CREATE INDEX CONCURRENTLY doit s'exécuter hors transaction explicite.
-- ============================================================

-- Batch : keyset sur les lignes actives En attente/Objectif.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cc_batch_waiting_keyset
    ON clients_campagnes (
        "ID_CAMPAGNE",
        "Etat_campagne",
        conversion,
        "Action",
        id
    )
    INCLUDE ("ID_Action", "Canal", "Radical_compte");

-- Mail : lecture de petits lots ordonnés par PK technique.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cc_mail_dispatch_keyset
    ON clients_campagnes (
        "Etat_campagne",
        conversion,
        "Canal",
        "Action",
        id
    )
    INCLUDE ("ID_CAMPAGNE", "ID_Action", "Radical_compte");

-- Dashboard / filtre gestionnaire et jointures de ciblage les plus fréquentes.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_gestionnaire
    ON clients ("Gestionnaire");

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_region
    ON clients ("Region");

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_agence
    ON clients ("Agence");

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_segment_actuel
    ON clients ("Segment_actuel");

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_age
    ON clients ("Age");

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_anciennete
    ON clients ("Anciennete");

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_qualite
    ON clients ("Qualite");

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_canal_acquisition
    ON clients ("Canal_acquisition");

-- Le filtre campagne exclut systématiquement les ruptures de relation.
-- L'index partiel permet à PostgreSQL d'éviter de scanner inutilement ces lignes.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_non_rupture_radical
    ON clients (radical_compte)
    WHERE LOWER(TRIM(COALESCE("STATUT_CLIENT", ''))) <> LOWER('Rupture de relation');

ANALYZE clients;
ANALYZE clients_campagnes;
