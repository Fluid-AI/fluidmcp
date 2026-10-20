# Shared settings for the platform-testing scripts. Sourced, not run.

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 8000 is often already taken by a server from another checkout, so default elsewhere.
PORT="${PORT:-8010}"
BASE_URL="http://127.0.0.1:$PORT"
HEALTH_URL="$BASE_URL/apps/health-check/is-alive"

# Kept outside the repo so nothing here can be committed by accident.
STATE_DIR="${TMPDIR:-/tmp}/fluidgpt-local-server-$PORT"
PID_FILE="$STATE_DIR/server.pid"
TOKEN_FILE="$STATE_DIR/token"
# Holds the path of the run in progress. Each run directory keeps the server log,
# every recorded call and check, so verify_run.py can be pointed at it later.
CURRENT_RUN_FILE="$STATE_DIR/current_run"

current_run_dir() {
    if [ ! -f "$CURRENT_RUN_FILE" ]; then
        echo "No test run on port $PORT. Run start_local_server.sh first." >&2
        return 1
    fi
    cat "$CURRENT_RUN_FILE"
}

# HTTP status of the health check, or 000 when nothing is listening.
health_code() {
    curl -s -o /dev/null -w "%{http_code}" --max-time 3 -X POST "$HEALTH_URL" || true
}

# Branch the dependency files are compared against.
BASE_REF="${BASE_REF:-origin/pre-development}"

# Prints pyproject.toml / poetry.lock if they differ from BASE_REF (committed or not);
# prints nothing if they don't.
changed_dependency_files() {
    local base
    if ! base="$(git -C "$REPO_ROOT" merge-base HEAD "$BASE_REF" 2>/dev/null)"; then
        echo "Cannot find $BASE_REF to compare dependencies against. Run 'git fetch origin', or set BASE_REF=<branch>." >&2
        return 1
    fi
    git -C "$REPO_ROOT" diff --name-only "$base" -- pyproject.toml poetry.lock
}

# Prints a Python that can run the server. Override with PYTHON=/path/to/python.
# If the dependency files changed, this is the checkout's own Poetry virtualenv
# (start_local_server.sh runs `poetry install` into it). Otherwise an existing
# complete virtualenv is reused: in a git worktree `poetry run` would create a new
# EMPTY one, and a full install takes many minutes.
find_project_python() {
    if [ -n "${PYTHON:-}" ]; then
        echo "$PYTHON"
        return 0
    fi

    local changed own_env
    changed="$(changed_dependency_files)" || return 1
    if [ -n "$changed" ]; then
        own_env="$(cd "$REPO_ROOT" && poetry env info -p 2>/dev/null || true)"
        if [ -n "$own_env" ] && [ -x "$own_env/bin/python" ]; then
            echo "$own_env/bin/python"
            return 0
        fi
        echo "$(echo $changed) changed vs $BASE_REF, but this checkout has no Poetry virtualenv yet. Run start_local_server.sh, which runs 'poetry install'." >&2
        return 1
    fi

    local candidates=()
    local poetry_env
    poetry_env="$(cd "$REPO_ROOT" && poetry env info -p 2>/dev/null || true)"
    [ -n "$poetry_env" ] && candidates+=("$poetry_env/bin/python")
    candidates+=("$HOME"/.cache/pypoetry/virtualenvs/*/bin/python)

    local py
    for py in "${candidates[@]}"; do
        [ -x "$py" ] || continue
        if "$py" -c 'import sys; assert (3, 11) <= sys.version_info[:2] < (3, 13); import uvicorn, fastapi, pymongo, azure.keyvault.secrets, llama_index' 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done

    echo "No complete project virtualenv found. Run 'poetry install' in $REPO_ROOT, or set PYTHON=/path/to/python." >&2
    return 1
}
