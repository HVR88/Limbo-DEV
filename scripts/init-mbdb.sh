#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_FILE_DEFAULT="$ROOT_DIR/upstream/lidarr-metadata/lidarrmetadata/sql/CreateIndices.sql"
SQL_FILE="${SQL_FILE:-$SQL_FILE_DEFAULT}"

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

LMBRIDGE_CACHE_DB=${LMBRIDGE_CACHE_DB:-lm_cache_db}
LMBRIDGE_CACHE_USER=${LMBRIDGE_CACHE_USER:-lmbridge}
LMBRIDGE_CACHE_PASSWORD=${LMBRIDGE_CACHE_PASSWORD:-lmbridge}
LMBRIDGE_CACHE_SCHEMA=${LMBRIDGE_CACHE_SCHEMA:-public}
LMBRIDGE_CACHE_FAIL_OPEN=${LMBRIDGE_CACHE_FAIL_OPEN:-false}
LMBRIDGE_INIT_STATE_DIR=${LMBRIDGE_INIT_STATE_DIR:-/metadata/init-state}

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
    PGPASSWORD="$LMBRIDGE_CACHE_PASSWORD" psql -h "$MB_DB_HOST" -p "$MB_DB_PORT" -U "$LMBRIDGE_CACHE_USER" -d "$1" "${@:2}"
  }
  SQL_PATH="$TMP_SQL"
  CACHE_SQL_PATH="$CACHE_SQL"
else
  POSTGRES_IMAGE=${POSTGRES_IMAGE:-postgres:16-alpine}
  docker_args_mb=(--rm -e PGPASSWORD="$MB_DB_PASSWORD" -v "$TMP_SQL":/sql/CreateIndices.sql:ro -v "$CACHE_SQL":/sql/cache.sql:ro)
  docker_args_cache=(--rm -e PGPASSWORD="$LMBRIDGE_CACHE_PASSWORD" -v "$TMP_SQL":/sql/CreateIndices.sql:ro -v "$CACHE_SQL":/sql/cache.sql:ro)
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
      psql -h "$MB_DB_HOST" -p "$MB_DB_PORT" -U "$LMBRIDGE_CACHE_USER" -d "$1" "${@:2}"
  }
  SQL_PATH="/sql/CreateIndices.sql"
  CACHE_SQL_PATH="/sql/cache.sql"
fi

LEGACY_CACHE_USERS=("lidarr" "abc")

migrate_legacy_cache_role() {
  local legacy_user
  local legacy_exists
  local new_exists
  local db_exists
  local db_owner
  local schema_owner
  local legacy_owns=0
  local tables_owned
  local func_owned

  db_exists="$(psql_run "$MB_ADMIN_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='${LMBRIDGE_CACHE_DB}'" | tr -d '[:space:]')"
  if [[ "$db_exists" != "1" ]]; then
    return
  fi

  new_exists="$(psql_run "$MB_ADMIN_DB" -tAc "SELECT 1 FROM pg_roles WHERE rolname='${LMBRIDGE_CACHE_USER}'" | tr -d '[:space:]')"
  db_owner="$(psql_run "$MB_ADMIN_DB" -tAc "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='${LMBRIDGE_CACHE_DB}'" | tr -d '[:space:]')"
  for legacy_user in "${LEGACY_CACHE_USERS[@]}"; do
    if [[ "$LMBRIDGE_CACHE_USER" == "$legacy_user" ]]; then
      return
    fi

    legacy_exists="$(psql_run "$MB_ADMIN_DB" -tAc "SELECT 1 FROM pg_roles WHERE rolname='${legacy_user}'" | tr -d '[:space:]')"
    if [[ "$legacy_exists" != "1" ]]; then
      continue
    fi

    legacy_owns=0
    if [[ "$db_owner" == "$legacy_user" ]]; then
      legacy_owns=1
    fi

    tables_owned="$(psql_run "$LMBRIDGE_CACHE_DB" -tAc "SELECT 1 FROM pg_tables WHERE schemaname='${LMBRIDGE_CACHE_SCHEMA}' AND tableowner='${legacy_user}' LIMIT 1;" | tr -d '[:space:]')"
    if [[ "$tables_owned" == "1" ]]; then
      legacy_owns=1
    fi

    func_owned="$(psql_run "$LMBRIDGE_CACHE_DB" -tAc "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE p.proname='cache_updated' AND n.nspname='${LMBRIDGE_CACHE_SCHEMA}' AND pg_get_userbyid(p.proowner)='${legacy_user}' LIMIT 1;" | tr -d '[:space:]')"
    if [[ "$func_owned" == "1" ]]; then
      legacy_owns=1
    fi

    if [[ "$legacy_owns" != "1" ]]; then
      continue
    fi

    if [[ "$new_exists" != "1" ]]; then
      echo "Migrating legacy cache role ${legacy_user} -> ${LMBRIDGE_CACHE_USER}..."
      psql_run "$MB_ADMIN_DB" -v ON_ERROR_STOP=1 \
        -c "ALTER ROLE \"${legacy_user}\" RENAME TO \"${LMBRIDGE_CACHE_USER}\";"
    else
      echo "Reassigning cache ownership from ${legacy_user} to ${LMBRIDGE_CACHE_USER}..."
      if [[ "$db_owner" == "$legacy_user" ]]; then
        psql_run "$MB_ADMIN_DB" -v ON_ERROR_STOP=1 \
          -c "ALTER DATABASE \"${LMBRIDGE_CACHE_DB}\" OWNER TO \"${LMBRIDGE_CACHE_USER}\";"
      fi
      schema_owner="$(psql_run "$LMBRIDGE_CACHE_DB" -tAc "SELECT nspowner::regrole::text FROM pg_namespace WHERE nspname='${LMBRIDGE_CACHE_SCHEMA}'" | tr -d '[:space:]')"
      if [[ "$schema_owner" == "$legacy_user" ]]; then
        psql_run "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 \
          -c "ALTER SCHEMA \"${LMBRIDGE_CACHE_SCHEMA}\" OWNER TO \"${LMBRIDGE_CACHE_USER}\";"
      fi
      psql_run "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 \
        -c "REASSIGN OWNED BY \"${legacy_user}\" TO \"${LMBRIDGE_CACHE_USER}\";"
    fi

    psql_run "$MB_ADMIN_DB" -v ON_ERROR_STOP=1 \
      -c "ALTER ROLE \"${LMBRIDGE_CACHE_USER}\" LOGIN PASSWORD '${LMBRIDGE_CACHE_PASSWORD}';"
    return
  done
}

