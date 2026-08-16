# Bulk campaign PostgreSQL

## Objectif

Optimiser la création et la synchronisation de campagnes sur des cibles DB de plusieurs centaines de milliers de clients.

## Changements

- Cible DB: sélection des `radical_compte` directement en SQL, sans DataFrame Pandas.
- Exclusion `Rupture de relation` directement dans PostgreSQL.
- `clients_campagnes`: `INSERT ... SELECT` massif au lieu de `executemany()`.
- Synchronisation batch insert-only: SQL natif + `NOT EXISTS`.
- `clients_cibles`: insertion insert-only native PostgreSQL pour les cibles DB.
- CRC / CC / DA: remplissage des queues via les fonctions bulk `INSERT ... SELECT` existantes.
- Cibles fichier plat: fallback historique conservé.
- Frontend: timeout de création campagne à 120 s uniquement pour cette requête.
- API: réponse de création enrichie avec `bulk_mode` et `timings_ms`.

## Migration locale

Windows CMD, depuis la racine du projet:

```bat
docker compose exec -T postgres sh -lc "psql -U $POSTGRES_USER -d $POSTGRES_DB" < database/init/004_bulk_campaign_indexes.sql
```

Le déploiement serveur applique automatiquement `004_bulk_campaign_indexes.sql` via le workflow existant.

## Vérification

Après création d'une campagne, la réponse API contient notamment:

```json
{
  "bulk_mode": "postgresql_native",
  "timings_ms": {
    "target": 0,
    "insert_clients_campagnes": 0,
    "routing_outputs": 0,
    "total": 0
  }
}
```

Les valeurs sont en millisecondes.

## Note terrain

Le remplissage local CRC/CC/DA est bulk. Les visites terrain externes restent un traitement distinct car elles impliquent un appel HTTP par client. Le batch existant continue de gérer `dispatch_pending_visits_for_campaign`.
