#!/usr/bin/env bash
# Bootstraps a fresh Alibaba Cloud ECS instance (Ubuntu 22.04/24.04) to run
# ChronoMemory: Postgres+pgvector in Docker, the app in a systemd service.
# Run as root (or with sudo) on the instance, from the repo root.
set -euo pipefail

APP_DIR="/opt/chronomemory"
DB_CONTAINER="chronomem-db"
DB_PASSWORD="${CHRONOMEM_DB_PASSWORD:?set CHRONOMEM_DB_PASSWORD before running}"

echo "==> Installing system packages"
apt-get update -y
apt-get install -y docker.io git

echo "==> Starting Postgres (pgvector) container"
if ! docker ps -a --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
    docker run -d --name "${DB_CONTAINER}" \
        -e POSTGRES_PASSWORD="${DB_PASSWORD}" \
        -e POSTGRES_DB=chronomemory \
        -p 127.0.0.1:5432:5432 \
        --restart unless-stopped \
        pgvector/pgvector:pg16
fi
echo "==> Waiting for Postgres to accept connections"
until docker exec "${DB_CONTAINER}" pg_isready -U postgres >/dev/null 2>&1; do
    sleep 2
done

echo "==> Applying schema migrations (idempotent — safe on every run)"
bash "${APP_DIR}/db/migrate.sh"

echo "==> Applying SQLite audit db migrations (on host, bind-mounted into the container)"
cd "${APP_DIR}"
python3 db/migrate_sqlite.py

echo "==> Building app image"
docker build -t chronomemory-app .

echo "==> Installing systemd service"
cp deploy/chronomemory.service /etc/systemd/system/chronomemory.service
systemctl daemon-reload
systemctl enable --now chronomemory

echo "==> Done. App should be reachable on port 8501."