ensure_role() {
  if ! psql_run "$MB_ADMIN_DB" -tAc "SELECT 1 FROM pg_roles WHERE rolname='${LMBRIDGE_CACHE_USER}'" | grep -q 1; then
    echo "Creating role: ${LMBRIDGE_CACHE_USER}"
    psql_run "$MB_ADMIN_DB" -v ON_ERROR_STOP=1 \
      -c "CREATE ROLE \"${LMBRIDGE_CACHE_USER}\" LOGIN PASSWORD '${LMBRIDGE_CACHE_PASSWORD}';"
  else
    echo "Role exists: ${LMBRIDGE_CACHE_USER}"
  fi
}

ensure_db() {
  if ! psql_run "$MB_ADMIN_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='${LMBRIDGE_CACHE_DB}'" | grep -q 1; then
    echo "Creating database: ${LMBRIDGE_CACHE_DB} (owner: ${LMBRIDGE_CACHE_USER})"
    psql_run "$MB_ADMIN_DB" -v ON_ERROR_STOP=1 \
      -c "CREATE DATABASE \"${LMBRIDGE_CACHE_DB}\" OWNER \"${LMBRIDGE_CACHE_USER}\";"
  else
    echo "Database exists: ${LMBRIDGE_CACHE_DB}"
  fi
}

echo "Initializing cache role/database and MusicBrainz indexes..."
migrate_legacy_cache_role
ensure_role
ensure_db

# Ensure cache DB permissions so cache tables can be created
echo "Ensuring cache DB permissions..."
psql_run "$MB_ADMIN_DB" -v ON_ERROR_STOP=1 \
  -c "GRANT CONNECT ON DATABASE \"${LMBRIDGE_CACHE_DB}\" TO \"${LMBRIDGE_CACHE_USER}\";"
psql_run "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 \
  -c "GRANT USAGE, CREATE ON SCHEMA public TO \"${LMBRIDGE_CACHE_USER}\";"

if [[ "$LMBRIDGE_CACHE_SCHEMA" != "public" ]]; then
  psql_run "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 \
    -c "CREATE SCHEMA IF NOT EXISTS \"${LMBRIDGE_CACHE_SCHEMA}\" AUTHORIZATION \"${LMBRIDGE_CACHE_USER}\";"
  psql_run "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 \
    -c "GRANT USAGE, CREATE ON SCHEMA \"${LMBRIDGE_CACHE_SCHEMA}\" TO \"${LMBRIDGE_CACHE_USER}\";"
  psql_run "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 \
    -c "ALTER ROLE \"${LMBRIDGE_CACHE_USER}\" IN DATABASE \"${LMBRIDGE_CACHE_DB}\" SET search_path = \"${LMBRIDGE_CACHE_SCHEMA}\", public;"
fi

