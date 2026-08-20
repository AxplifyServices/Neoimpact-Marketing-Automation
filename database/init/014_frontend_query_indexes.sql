-- 014_frontend_query_indexes.sql
-- Indexes supporting server-side search/filtering added by frontend performance lot.
-- CONCURRENTLY keeps write blocking minimal on existing production tables.

CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- ``cibles.filtre`` est historiquement du TEXT. Cette fonction rend les
-- recherches frontend sur les filtres JSON robustes face à une ancienne
-- valeur vide/malformée, sans imposer de migration destructive de la colonne.
CREATE OR REPLACE FUNCTION neoimpact_safe_jsonb(value TEXT)
RETURNS JSONB
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
AS $$
BEGIN
    IF value IS NULL OR BTRIM(value) = '' THEN
        RETURN '{}'::jsonb;
    END IF;
    RETURN value::jsonb;
EXCEPTION WHEN others THEN
    RETURN '{}'::jsonb;
END;
$$;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_campagnes_nom_trgm
ON campagnes USING gin (nom_campagne gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_campagnes_id_trgm
ON campagnes USING gin (id_campagne gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_campagnes_description_trgm
ON campagnes USING gin (description gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_campagnes_front_filters
ON campagnes (etat_campagne, date_debut, date_fin, date_creation DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cibles_nom_trgm
ON cibles USING gin (nom_cible gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cibles_id_trgm
ON cibles USING gin (id_cible gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cibles_front_filters
ON cibles (source, date_creation DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_modeles_nom_trgm
ON modeles USING gin (nom_modele gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_modeles_id_trgm
ON modeles USING gin (id_modele gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_modeles_front_filters
ON modeles (variable_cible, date_creation DESC);
