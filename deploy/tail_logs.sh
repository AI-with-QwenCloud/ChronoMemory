#!/usr/bin/env bash
# Streams the deployed app's logs live to your local terminal — the direct
# equivalent of what `streamlit run app.py` prints when you run it locally.
# Locally, the app prints straight to your terminal because you're running
# it in the foreground. On the instance it runs detached (systemd/Docker,
# so it survives you closing your laptop) — detached means nothing prints
# anywhere by default, you have to explicitly ask to see it. This is that.
set -euo pipefail

IP="${CHRONOMEM_INSTANCE_IP:?set CHRONOMEM_INSTANCE_IP}"
KEY="${CHRONOMEM_SSH_KEY:?set CHRONOMEM_SSH_KEY to the path of the .pem file}"

ssh -i "${KEY}" "root@${IP}" "docker logs -f --tail 100 chronomemory-app"
