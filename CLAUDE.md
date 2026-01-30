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

## Running Tests

```bash
# Run all tests
pytest

# Run specific test suites
pytest tests/test_llm_security.py      # Security tests (14 tests)
pytest tests/test_llm_integration.py   # Integration tests (9 tests)

# Run with coverage
pytest --cov=fluidmcp
```

Manual testing can also be done using sample configurations in the `examples/` directory.

## Architecture

### Entry Point
- `fluidmcp/cli/cli.py` - Main CLI implementation with argument parsing and command handlers
- `fluidmcp/cli/__init__.py` - Package entry point with `main()` function
- `fluidmcp/cli/__main__.py` - Module execution handler

### Services Layer (`fluidmcp/cli/services/`)
- `config_resolver.py` - Unified config resolution from multiple sources (packages, files, S3, GitHub)
  - `resolve_from_file()` - Handles direct configs, package strings, and GitHub repos
  - `_handle_github_server()` - Clones and prepares GitHub repositories
  - `_create_temp_server_dir()` - Creates temp metadata for direct configs
- `github_utils.py` - GitHub repository operations
  - `clone_github_repo()` - Clone repos with authentication
  - `extract_or_create_metadata()` - Extract metadata from README or use existing
  - `normalize_github_repo()` - Parse GitHub URLs/paths
  - `validate_mcp_metadata()` - Validate metadata structure
- `run_servers.py` - Unified server launcher for all run modes
- `package_installer.py` - Downloads and installs MCP packages from registry
- `package_launcher.py` - Launches MCP servers via FastAPI proxy
  - Detects GitHub repos and sets appropriate working directory
- `env_manager.py` - Manages environment variables for packages
- `s3_utils.py` - S3 upload/download for master mode configuration
- `network_utils.py` - Port management utilities
- `package_list.py` - Package version resolution
- `llm_launcher.py` - LLM inference server lifecycle management (vLLM, Ollama, LM Studio)
  - `LLMProcess` - Process lifecycle with secure logging and environment filtering
  - `LLMHealthMonitor` - Health checks with automatic restart on failure
  - `launch_llm_models()` / `stop_all_llm_models()` - Multi-model orchestration with error recovery

### Key Data Structures

MCP server configurations support three formats:

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

**Format 2: GitHub Repository**
```json
{
  "github_token": "default-token",
  "mcpServers": {
    "server-name": {
      "github_repo": "owner/repo",
      "github_token": "optional-specific-token",
      "branch": "main",
      "env": {
        "API_KEY": "value"
      }
    }
  }
}
```
- Clones repositories to `.fmcp-packages/owner/repo/branch/`
- Automatically extracts metadata from README if metadata.json doesn't exist
- Supports default and per-server GitHub tokens
- Working directory intelligently set based on command type (npx -y vs source code)
- Can be mixed with other configuration formats

**Format 3: Package String (Requires FluidMCP Registry)**
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

# Clone and run from GitHub
fluidmcp github owner/repo --github-token TOKEN --start-server
fluidmcp github owner/repo --github-token TOKEN --branch develop --start-server

# List installed packages
fluidmcp list

# Edit package environment variables
fluidmcp edit-env author/package@version

# Show version information
fluidmcp --version

# Validate configuration without running servers
fluidmcp validate config.json --file              # Validate local config file
fluidmcp validate author/package@version          # Validate installed package
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

# GitHub access (for cloning repositories)
FMCP_GITHUB_TOKEN  # Default GitHub token
GITHUB_TOKEN       # Alternative environment variable

# Port configuration
MCP_CLIENT_SERVER_PORT=8090
MCP_CLIENT_SERVER_ALL_PORT=8099

