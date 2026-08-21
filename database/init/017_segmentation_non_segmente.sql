BEGIN;

-- Segment_actuel doit toujours porter une valeur métier explicite.
-- Les clients pas encore éligibles ou non Actif utilisent "non_segmente".
ALTER TABLE clients
    DROP CONSTRAINT IF EXISTS ck_clients_segment_actuel_values;

ALTER TABLE clients
    ALTER COLUMN "Segment_actuel" SET DEFAULT 'non_segmente';

UPDATE clients
SET "Segment_actuel" = 'non_segmente'
WHERE "Segment_actuel" IS NULL;

ALTER TABLE clients
    ADD CONSTRAINT ck_clients_segment_actuel_values
    CHECK (
        "Segment_actuel" IS NULL
        OR "Segment_actuel" IN (
            'Mass Market',
            'Medium',
            'Haut de gamme',
            'Premium',
            'Banque privée',
            'non_segmente'
        )
    );

COMMIT;
