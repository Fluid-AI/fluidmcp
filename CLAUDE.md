# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FluidMCP is a CLI tool for orchestrating multiple Model Context Protocol (MCP) servers through a single configuration file and a unified FastAPI gateway. It enables running multiple MCP servers with one command and exposes them via HTTP endpoints.

## Build and Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Install package in development mode
pip install -e .

# Run the CLI (three equivalent commands)
fluidmcp <command>
fmcp <command>
fluidai-mcp <command>
```

There are no automated tests in this repository currently. Manual testing can be done using sample configurations in the `examples/` directory.

## Architecture

### Entry Point
- `fluidai_mcp/cli.py` - Main CLI implementation with argument parsing and command handlers

### Services Layer (`fluidai_mcp/services/`)
- `config_resolver.py` - Unified config resolution from multiple sources (packages, files, S3)
  - `resolve_from_file()` - Handles both direct configs and package strings
  - `_create_temp_server_dir()` - Creates temp metadata for direct configs
- `run_servers.py` - Unified server launcher for all run modes
- `package_installer.py` - Downloads and installs MCP packages from registry
- `package_launcher.py` - Launches MCP servers via FastAPI proxy (`launch_mcp_using_fastapi_proxy`)
- `env_manager.py` - Manages environment variables for packages
- `s3_utils.py` - S3 upload/download for master mode configuration
- `network_utils.py` - Port management utilities
- `package_list.py` - Package version resolution

### Key Data Structures

MCP server configurations support two formats:

**Format 1: Direct Server Configuration (Recommended for Testing)**
```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@package/server"],
      "env": {
        "API_KEY": "value"
      }
    }
  }
}
```
- Runs immediately without installation
- FluidMCP creates temporary metadata in `.fmcp-packages/.temp_servers/`
- Ideal for testing and development

**Format 2: Package String (Requires FluidMCP Registry)**
```json
{
  "mcpServers": {
    "server-name": "Author/Package@version"
  }
}
```
- Requires installation from registry
- Packages install to `.fmcp-packages/Author/Package/Version/`
- Each package has a `metadata.json` with MCP server configuration

### Key Ports
- `8090` - Individual package server (MCP_CLIENT_SERVER_PORT)
- `8099` - All packages unified server (MCP_CLIENT_SERVER_ALL_PORT)

## CLI Commands

```bash
# Install a package
fluidmcp install author/package@version [--master]

# Run servers
fluidmcp run <package> --start-server        # Single package
fluidmcp run all --start-server              # All installed packages
fluidmcp run config.json --file --start-server  # From local config file
fluidmcp run <s3-url> --s3 --start-server    # From S3 config

# List installed packages
fluidmcp list

# Edit package environment variables
fluidmcp edit-env author/package@version
```

## Testing with Sample Configurations

The `examples/` directory contains sample configurations for testing:

```bash
# Create test directory
mkdir -p /tmp/test-directory

# Run sample config with direct server configurations (no installation required)
fluidmcp run examples/sample-config.json --file --start-server

# Server runs on http://localhost:8099
# Swagger UI available at http://localhost:8099/docs

# Test an endpoint
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

Available sample files:
- `examples/sample-config.json` - Basic config with filesystem & memory servers
- `examples/sample-metadata.json` - Package metadata example
- `examples/sample-config-with-api-keys.json` - Config with API keys
- `examples/README.md` - Detailed testing guide

## Environment Variables

```bash
# S3 credentials (for --master mode)
S3_BUCKET_NAME, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION

# Registry access
MCP_FETCH_URL="https://registry.fluidmcp.com/fetch-mcp-package"
MCP_TOKEN

# Port configuration
MCP_CLIENT_SERVER_PORT=8090
MCP_CLIENT_SERVER_ALL_PORT=8099
```
