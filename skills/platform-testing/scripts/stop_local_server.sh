#!/usr/bin/env bash
# Stop the isolated FluidMCP gateway and fake HTTP MCP server.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
export PORT
exec "$(find_project_python)" "$SCRIPTS_DIR/local_server.py" stop
