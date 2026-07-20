#!/usr/bin/env bash
# Ships local changes to an already-running ECS instance and brings the app
# back up on them: full code sync, schema migrations, image rebuild, service
# restart, two-level verify. Run this from your laptop, from the repo root.
#
# This replaces hand-picking which files changed (app.py? requirements.txt?
# schema.sql? — that's exactly how the bcrypt/users-table/cookie-key bugs
# happened) with syncing everything every time, migrations included.
#
# Required env vars:
#   CHRONOMEM_INSTANCE_IP   the instance's public IP
#   CHRONOMEM_SSH_KEY       path to the private key .pem file
# Optional:
#   ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET
#     — if set, the final ECS-level verify step runs too
set -euo pipefail

IP="${CHRONOMEM_INSTANCE_IP:?set CHRONOMEM_INSTANCE_IP}"
KEY="${CHRONOMEM_SSH_KEY:?set CHRONOMEM_SSH_KEY to the path of the .pem file}"
REMOTE="root@${IP}"
APP_DIR="/opt/chronomemory"
SSH="ssh -i ${KEY}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> [1/6] syncing code (excludes .git, __pycache__, .env, the audit db)"
rsync -a -e "${SSH}" \
    --exclude .git --exclude __pycache__ --exclude .env \
    --exclude chronomemory_audit.db \
    ./ "${REMOTE}:${APP_DIR}/"

echo "==> [2/6] checking .env has every key the app requires (names only, values never read)"
bash "$(dirname "${BASH_SOURCE[0]}")/check_env_parity.sh" || true

echo "==> [3/6] applying any new Postgres schema migrations"
${SSH} "${REMOTE}" "cd ${APP_DIR} && bash db/migrate.sh"

echo "==> [4/6] applying any new SQLite audit-db migrations"
${SSH} "${REMOTE}" "cd ${APP_DIR} && python3 db/migrate_sqlite.py"

echo "==> [5/6] rebuilding image and restarting the service"
${SSH} "${REMOTE}" "cd ${APP_DIR} && docker build -t chronomemory-app . && systemctl restart chronomemory && sleep 3 && systemctl is-active chronomemory"

echo "==> [6/6] verifying"
${SSH} "${REMOTE}" "docker logs chronomemory-app --tail 15"
curl -s -o /dev/null -w "app http_status: %{http_code}\n" --max-time 10 "http://${IP}:8501"
if [ -n "${ALIBABA_CLOUD_ACCESS_KEY_ID:-}" ]; then
    python3 deploy/verify_alibaba_deployment.py
else
    echo "(skipping ECS-level verify — ALIBABA_CLOUD_ACCESS_KEY_ID not set)"
fi

echo "==> done"
