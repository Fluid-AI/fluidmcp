#!/bin/bash
#
# FluidMCP Docker Entrypoint Script
# ==================================
#
# This script serves as the Docker container entrypoint for FluidMCP.
# It configures and launches MCP servers based on the METADATA_ENV_FILE_CONTENT
# environment variable.
#
# USAGE:
# ------
# Set the METADATA_ENV_FILE_CONTENT environment variable with a JSON string
# that specifies the configuration source and type.
#
# SUPPORTED FORMATS:
# -----------------
#
# 1. S3 Configuration:
#    METADATA_ENV_FILE_CONTENT='{"s3": "s3://bucket/path/to/config.json"}'
#    - Fetches configuration from an S3 bucket
#    - Requires S3_BUCKET_NAME, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION env vars
#
# 2. File Path:
#    METADATA_ENV_FILE_CONTENT='{"file": "/path/to/config.json"}'
#    - Uses a configuration file from the filesystem
#    - Path is automatically mapped from /fluidmcp to /app for Docker volumes
#
# 3. Inline JSON Configuration:
#    METADATA_ENV_FILE_CONTENT='{"file": {"mcpServers": {...}}}'
#    - Embeds the entire configuration as JSON
#    - Configuration is written to /app/metadata_env_file.json before execution
#
# ERROR HANDLING:
# --------------
# If METADATA_ENV_FILE_CONTENT is not set or invalid, the container will drop
# into an interactive bash shell for debugging.
#

# Exit immediately if any command fails
set -e

# ==============================================================================
# CONFIGURATION PARSING
# ==============================================================================

# Read the METADATA_ENV_FILE_CONTENT environment variable
# This variable should contain a JSON object specifying the config source
METADATA_ENV_FILE_CONTENT="${METADATA_ENV_FILE_CONTENT:-}"

# Check if METADATA_ENV_FILE_CONTENT is set
if [ -z "$METADATA_ENV_FILE_CONTENT" ]; then
  echo "ERROR: METADATA_ENV_FILE_CONTENT environment variable is not set"
  echo ""
  echo "Please provide a configuration using one of these formats:"
  echo "  - S3:   {\"s3\": \"s3://bucket/path/config.json\"}"
  echo "  - File: {\"file\": \"/path/to/config.json\"}"
  echo "  - JSON: {\"file\": {\"mcpServers\": {...}}}"
  echo ""
  echo "Dropping into bash for debugging..."
  exec bash
fi

# Parse the JSON to determine the configuration type (s3 or file)
# This extracts the first key from the JSON object
TYPE=$(echo "$METADATA_ENV_FILE_CONTENT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(list(d.keys())[0])" 2>/dev/null || echo "")

# ==============================================================================
# S3 CONFIGURATION HANDLER
# ==============================================================================

if [ "$TYPE" = "s3" ]; then
  echo "Configuration type: S3"

  # Extract the S3 URL from the JSON
  URL=$(echo "$METADATA_ENV_FILE_CONTENT" | python3 -c "import sys, json; print(json.load(sys.stdin)['s3'])")

  echo "Fetching configuration from S3: $URL"
  echo "Starting FluidMCP server with S3 configuration..."

  # Run FluidMCP with S3 configuration
  # --s3: Indicates configuration should be fetched from S3
  # --start-server: Starts the FastAPI gateway server (blocks to keep container running)
  exec fmcp run "$URL" --s3 --start-server

# ==============================================================================
# FILE CONFIGURATION HANDLER
# ==============================================================================

elif [ "$TYPE" = "file" ]; then
  echo "Configuration type: File"

  # Extract the value of the "file" key
  # This could be either a string (file path) or a dict (inline JSON config)
  VALUE=$(echo "$METADATA_ENV_FILE_CONTENT" | python3 -c "import sys, json; v=json.load(sys.stdin)['file']; import json; print(json.dumps(v))")

  # Check if VALUE is a string (file path) or dict (inline JSON)
  if echo "$VALUE" | python3 -c "import sys, json; v=json.load(sys.stdin); assert isinstance(v, str)" 2>/dev/null; then
    # -------------------------------------------------------------------------
    # CASE 1: File Path - Copy existing config file
    # -------------------------------------------------------------------------

    # Extract the file path from the JSON string
    FILE_PATH=$(echo "$VALUE" | python3 -c "import sys, json; print(json.load(sys.stdin))")

    echo "Original file path: $FILE_PATH"

    # Normalize the file path for Docker volume mapping
    # Replace any path ending with /fluidmcp with /app
    # This handles cases where host paths are mounted as volumes
    FILE_PATH=$(echo "$FILE_PATH" | sed -E 's|^.*/fluidmcp|/app|')

    echo "Mapped file path: $FILE_PATH"

    # Destination path inside the container
    DEST_PATH="/app/metadata_env_file.json"

    # Verify that the source file exists
    if [ -f "$FILE_PATH" ]; then
      echo "Copying configuration file to $DEST_PATH"
      cp "$FILE_PATH" "$DEST_PATH"
    else
      echo "ERROR: Configuration file not found: $FILE_PATH"
      echo ""
      echo "Please ensure the file exists and is mounted into the container."
      echo "Dropping into bash for debugging..."
      exec bash
    fi

    echo "Starting FluidMCP server with file configuration..."

    # Run FluidMCP with file configuration
    # --file: Indicates configuration is from a file
    # --start-server: Starts the FastAPI gateway server (blocks to keep container running)
    exec fmcp run "$DEST_PATH" --file --start-server

  else
    # -------------------------------------------------------------------------
    # CASE 2: Inline JSON - Write config from environment variable
    # -------------------------------------------------------------------------

    echo "Using inline JSON configuration"

    # Destination path for the generated config file
    DEST_PATH="/app/metadata_env_file.json"

    echo "Writing configuration to $DEST_PATH"

    # Parse the JSON and write it to a file
    # This handles the case where the entire config is embedded in the env var
    echo "$VALUE" | python3 -c "import sys, json; json.dump(json.loads(sys.stdin.read()), open('$DEST_PATH', 'w'), indent=2)"

    echo "Starting FluidMCP server with inline configuration..."

    # Run FluidMCP with file configuration
    # --file: Indicates configuration is from a file
    # --start-server: Starts the FastAPI gateway server (blocks to keep container running)
    exec fmcp run "$DEST_PATH" --file --start-server
  fi

# ==============================================================================
# ERROR HANDLER - Invalid Configuration Type
# ==============================================================================

else
  echo "ERROR: Invalid METADATA_ENV_FILE_CONTENT format"
  echo ""
  echo "Expected JSON with 's3' or 'file' key, but got: $TYPE"
  echo "Received content: $METADATA_ENV_FILE_CONTENT"
  echo ""
  echo "Please provide a configuration using one of these formats:"
  echo "  - S3:   {\"s3\": \"s3://bucket/path/config.json\"}"
  echo "  - File: {\"file\": \"/path/to/config.json\"}"
  echo "  - JSON: {\"file\": {\"mcpServers\": {...}}}"
  echo ""
  echo "Dropping into bash for debugging..."
  exec bash
fi
