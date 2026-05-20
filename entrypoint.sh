#!/bin/bash

set -e

# Railway/on-premise deployment for FluidMCP Unified Platform
# Supports MCP servers, LLM models, image/video generation
#
# Deployment modes (controlled by ON_PREMISE env var):
#   ON_PREMISE=true  → fmcp run (static config, no MongoDB, no auth required)
#   unset/false      → fmcp serve (Railway/cloud, MongoDB, bearer token auth)

# Support METADATA_ENV_FILE_CONTENT for serverless/Railway deployments
# This is REQUIRED for platforms with read-only filesystems
if [ -n "$METADATA_ENV_FILE_CONTENT" ]; then
  echo "=========================================="
  echo "✓ Using METADATA_ENV_FILE_CONTENT for serverless deployment"
  echo "=========================================="
  echo "Detected configuration via environment variable (read-only filesystem mode)"
  echo ""
  # Write config to temporary file
  CONFIG_FILE="/tmp/fluidmcp-config.json"
  echo "$METADATA_ENV_FILE_CONTENT" > "$CONFIG_FILE"
  export FMCP_CONFIG_PATH="$CONFIG_FILE"
  echo "Config written to: $CONFIG_FILE"
  echo "=========================================="
fi

# Get port from environment (Railway sets this automatically)
PORT="${PORT:-8099}"

# Initialize SERVE_PID before signal handlers to prevent race condition on early signals
SERVE_PID=""

shutdown_with_timeout() {
  local exit_code=$1
  if [ -n "$SERVE_PID" ] && kill -0 "$SERVE_PID" 2>/dev/null; then
    echo "Shutting down server (PID $SERVE_PID)..."
    kill -TERM "$SERVE_PID"
    for i in {1..30}; do
      if ! kill -0 "$SERVE_PID" 2>/dev/null; then
        wait "$SERVE_PID" 2>/dev/null || true
        exit "$exit_code"
      fi
      sleep 1
    done
    if kill -0 "$SERVE_PID" 2>/dev/null; then
      echo "⚠ Server did not stop gracefully after 30s, forcing shutdown..."
      kill -9 "$SERVE_PID" 2>/dev/null || true
      exit 1
    fi
  else
    if [ -z "$SERVE_PID" ]; then
      echo "⚠ Shutdown requested but no server PID recorded (server may not have started)"
    else
      echo "⚠ Shutdown requested but server process (PID $SERVE_PID) is not running"
    fi
  fi
  exit "$exit_code"
}

trap 'shutdown_with_timeout 130' INT
trap 'shutdown_with_timeout 143' TERM

# ============================================================================
# ON_PREMISE mode: fmcp run (static config, no MongoDB, no auth)
# ============================================================================
if [ "${ON_PREMISE}" = "true" ]; then
  echo "=========================================="
  echo "FluidMCP — On-Premise Mode"
  echo "=========================================="

  # Resolve config path
  CONFIG_PATH="${FMCP_CONFIG_PATH:-}"
  if [ -z "$CONFIG_PATH" ]; then
    echo "ERROR: ON_PREMISE mode requires a config file."
    echo "Set FMCP_CONFIG_PATH or provide config via METADATA_ENV_FILE_CONTENT."
    exit 1
  fi

  # Validate path is under /app/ or /tmp/ (prevent path traversal)
  REAL_PATH=$(realpath -m "$CONFIG_PATH" 2>/dev/null || echo "$CONFIG_PATH")
  if [[ ! "$REAL_PATH" =~ ^/app/ ]] && [[ ! "$REAL_PATH" =~ ^/tmp/ ]]; then
    echo "ERROR: CONFIG_PATH must be under /app/ or /tmp/ (security restriction)"
    echo "Got: $REAL_PATH"
    exit 1
  fi

  echo "Port:   $PORT"
  echo "Config: $CONFIG_PATH"
  echo ""

  echo "Starting fmcp run..."
  fmcp run "$CONFIG_PATH" --file --start-server --port "$PORT" &
  SERVE_PID=$!

  if ! kill -0 "$SERVE_PID" 2>/dev/null; then
    echo "✗ Server process terminated unexpectedly before wait (PID $SERVE_PID)"
    exit 1
  fi

  set +e
  wait "$SERVE_PID"
  SERVER_EXIT_CODE=$?
  set -e

  if [ "$SERVER_EXIT_CODE" -ne 0 ]; then
    echo "✗ Server process terminated unexpectedly (exit code: $SERVER_EXIT_CODE)"
  fi
  exit "$SERVER_EXIT_CODE"
fi

# ============================================================================
# SERVE mode (default): fmcp serve — Railway/cloud with MongoDB and auth
# ============================================================================

# Bearer token for client authentication (required for security)
if [ -z "$FMCP_BEARER_TOKEN" ]; then
  echo "ERROR: FMCP_BEARER_TOKEN environment variable is required"
  exit 1
fi

# Path to configuration file for auto-registration (configurable via env var)
CONFIG_PATH="${FMCP_CONFIG_PATH:-/app/examples/railway-llama4-config.json}"

