# Shared local FluidMCP test settings. Sourced, not executed.
REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8099}"
BASE_URL="http://127.0.0.1:$PORT"
HEALTH_URL="$BASE_URL/health"
STATE_DIR="${TMPDIR:-/tmp}/fluidmcp-local-server-$PORT"
PID_FILE="$STATE_DIR/server.pid"
TOKEN_FILE="$STATE_DIR/token"
CURRENT_RUN_FILE="$STATE_DIR/current_run"
current_run_dir() {
    if [ ! -f "$CURRENT_RUN_FILE" ]; then
        echo "No test run on port $PORT. Run start_local_server.sh first." >&2
        return 1
    fi
    cat "$CURRENT_RUN_FILE"
}
find_project_python() {
    if [ -n "${PYTHON:-}" ]; then
        command -v "$PYTHON"
    elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
        echo "$REPO_ROOT/.venv/bin/python"
    else
        command -v python3
    fi
}
