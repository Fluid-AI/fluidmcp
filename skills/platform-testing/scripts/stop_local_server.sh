#!/usr/bin/env bash
# Stop the server started by start_local_server.sh and delete the saved token.
# Only kills the process recorded in $PID_FILE, and only if it is still that server.
# The run directory (server log, calls, checks) is kept for verify_run.py.
#
# Usage: [PORT=8010] stop_local_server.sh
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

rm -f "$TOKEN_FILE"

if [ ! -f "$PID_FILE" ]; then
    echo "No server started by start_local_server.sh on port $PORT."
    exit 0
fi

SERVER_PID="$(cat "$PID_FILE")"
if ps -o cmd= -p "$SERVER_PID" | grep -q "uvicorn server.main:app.*--port $PORT"; then
    kill "$SERVER_PID"
fi

# An exited child of a still-running shell stays as a zombie (STAT Z); it no
# longer serves anything, so the port being free is what counts.
for _ in $(seq 1 20); do
    if [ "$(health_code)" = "000" ]; then
        rm -f "$PID_FILE"
        echo "✅ Server on port $PORT stopped. Evidence kept in $(current_run_dir 2>/dev/null || echo "$STATE_DIR/runs")"
        exit 0
    fi
    sleep 1
done

echo "⚠️  Still answering after 20s; sending SIGKILL to $SERVER_PID"
kill -9 "$SERVER_PID" 2>/dev/null || true
rm -f "$PID_FILE"
