BEGIN;

-- Accélère la synchronisation insert-only cible -> campagne et les recherches
-- d'un client dans une campagne sans imposer une nouvelle contrainte métier.
CREATE INDEX IF NOT EXISTS idx_cc_campaign_radical
    ON clients_campagnes ("ID_CAMPAGNE", "Radical_compte");

-- Accélère la reconstruction bulk des files CRC / CC / DA.
CREATE INDEX IF NOT EXISTS idx_cc_campaign_action_state_conversion
    ON clients_campagnes ("ID_CAMPAGNE", "Action", "Etat_campagne", conversion);

COMMIT;