# Server startup configuration
MCP_PORT_RELEASE_TIMEOUT=5  # Timeout in seconds when waiting for port release (default: 5)
```

## LLM Inference Servers (vLLM, Ollama, LM Studio)

FluidMCP supports running LLM inference servers with automatic error recovery and health monitoring.

### Configuration Format

Add LLM models to your config using the `llmModels` section:

```json
{
  "mcpServers": {},
  "llmModels": {
    "vllm": {
      "command": "vllm",
      "args": [
        "serve",
        "facebook/opt-125m",
        "--port", "8001",
        "--gpu-memory-utilization", "0.9"
      ],
      "env": {
        "CUDA_VISIBLE_DEVICES": "0"
      },
      "endpoints": {
        "base_url": "http://localhost:8001/v1"
      },
      "restart_policy": "on-failure",
      "max_restarts": 3,
      "restart_delay": 5
    }
  }
}
```

### Key Features

**Process Lifecycle**:
- Secure command logging (redacts API keys, tokens, passwords)
- Environment variable filtering (allowlist approach)
- Secure log file permissions (0o600)
- Graceful shutdown with force-kill fallback

**Error Recovery**:
- Automatic restart on failure (configurable policy)
- Exponential backoff between restart attempts
- CUDA OOM detection from stderr logs
- Maximum restart limits to prevent infinite loops

**Health Monitoring**:
- Periodic HTTP health checks to `/health` or `/v1/models`
- Configurable check intervals and failure thresholds
- Automatic restart trigger on consecutive failures
- Resource tracking and metrics

**Supported Restart Policies**:
- `"on-failure"` - Restart only on non-zero exit codes
- `"always"` - Restart on any termination (including success)
- `"no"` - No automatic restart

### Configuration Options

```json
{
  "command": "vllm",              // Required: Command to execute
  "args": ["serve", "model"],     // Optional: Command arguments
  "env": {                         // Optional: Environment variables
    "CUDA_VISIBLE_DEVICES": "0"
  },
  "endpoints": {                   // Required: Health check endpoint
    "base_url": "http://localhost:8001/v1"
  },
  "restart_policy": "on-failure", // Optional: "on-failure", "always", "no" (default: "no")
  "max_restarts": 3,              // Optional: Max restart attempts (default: 3)
  "restart_delay": 5,             // Optional: Base delay between restarts in seconds (default: 5)
  "health_check_interval": 30,   // Optional: Seconds between health checks (default: 30)
  "health_check_failures": 2     // Optional: Failures before restart (default: 2)
}
```

### Security Features

**Command Sanitization**:
- Automatically redacts sensitive patterns in logs: `api-key`, `token`, `secret`, `password`, `auth`, `credential`
- Handles both `--flag value` and `--flag=value` formats
- Example: `vllm serve --api-key sk-secret123` → `vllm serve --api-key ***REDACTED***`

**Environment Filtering**:
- Only allowlisted system environment variables passed to subprocess
- Allowlist: `PATH`, `HOME`, `USER`, `TMPDIR`, `LANG`, `LC_ALL`, `CUDA_VISIBLE_DEVICES`, `CUDA_DEVICE_ORDER`, `LD_LIBRARY_PATH`, `PYTHONPATH`, `VIRTUAL_ENV`
- User-provided env vars from config always included (explicit configuration)

**Log Security**:
- Stderr logs stored in `~/.fluidmcp/logs/llm_{model_id}_stderr.log`
- File permissions set to `0o600` (owner read/write only)
- Model ID sanitized to prevent path traversal attacks

### Example Configurations

See [examples/vllm-with-error-recovery.json](examples/vllm-with-error-recovery.json) for a complete working example.

**Minimal vLLM**:
```json
{
  "llmModels": {
    "vllm": {
      "command": "vllm",
      "args": ["serve", "facebook/opt-125m", "--port", "8001"],
      "endpoints": {"base_url": "http://localhost:8001/v1"}
    }
  }
}
```

**Production vLLM with Full Error Recovery**:
```json
{
  "llmModels": {
    "vllm-production": {
      "command": "vllm",
      "args": [
        "serve",
        "meta-llama/Llama-2-7b-hf",
        "--port", "8001",
        "--gpu-memory-utilization", "0.9",
        "--max-model-len", "4096"
      ],
      "env": {
        "CUDA_VISIBLE_DEVICES": "0,1",
        "HF_TOKEN": "hf_..."
      },
      "endpoints": {"base_url": "http://localhost:8001/v1"},
      "restart_policy": "on-failure",
      "max_restarts": 5,
      "restart_delay": 10,
      "health_check_interval": 60,
      "health_check_failures": 3
    }
  }
}
```

**Ollama**:
```json
{
  "llmModels": {
    "ollama": {
      "command": "ollama",
      "args": ["serve"],
      "endpoints": {"base_url": "http://localhost:11434"},
      "restart_policy": "on-failure"
    }
  }
}
```

### Implementation Files

- [fluidmcp/cli/services/llm_launcher.py](fluidmcp/cli/services/llm_launcher.py) - Core implementation
- [tests/test_llm_security.py](tests/test_llm_security.py) - Security tests (14 tests, 100% passing)
- [tests/test_llm_integration.py](tests/test_llm_integration.py) - Integration tests (9 tests, 100% passing)
- [examples/vllm-with-error-recovery.json](examples/vllm-with-error-recovery.json) - Example config
