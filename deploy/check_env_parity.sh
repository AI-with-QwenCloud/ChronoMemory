#!/usr/bin/env bash
# Warns if a key the app actually reads via os.environ[...] is missing from
# the instance's .env file. Compares key *names* only — never reads or
# prints values, local or remote. This is what would have caught the
# CHRONOMEM_AUTH_COOKIE_KEY KeyError before it ever hit the deployed app.
set -euo pipefail

IP="${CHRONOMEM_INSTANCE_IP:?set CHRONOMEM_INSTANCE_IP}"
KEY="${CHRONOMEM_SSH_KEY:?set CHRONOMEM_SSH_KEY to the path of the .pem file}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# excludes deploy/ — those scripts (e.g. verify_alibaba_deployment.py) run
# locally against the Alibaba Cloud API, not inside the deployed container,
# so their env vars belong on your laptop, not the instance's .env
required="$(grep -rhoE 'os\.environ\["[A-Z_]+"\]' --include='*.py' \
    --exclude-dir=deploy --exclude-dir=.git . \
    | grep -oE '"[A-Z_]+"' | tr -d '"' | sort -u)"

remote_keys="$(ssh -i "${KEY}" "root@${IP}" \
    "grep -oE '^[A-Z_]+=' /opt/chronomemory/.env 2>/dev/null | tr -d '='" | sort -u)"

missing="$(comm -23 <(echo "${required}") <(echo "${remote_keys}"))"

if [ -n "${missing}" ]; then
    echo "MISSING from the instance's .env (app will KeyError on these):"
    while IFS= read -r var; do echo "  - ${var}"; done <<< "${missing}"
    exit 1
fi

echo "env parity OK — every os.environ[...] key the app reads exists in the remote .env"
