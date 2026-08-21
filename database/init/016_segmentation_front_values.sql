BEGIN;

-- Segment_actuel est produit exclusivement par le moteur de segmentation.
-- Nettoyage des anciennes modalités Faker + garde-fou DB.
UPDATE clients
SET "Segment_actuel" = NULL
WHERE "Segment_actuel" IS NOT NULL
  AND "Segment_actuel" NOT IN (
      'Mass Market', 'Medium', 'Haut de gamme', 'Premium', 'Banque privée'
  );

ALTER TABLE clients
    DROP CONSTRAINT IF EXISTS ck_clients_segment_actuel_values;

ALTER TABLE clients
    ADD CONSTRAINT ck_clients_segment_actuel_values
    CHECK (
        "Segment_actuel" IS NULL
        OR "Segment_actuel" IN (
            'Mass Market', 'Medium', 'Haut de gamme', 'Premium', 'Banque privée'
        )
    );

ALTER TABLE dm_segmentation_resultats
    DROP CONSTRAINT IF EXISTS ck_dm_segmentation_resultats_segment;

ALTER TABLE dm_segmentation_resultats
    ADD CONSTRAINT ck_dm_segmentation_resultats_segment
    CHECK (
        segment IN (
            'Mass Market', 'Medium', 'Haut de gamme', 'Premium',
            'Banque privée', 'Non segmenté'
        )
    );

CREATE INDEX IF NOT EXISTS idx_dm_segmentation_resultats_periode_region_age
    ON dm_segmentation_resultats (annee_mois, region, tranche_age);

COMMIT;