# Validate path is under /app/ (prevent path traversal attacks)
REAL_PATH=$(realpath -m "$CONFIG_PATH" 2>/dev/null || echo "$CONFIG_PATH")
if [[ ! "$REAL_PATH" =~ ^/app/ ]]; then
  echo "=========================================="
  echo "❌ ERROR: Invalid Configuration Path"
  echo "=========================================="
  echo "CONFIG_PATH must be under /app/ directory (security restriction)"
  echo "Got: $REAL_PATH"
  echo ""
  echo "Please set FMCP_CONFIG_PATH to a valid path under /app/"
  echo "=========================================="
  exit 1
fi

# Redact MongoDB credentials for logging (hide username:password)
if [ -n "$MONGODB_URI" ]; then
  MONGODB_REDACTED=$(echo "$MONGODB_URI" | sed -E 's|(mongodb(\+srv)?://)[^@/]*@|\1***@|')
else
  MONGODB_REDACTED="in-memory (not configured)"
fi

echo "=========================================="
echo "FluidMCP Unified Platform"
echo "=========================================="
echo "Port: $PORT"
echo "MongoDB: $MONGODB_REDACTED"
echo "Config: $CONFIG_PATH"
echo "Security: Bearer token authentication enabled"
echo ""

# Start fmcp serve in background
# Note: FMCP_BEARER_TOKEN is read from environment (more secure than CLI arg)
echo "Starting fmcp serve..."

# Build command with optional MongoDB URI (use array to prevent shell injection)
SERVE_CMD=(fmcp serve --host 0.0.0.0 --port "$PORT" --secure --allow-all-origins)
if [ -n "$MONGODB_URI" ]; then
  SERVE_CMD+=(--mongodb-uri "$MONGODB_URI")
fi

"${SERVE_CMD[@]}" &

SERVE_PID=$!

# Give server time to start by waiting for health endpoint
echo "Waiting for server health endpoint to become ready..."
MAX_WAIT_SECONDS="${FMCP_STARTUP_TIMEOUT_SECONDS:-120}"  # Default 120s for production (configurable)
SLEEP_INTERVAL_SECONDS=2
ATTEMPTS=$((MAX_WAIT_SECONDS / SLEEP_INTERVAL_SECONDS))

for i in $(seq 1 "$ATTEMPTS"); do
  # Check if process is still alive (critical: detect crashes during startup)
  if ! kill -0 "$SERVE_PID" 2>/dev/null; then
    echo "✗ Server process died during startup (PID $SERVE_PID)"
    exit 1
  fi

  if curl -sSf "http://localhost:$PORT/health" > /dev/null 2>&1; then
    echo "✓ Server is healthy (after $((i * SLEEP_INTERVAL_SECONDS))s)"
    break
  fi
  if [ "$i" -eq "$ATTEMPTS" ]; then
    echo "✗ Server did not become ready after ${MAX_WAIT_SECONDS}s"
    exit 1
  fi
  echo "  Attempt $i/$ATTEMPTS: Server not ready yet, retrying in ${SLEEP_INTERVAL_SECONDS}s..."
  sleep "$SLEEP_INTERVAL_SECONDS"
done

# Auto-register models from config file
if [ -f "$CONFIG_PATH" ]; then
  echo ""
  echo "=========================================="
  echo "Auto-registering models from config..."
  echo "=========================================="

  # Use environment variable for bearer token (secure - not visible in ps)
  # Temporarily disable errexit to capture exit code (allow partial failures)
  # Note: Between set +e and set -e, the registration script can fail without stopping execution
  set +e
  python3 /app/scripts/register_models.py \
    "$CONFIG_PATH" \
    "http://localhost:$PORT"

  REGISTER_EXIT_CODE=$?
  set -e  # Re-enable errexit immediately after capturing exit code

  if [ $REGISTER_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✓ All models registered successfully!"
  else
    echo ""
    echo "⚠ Some models failed to register (exit code: $REGISTER_EXIT_CODE)"
    echo "⚠ Server will continue running, check logs for details"
  fi
else
  echo "⚠ Config file not found: $CONFIG_PATH"
  echo "⚠ Server running without auto-registered models"
fi

echo ""
echo "=========================================="
echo "FluidMCP is ready!"
echo "=========================================="
echo "Swagger UI: http://0.0.0.0:$PORT/docs"
echo "Health check: http://0.0.0.0:$PORT/health"
echo "API endpoint: http://0.0.0.0:$PORT/api/llm/v1/chat/completions"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Signal handlers were set up earlier (before server start) to avoid race condition
# COPILOT FIX: Check if server is still running before waiting, and propagate exit code
if ! kill -0 "$SERVE_PID" 2>/dev/null; then
  echo "✗ Server process terminated unexpectedly before wait (PID $SERVE_PID)"
  exit 1
fi

# Keep the serve process in foreground and capture its exit code
# Temporarily disable errexit to capture server exit code from wait
set +e
wait "$SERVE_PID"
SERVER_EXIT_CODE=$?
set -e

if [ "$SERVER_EXIT_CODE" -ne 0 ]; then
  echo "✗ Server process terminated unexpectedly (exit code: $SERVER_EXIT_CODE)"
fi
exit "$SERVER_EXIT_CODE"
