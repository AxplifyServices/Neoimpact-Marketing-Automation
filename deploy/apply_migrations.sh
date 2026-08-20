#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-database/init}"

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

if [ ! -d "$MIGRATIONS_DIR" ]; then
  echo "Migration directory not found: $MIGRATIONS_DIR" >&2
  exit 1
fi

# Registre persistant des migrations : évite de rejouer ANALYZE/UPDATE/DDL
# à chaque déploiement et interdit la modification silencieuse d'une migration
# déjà appliquée. Toute évolution de schéma doit utiliser un nouveau fichier SQL.
compose exec -T postgres sh -lc \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SQL

for migration in "$MIGRATIONS_DIR"/*.sql; do
  [ -f "$migration" ] || continue

  name="$(basename "$migration")"
  if [ "$name" = "001_schema.sql" ]; then
    continue
  fi

  checksum="$(sha256sum "$migration" | awk '{print $1}')"
  applied_checksum="$(
    compose exec -T postgres sh -lc \
      "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atq -c \"SELECT checksum FROM schema_migrations WHERE filename = '$name';\"" \
      | tr -d '\r\n'
  )"

  if [ -n "$applied_checksum" ]; then
    if [ "$applied_checksum" != "$checksum" ]; then
      echo "ERROR: migration already applied but its checksum changed: $name" >&2
      echo "Create a new migration file instead of modifying an applied migration." >&2
      exit 1
    fi
    echo "Skipping already applied migration: $name"
    continue
  fi

  echo "Applying migration: $name"
  compose exec -T postgres sh -lc \
    'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    < "$migration"

  compose exec -T postgres sh -lc \
    "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"INSERT INTO schema_migrations(filename, checksum) VALUES ('$name', '$checksum');\"" \
    >/dev/null

done

echo "Database migrations are up to date."
