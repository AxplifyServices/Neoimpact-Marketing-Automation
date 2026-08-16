BEGIN;

ALTER TABLE clients_campagnes
    ADD COLUMN IF NOT EXISTS "NB_da" INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS "NB_cc" INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS "NB_push" INTEGER DEFAULT 0;

UPDATE clients_campagnes SET "NB_da" = 0 WHERE "NB_da" IS NULL;
UPDATE clients_campagnes SET "NB_cc" = 0 WHERE "NB_cc" IS NULL;
UPDATE clients_campagnes SET "NB_push" = 0 WHERE "NB_push" IS NULL;

-- NB_approche_commercial reste volontairement conservé comme compteur global
-- historique/compatibilité. Il est impossible de répartir fiablement son ancien
-- contenu entre DA et CC sans historique événementiel.

COMMIT;
