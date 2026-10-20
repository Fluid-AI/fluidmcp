#!/usr/bin/env bash
# Log in to a running server and save a fresh JWT to $TOKEN_FILE (mode 600).
#
# Uses TEST_DEV_EMAIL / TEST_DEV_PASSWORD from the shell if set, otherwise reads
# them from Azure Key Vault, the same place the server gets its own config.
# Do not rely on BEARER_TOKEN from the shell: it is often a long-expired JWT.
#
# Prints only the role and tenant, never the token or the password.
#
# Usage: [PORT=8010] get_token.sh
#        then: TOKEN=$(cat "$TOKEN_FILE")
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

PY="$(find_project_python)"
mkdir -p "$STATE_DIR"
umask 077
cd "$REPO_ROOT"

"$PY" - "$BASE_URL" "$TOKEN_FILE" <<'EOF' 2> >(grep -v -E "DEBUG|INFO" >&2)
import base64
import json
import os
import sys

import requests

base_url, token_file = sys.argv[1], sys.argv[2]

if not (os.getenv("TEST_DEV_EMAIL") and os.getenv("TEST_DEV_PASSWORD")):
    from services.environment_variables import loadVariablesFromAzureKeyVault
    loadVariablesFromAzureKeyVault()

email, password = os.getenv("TEST_DEV_EMAIL"), os.getenv("TEST_DEV_PASSWORD")
if not (email and password):
    sys.exit("TEST_DEV_EMAIL / TEST_DEV_PASSWORD are neither in the shell nor in Key Vault")

response = requests.post(f"{base_url}/auth/get_token", json={"email": email, "password": password}, timeout=30)
if response.status_code != 200 or "token" not in response.json():
    sys.exit(f"Login failed: HTTP {response.status_code} {response.text[:200]}")

token = response.json()["token"]
with open(token_file, "w") as handle:
    handle.write(token)

payload = token.split(".")[1]
payload += "=" * (-len(payload) % 4)
metadata = json.loads(base64.urlsafe_b64decode(payload)).get("fluidai_app_metadata", {})
print(f"✅ Logged in: role={metadata.get('role')} tenant={metadata.get('tenant')}")
EOF

echo "   TOKEN_FILE=$TOKEN_FILE"
