#!/usr/bin/env bash
# Applies any not-yet-applied files in db/migrations/, in filename order.
# Idempotent — safe to run on every deploy, every bootstrap, every time.
# Already-applied migrations are skipped, tracked in a schema_migrations table.
# Run from the repo root, on a host where the Postgres container is reachable
# via `docker exec` (i.e. on the instance itself, not from your laptop).
set -euo pipefail

DB_CONTAINER="${CHRONOMEM_DB_CONTAINER:-chronomem-db}"
DB_NAME="${CHRONOMEM_DB_NAME:-chronomemory}"
MIGRATIONS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/migrations" && pwd)"

psql_exec() {
    docker exec -i "${DB_CONTAINER}" psql -v ON_ERROR_STOP=1 -U postgres -d "${DB_NAME}" "$@"
}

psql_exec -c "
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version     TEXT PRIMARY KEY,
        applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
" >/dev/null

for f in "${MIGRATIONS_DIR}"/*.sql; do
    version="$(basename "${f}")"
    already="$(psql_exec -tAc "SELECT 1 FROM schema_migrations WHERE version = '${version}';")"
    if [ "${already}" = "1" ]; then
        echo "==> ${version}: already applied, skipping"
        continue
    fi
    echo "==> ${version}: applying"
    psql_exec < "${f}"
    psql_exec -c "INSERT INTO schema_migrations (version) VALUES ('${version}');" >/dev/null
done

echo "==> schema up to date"
