BEGIN;

ALTER TABLE clients_campagnes
    ADD COLUMN IF NOT EXISTS conversion_date TEXT,
    ADD COLUMN IF NOT EXISTS conversion_id_action TEXT,
    ADD COLUMN IF NOT EXISTS conversion_canal TEXT,
    ADD COLUMN IF NOT EXISTS objective_source_id_action TEXT,
    ADD COLUMN IF NOT EXISTS objective_source_canal TEXT;

-- Les anciennes lignes déjà converties ne possèdent pas d'historique fiable.
-- On ne fabrique donc pas de date/canal artificiel. Elles restent conversion=1.

CREATE INDEX IF NOT EXISTS idx_cc_conversion
    ON clients_campagnes (conversion);

CREATE INDEX IF NOT EXISTS idx_cc_conversion_date
    ON clients_campagnes (conversion_date);

COMMIT;
