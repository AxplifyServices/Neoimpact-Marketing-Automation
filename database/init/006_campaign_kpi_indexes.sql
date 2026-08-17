BEGIN;

-- La liste des campagnes agrège toujours clients_campagnes par ID_CAMPAGNE.
-- L'index 004 peut déjà couvrir certains cas, mais cet index simple reste
-- utile pour COUNT/SUM groupés et pour les autres endpoints de campagne.
CREATE INDEX IF NOT EXISTS idx_clients_campagnes_campaign
    ON clients_campagnes ("ID_CAMPAGNE");

COMMIT;
