BEGIN;

-- Le premier bootstrap Best Channel (v1) contenait un défaut de préparation
-- des catégories région au moment de l'entraînement. Tant qu'aucune interaction
-- réelle n'existe, on peut reconstruire proprement les données synthétiques et
-- les scores. Dès qu'une vraie campagne a alimenté la table, cette migration ne
-- touche ni à l'historique ni aux scores.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM dm_best_channel_interactions WHERE source = 'fake'
    ) AND NOT EXISTS (
        SELECT 1 FROM dm_best_channel_interactions WHERE source = 'reel'
    ) THEN
        DELETE FROM dm_best_channel_scores;
        DELETE FROM dm_best_channel_interactions WHERE source = 'fake';

        UPDATE clients
        SET "Canal_top1" = 'non_score',
            "Canal_top2" = 'non_score',
            "Canal_top3" = 'non_score';
    END IF;
END $$;

COMMIT;
