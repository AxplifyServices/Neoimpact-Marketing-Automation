# Seed Faker — table `clients`

Ce seed est prévu pour PostgreSQL et utilise le même `.env` que l'application.

## Valeurs par défaut

- Nombre de lignes : `500000`
- Seed : `20260816`
- Préfixe `radical_compte` : `FAKE_RC_`
- Préfixe `ID_Client` : `FAKE_CL_`

Le script est rejouable : les mêmes identifiants sont mis à jour via `ON CONFLICT`
au lieu de créer des doublons.

Les clients existants qui ne portent pas le préfixe Faker ne sont pas supprimés.

## Local — Windows CMD

Depuis la racine du projet :

```bat
.venv\Scripts\python database\seeds\seed_clients_faker.py
```

ou explicitement :

```bat
.venv\Scripts\python database\seeds\seed_clients_faker.py --rows 500000 --seed 20260816
```

Le `.env` local peut continuer à utiliser PostgreSQL via `127.0.0.1:5433`.

## Serveur

Depuis `/opt/apps/marketing-automation/repo` :

```bash
docker compose -f docker-compose.prod.yml exec -T marketing_app \
  python database/seeds/seed_clients_faker.py --rows 500000 --seed 20260816
```

Dans le conteneur, `DATABASE_URL` est déjà surchargée vers `postgres:5432`.

## Vérification

À la fin, le script affiche un `SHA256 génération`.

Pour le même :
- code,
- nombre de lignes,
- seed,
- version de Faker,

le SHA256 doit être identique en local et sur le serveur.

Exemple de contrôle SQL :

```sql
SELECT COUNT(*)
FROM clients
WHERE radical_compte LIKE 'FAKE_RC_%';
```

Le résultat attendu est `500000`.