# Create indexes on musicbrainz_db
psql_run "$MB_DB_NAME" -v ON_ERROR_STOP=1 -f "$SQL_PATH"

{
  if [[ "$LMBRIDGE_CACHE_SCHEMA" != "public" ]]; then
    echo "SET search_path TO \"${LMBRIDGE_CACHE_SCHEMA}\", public;"
  fi
  cat <<'SQL'
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.proname = 'cache_updated'
          AND n.nspname = current_schema()
    ) THEN
        EXECUTE $f$
        CREATE FUNCTION cache_updated() RETURNS TRIGGER
        AS $$
        BEGIN
            NEW.updated = current_timestamp;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        $f$;
    END IF;
END
$do$;
SQL
} > "$CACHE_SQL"

cache_tables=(fanart tadb wikipedia artist album spotify)

# Try to align ownership/privileges for existing cache tables/functions.
for table in "${cache_tables[@]}"; do
  owner="$(psql_run "$LMBRIDGE_CACHE_DB" -tAc "SELECT tableowner FROM pg_tables WHERE schemaname = current_schema() AND tablename = '${table}';" | tr -d '[:space:]')"
  if [[ -n "$owner" && "$owner" != "$LMBRIDGE_CACHE_USER" ]]; then
    if ! psql_run "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 -c "ALTER TABLE \"${table}\" OWNER TO \"${LMBRIDGE_CACHE_USER}\";" ; then
      echo "WARNING: Unable to change owner for table ${table}; will grant privileges and skip indexes/triggers if not owner." >&2
    fi
  fi
  if [[ -n "$owner" ]]; then
    psql_run "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 \
      -c "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE \"${table}\" TO \"${LMBRIDGE_CACHE_USER}\";"
  fi
done

func_owner="$(psql_run "$LMBRIDGE_CACHE_DB" -tAc "SELECT pg_get_userbyid(p.proowner) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE p.proname = 'cache_updated' AND n.nspname = current_schema();" | tr -d '[:space:]')"
if [[ -n "$func_owner" && "$func_owner" != "$LMBRIDGE_CACHE_USER" ]]; then
  if ! psql_run "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 -c "ALTER FUNCTION cache_updated() OWNER TO \"${LMBRIDGE_CACHE_USER}\";" ; then
    echo "WARNING: Unable to change owner for function cache_updated; will avoid replacing it." >&2
  fi
fi

for table in "${cache_tables[@]}"; do
  cat >> "$CACHE_SQL" <<SQL
CREATE TABLE IF NOT EXISTS ${table} (key varchar PRIMARY KEY, expires timestamp with time zone, updated timestamp with time zone default current_timestamp, value bytea);
DO \$do\$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_tables
        WHERE schemaname = current_schema()
          AND tablename = '${table}'
          AND tableowner = current_user
    ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS ${table}_expires_idx ON ${table}(expires);';
        EXECUTE 'CREATE INDEX IF NOT EXISTS ${table}_updated_idx ON ${table}(updated DESC) INCLUDE (key);';
        EXECUTE 'DROP TRIGGER IF EXISTS ${table}_updated_trigger ON ${table};';
        EXECUTE 'CREATE TRIGGER ${table}_updated_trigger BEFORE UPDATE ON ${table} FOR EACH ROW WHEN (OLD.value IS DISTINCT FROM NEW.value) EXECUTE PROCEDURE cache_updated();';
    END IF;
END
\$do\$;
SQL
done

# Ensure cache tables exist in lm_cache_db
mkdir -p "$LMBRIDGE_INIT_STATE_DIR"
if ! psql_run_cache "$LMBRIDGE_CACHE_DB" -v ON_ERROR_STOP=1 -f "$CACHE_SQL_PATH"; then
  echo "ERROR: cache table creation failed for database ${LMBRIDGE_CACHE_DB}." >&2
  echo "Common cause: ${LMBRIDGE_CACHE_USER} lacks CREATE on schema ${LMBRIDGE_CACHE_SCHEMA}." >&2
  echo "Suggested fix: GRANT USAGE, CREATE ON SCHEMA ${LMBRIDGE_CACHE_SCHEMA} TO ${LMBRIDGE_CACHE_USER};" >&2
  if [[ "$LMBRIDGE_CACHE_FAIL_OPEN" == "true" || "$LMBRIDGE_CACHE_FAIL_OPEN" == "1" ]]; then
    echo "Cache fail-open enabled. API will start with cache disabled." >&2
    touch "$LMBRIDGE_INIT_STATE_DIR/cache_init_failed"
    exit 0
  fi
  exit 3
fi
rm -f "$LMBRIDGE_INIT_STATE_DIR/cache_init_failed"

echo "Done."
