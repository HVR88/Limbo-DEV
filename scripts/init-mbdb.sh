#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_FILE="$ROOT_DIR/upstream/lidarr-metadata/lidarrmetadata/sql/CreateIndices.sql"

if [[ ! -f "$SQL_FILE" ]]; then
  echo "Missing SQL file: $SQL_FILE" >&2
  exit 1
fi

MB_DB_HOST=${MB_DB_HOST:-db}
MB_DB_PORT=${MB_DB_PORT:-5432}
MB_DB_USER=${MB_DB_USER:-musicbrainz}
MB_DB_PASSWORD=${MB_DB_PASSWORD:-musicbrainz}
MB_DB_NAME=${MB_DB_NAME:-musicbrainz_db}
MB_ADMIN_DB=${MB_ADMIN_DB:-postgres}
MB_DB_NETWORK=${MB_DB_NETWORK:-}

LMD_CACHE_DB=${LMD_CACHE_DB:-lm_cache_db}
LMD_CACHE_USER=${LMD_CACHE_USER:-abc}
LMD_CACHE_PASSWORD=${LMD_CACHE_PASSWORD:-abc}

TMP_SQL="$(mktemp)"
CACHE_SQL="$(mktemp)"
trap 'rm -f "$TMP_SQL" "$CACHE_SQL"' EXIT

# Make CreateIndices.sql idempotent
sed -E 's/^CREATE INDEX /CREATE INDEX IF NOT EXISTS /I' "$SQL_FILE" > "$TMP_SQL"

use_docker=0
if [[ -n "$MB_DB_NETWORK" ]]; then
  use_docker=1
fi

if [[ "$use_docker" -eq 0 ]] && command -v psql >/dev/null 2>&1; then
  psql_run() {
    PGPASSWORD="$MB_DB_PASSWORD" psql -h "$MB_DB_HOST" -p "$MB_DB_PORT" -U "$MB_DB_USER" -d "$1" "${@:2}"
  }
  psql_run_cache() {
    PGPASSWORD="$LMD_CACHE_PASSWORD" psql -h "$MB_DB_HOST" -p "$MB_DB_PORT" -U "$LMD_CACHE_USER" -d "$1" "${@:2}"
  }
  SQL_PATH="$TMP_SQL"
  CACHE_SQL_PATH="$CACHE_SQL"
else
  POSTGRES_IMAGE=${POSTGRES_IMAGE:-postgres:14-alpine}
  docker_args_mb=(--rm -e PGPASSWORD="$MB_DB_PASSWORD" -v "$TMP_SQL":/sql/CreateIndices.sql:ro -v "$CACHE_SQL":/sql/cache.sql:ro)
  docker_args_cache=(--rm -e PGPASSWORD="$LMD_CACHE_PASSWORD" -v "$TMP_SQL":/sql/CreateIndices.sql:ro -v "$CACHE_SQL":/sql/cache.sql:ro)
  if [[ -n "$MB_DB_NETWORK" ]]; then
    docker_args_mb+=(--network "$MB_DB_NETWORK")
    docker_args_cache+=(--network "$MB_DB_NETWORK")
  fi
  psql_run() {
    docker run "${docker_args_mb[@]}" "$POSTGRES_IMAGE" \
      psql -h "$MB_DB_HOST" -p "$MB_DB_PORT" -U "$MB_DB_USER" -d "$1" "${@:2}"
  }
  psql_run_cache() {
    docker run "${docker_args_cache[@]}" "$POSTGRES_IMAGE" \
      psql -h "$MB_DB_HOST" -p "$MB_DB_PORT" -U "$LMD_CACHE_USER" -d "$1" "${@:2}"
  }
  SQL_PATH="/sql/CreateIndices.sql"
  CACHE_SQL_PATH="/sql/cache.sql"
fi

ensure_role() {
  if ! psql_run "$MB_ADMIN_DB" -tAc "SELECT 1 FROM pg_roles WHERE rolname='${LMD_CACHE_USER}'" | grep -q 1; then
    echo "Creating role: ${LMD_CACHE_USER}"
    psql_run "$MB_ADMIN_DB" -v ON_ERROR_STOP=1 \
      -c "CREATE ROLE \"${LMD_CACHE_USER}\" LOGIN PASSWORD '${LMD_CACHE_PASSWORD}';"
  else
    echo "Role exists: ${LMD_CACHE_USER}"
  fi
}

ensure_db() {
  if ! psql_run "$MB_ADMIN_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='${LMD_CACHE_DB}'" | grep -q 1; then
    echo "Creating database: ${LMD_CACHE_DB} (owner: ${LMD_CACHE_USER})"
    psql_run "$MB_ADMIN_DB" -v ON_ERROR_STOP=1 \
      -c "CREATE DATABASE \"${LMD_CACHE_DB}\" OWNER \"${LMD_CACHE_USER}\";"
  else
    echo "Database exists: ${LMD_CACHE_DB}"
  fi
}

echo "Initializing cache role/database and MusicBrainz indexes..."
ensure_role
ensure_db

# Create indexes on musicbrainz_db
psql_run "$MB_DB_NAME" -v ON_ERROR_STOP=1 -f "$SQL_PATH"

cat > "$CACHE_SQL" <<'SQL'
CREATE OR REPLACE FUNCTION cache_updated() RETURNS TRIGGER
AS
$$
BEGIN
    NEW.updated = current_timestamp;
    RETURN NEW;
END;
$$
language 'plpgsql';
SQL

cache_tables=(fanart tadb wikipedia artist album spotify)
for table in "${cache_tables[@]}"; do
  cat >> "$CACHE_SQL" <<SQL
CREATE TABLE IF NOT EXISTS ${table} (key varchar PRIMARY KEY, expires timestamp with time zone, updated timestamp with time zone default current_timestamp, value bytea);
CREATE INDEX IF NOT EXISTS ${table}_expires_idx ON ${table}(expires);
CREATE INDEX IF NOT EXISTS ${table}_updated_idx ON ${table}(updated DESC) INCLUDE (key);
DROP TRIGGER IF EXISTS ${table}_updated_trigger ON ${table};
CREATE TRIGGER ${table}_updated_trigger BEFORE UPDATE ON ${table} FOR EACH ROW WHEN (OLD.value IS DISTINCT FROM NEW.value) EXECUTE PROCEDURE cache_updated();
SQL
done

# Ensure cache tables exist in lm_cache_db
psql_run_cache "$LMD_CACHE_DB" -v ON_ERROR_STOP=1 -f "$CACHE_SQL_PATH"

echo "Done."
