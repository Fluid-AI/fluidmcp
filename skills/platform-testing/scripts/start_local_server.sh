#!/usr/bin/env bash
# Start the FluidGPT server from the current checkout and open a new test run.
#
# Same launch as tests/e2e-tests/scripts/init.sh (uvicorn server.main:app), except:
#   - port defaults to 8010 (PORT=... to change), since 8000 is often in use
#   - reuses an existing complete virtualenv, unless pyproject.toml / poetry.lock
#     changed vs BASE_REF: then `poetry install` and the server runs with `poetry run`
#   - the server log goes into the run directory, outside the repo, so
#     verify_run.py can later match every recorded call against it
#
# Config comes from Azure Key Vault at startup (services/environment_variables.py),
# so only the AZURE_KEY_VAULT_* variables need to be in the shell.
#
# Usage: [PORT=8010] start_local_server.sh
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

if [ -z "${AZURE_KEY_VAULT_NAME:-}" ]; then
    echo "❌ AZURE_KEY_VAULT_NAME is not set; the server cannot load its configuration."
    exit 1
fi
for var in AZURE_KEY_VAULT_CLIENT_ID AZURE_KEY_VAULT_CLIENT_SECRET AZURE_KEY_VAULT_TENANT_ID; do
    [ -n "${!var:-}" ] || echo "⚠️  $var is not set; Key Vault login falls back to managed identity."
done

if [ "$(health_code)" != "000" ]; then
    echo "❌ Something is already listening on port $PORT. Use PORT=<other port>."
    exit 1
fi

cd "$REPO_ROOT"
# Changed dependencies must be tested with this branch's own packages, not a reused
# virtualenv. `poetry run` execs the server in place, so its pid is still $!.
DEPENDENCY_CHANGES="$(changed_dependency_files)"
if [ -n "$DEPENDENCY_CHANGES" ]; then
    DEPENDENCIES="poetry install + poetry run ($(echo $DEPENDENCY_CHANGES) changed vs $BASE_REF)"
    echo "📦 $(echo $DEPENDENCY_CHANGES) changed vs $BASE_REF: installing this branch's dependencies with poetry (can take several minutes)"
    poetry install --no-interaction
    PY="$(find_project_python)"
    LAUNCH=(poetry run python)
else
    DEPENDENCIES="reused existing virtualenv (pyproject.toml and poetry.lock unchanged vs $BASE_REF)"
    PY="$(find_project_python)"
    LAUNCH=("$PY")
fi
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
COMMIT="$(git rev-parse HEAD)"
DIRTY="$(git status --porcelain --untracked-files=no | head -c1)"

RUN_DIR="$STATE_DIR/runs/$(date -u +%Y%m%dT%H%M%SZ)-${COMMIT:0:9}"
mkdir -p "$RUN_DIR/calls"
echo "$RUN_DIR" > "$CURRENT_RUN_FILE"

echo "🐍 Python: $PY"
echo "📦 Dependencies: $DEPENDENCIES"
echo "🔧 Starting $BRANCH @ ${COMMIT:0:9}${DIRTY:+ (with uncommitted changes)} on port $PORT"
nohup "${LAUNCH[@]}" -m uvicorn server.main:app --host 127.0.0.1 --port "$PORT" > "$RUN_DIR/server.log" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

python3 -I - "$RUN_DIR/run.json" <<EOF
import json, sys
json.dump({
    "branch": "$BRANCH", "commit": "$COMMIT", "uncommitted_changes": bool("$DIRTY"),
    "port": $PORT, "pid": $SERVER_PID, "python": "$PY", "dependencies": "$DEPENDENCIES",
    "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
}, open(sys.argv[1], "w"), indent=2)
EOF

# Startup takes about a minute: Key Vault, MongoDB, settings, routers.
for elapsed in $(seq 1 300); do
    if [ "$(health_code)" = "200" ]; then
        echo "✅ Ready after ${elapsed}s"
        echo "   BASE_URL=$BASE_URL"
        echo "   RUN_DIR=$RUN_DIR"
        exit 0
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "❌ Server exited during startup. Errors from $RUN_DIR/server.log:"
        grep -iE "error|exception|traceback" "$RUN_DIR/server.log" | tail -n 30 || true
        tail -n 20 "$RUN_DIR/server.log"
        rm -f "$PID_FILE"
        exit 1
    fi
    sleep 1
done

echo "❌ Not healthy after 300s. Last lines of $RUN_DIR/server.log:"
tail -n 30 "$RUN_DIR/server.log"
exit 1
