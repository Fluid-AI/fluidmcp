# FluidMCP Examples

This directory contains sample configuration files for testing and development.

## Important Security Notice

**All tokens, API keys, and credentials in these example files are placeholders and should never be real secrets.** Never commit files containing real API keys, tokens, or credentials to any repository. When using these examples:

- Replace placeholder values with your actual credentials only in local copies
- Use environment variables for sensitive data in production
- Add your local configuration files to `.gitignore`
- Rotate any credentials that are accidentally exposed

## Prerequisites

Before running these examples, ensure you have the following installed:

- **Node.js** (v18 or higher) - Required for npx-based MCP servers
- **TSX** - Required for TypeScript-based MCP servers: `npm install -g tsx`
- **UV** - Required for Python-based MCP servers: Install from [astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/)

To verify your installation:
```bash
node --version    # Should show v18 or higher
npx tsx --version # Should show tsx version
uv --version      # Should show uv version
```

## Sample Files

### 1. `sample-metadata.json`
A basic metadata.json file with two MCP servers (filesystem and memory) that don't require API keys.

**Use case**: Testing individual package metadata structure.

**Servers included**:
- `filesystem`: File system operations server
- `memory`: In-memory storage server

### 2. `sample-config.json`
A simple configuration file for running multiple MCP servers without API keys.

**Use case**: Testing the `fluidmcp run --file` command with direct server configurations.

**Usage**:
```bash
# Create the test directory first
mkdir -p /tmp/test-directory

# Run with FluidMCP
fluidmcp run examples/sample-config.json --file --start-server

# Access the Swagger UI at http://localhost:8099/docs
# Test an endpoint:
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

**Servers included**:
- `filesystem`: File system operations server
- `memory`: In-memory storage server

**Note**: These servers are run directly from the configuration without installation. FluidMCP creates temporary metadata files automatically.

### 3. `sample-github-config.json`
A configuration file for running MCP servers directly from GitHub repositories.

**Use case**: Testing GitHub repository cloning, running Python source code from the repo.

**Usage**:
```bash
# Replace the GitHub token in the file first
# Edit sample-github-config.json and add your GitHub personal access token

# Run with FluidMCP (requires 'uv' to be installed for Python servers)
fluidmcp run examples/sample-github-config.json --file --start-server
```

**Servers included**:
- `fastmcp-quickstart`: Python MCP server from modelcontextprotocol/python-sdk
  - Clones the repository and runs `uv run examples/snippets/servers/fastmcp_quickstart.py`
  - Demonstrates a calculator tool, greeting resource, and prompt

**Note**: GitHub repositories are automatically cloned to `.fmcp-packages/owner/repo/branch/`. FluidMCP automatically extracts metadata from the README if no metadata.json exists.

### 4. `sample-github-with-command.json`
A configuration demonstrating GitHub servers with explicit command specification for Python source code.

**Use case**: Running GitHub MCP servers from source when you already know the command (skips README extraction).

**Features**:
- **Mode 1 (Explicit Command)**: When `command` and `args` are provided, FluidMCP uses them directly without parsing README
- **Mode 2 (Auto-extraction)**: When no command specified, FluidMCP extracts from README (same as sample-github-config.json)

**Usage**:
```bash
# Replace the GitHub token in the file first
# Requires 'uv' to be installed for Python servers
fluidmcp run examples/sample-github-with-command.json --file --start-server
```

**Servers included**:
- `python-quickstart-explicit`: Uses explicit command `uv run examples/snippets/servers/fastmcp_quickstart.py`
  - Runs Python source code directly from the cloned repository
  - Faster startup (no README parsing required)
- `python-quickstart-auto`: Auto-extracts command from README
  - Same repository, but uses automatic command detection

**When to use explicit commands**:
- You know the exact command to run the MCP server from source
- The README format is non-standard or missing
- You want faster startup (skips README parsing)
- You want to override the default command from the repository
- Running Python scripts with `uv run`, `python -m`, or Node.js with `node` or `tsx`

### 5. `sample-mixed-config.json`
A configuration demonstrating multiple server types in one file.

**Use case**: Running direct commands and GitHub repos together.

**Servers included**:
- `filesystem`: Direct command configuration (npx package)
- `python-quickstart`: GitHub repository with Python source code (auto-extracts from README)

**Note**: You can set a default `github_token` at the top level of the config, which will be used for all GitHub servers that don't specify their own token.

### 6. `sample-config-with-api-keys.json`
A more complex configuration with servers that require API keys.

**Use case**: Testing environment variable management and servers with authentication.

**Servers included**:
- `google-maps`: Google Maps MCP server (requires GOOGLE_MAPS_API_KEY)
- `filesystem`: File system operations server (no key required)
- `brave-search`: Brave Search MCP server (requires BRAVE_API_KEY)

**Usage**:
```bash
# 1. Copy and edit the file with your actual API keys
cp examples/sample-config-with-api-keys.json my-config.json
# Edit my-config.json to add your real API keys

# 2. Create the test directory
mkdir -p /tmp/test-directory

# 3. Run with FluidMCP
fluidmcp run my-config.json --file --start-server
```

### 7. `github-private-repo.json`
A template configuration for accessing private GitHub repositories with authentication.

**Use case**: Running MCP servers from private/internal company repositories or private forks.

**Usage**:
```bash
# 1. Edit the file with your actual private repository details
# Replace placeholder repositories with your own private repos
# Add your GitHub personal access token(s)

# 2. Run with FluidMCP
fluidmcp run examples/github-private-repo.json --file --start-server
```

**Servers included (templates)**:
- `private-company-server`: Example private company MCP server with TypeScript
- `private-fork-with-custom-token`: Example private fork with per-server token override
- `public-server-for-comparison`: Public MCP server for comparison

**Note**: This is a template file. Replace the placeholder repositories (`your-org/private-mcp-server`, `your-username/forked-mcp-server`) with your actual private repositories. The file demonstrates both default `github_token` for all servers and per-server `github_token` overrides.

### 8. `multi-server-dependencies.json`
Demonstrates environment variable sharing across multiple MCP servers.

**Use case**: Running multiple servers with shared configuration (logging levels, workspace paths, API keys).

**Usage**:
```bash
# 1. Create the shared workspace directory
mkdir -p /tmp/shared-workspace

# 2. Run with FluidMCP
fluidmcp run examples/multi-server-dependencies.json --file --start-server

# Access the Swagger UI at http://localhost:8099/docs
# Test filesystem endpoint:
curl http://localhost:8099/filesystem/mcp/tools/list

# Test sqlite endpoint:
curl http://localhost:8099/sqlite/mcp/tools/list
```

**Servers included**:
- `filesystem`: File system operations in shared workspace
- `sqlite`: SQLite database in shared workspace
- `brave-search`: Web search (requires BRAVE_API_KEY)

**Shared environment variables**:
- `LOG_LEVEL`: Shared across all 3 servers for consistent logging
- `WORKSPACE_ROOT`: Shared between filesystem and sqlite for same working directory
- `BRAVE_API_KEY`: Unique to brave-search server

**Note**: This example shows a realistic pattern where multiple servers work in the same workspace and share common configuration values, reducing duplication.

### 9. `secure-mode.json`
Configuration for production deployment with bearer token authentication.

**Use case**: Deploying FluidMCP in production environments with security enabled, protecting API endpoints from unauthorized access.

**Usage**:
```bash
# 1. Create the test directory
mkdir -p /tmp/test-directory

# 2. Run with secure mode enabled and custom token
fluidmcp run examples/secure-mode.json --file --start-server --secure --token mySecureToken123

# 3. Test with authentication (in another terminal)
# This will succeed with correct token:
curl http://localhost:8099/filesystem/mcp/tools/list \
  -H "Authorization: Bearer mySecureToken123"

# This will fail without authentication:
curl http://localhost:8099/filesystem/mcp/tools/list
```

**How to provide your token (3 methods)**:

1. **Via command-line flag** (Recommended for testing):
   ```bash
   fluidmcp run examples/secure-mode.json --file --start-server --secure --token YOUR_TOKEN_HERE
   ```

2. **Via environment variable** (Recommended for production):
   ```bash
   export FMCP_BEARER_TOKEN="your-production-token-here"
   fluidmcp run examples/secure-mode.json --file --start-server --secure
   ```

3. **Auto-generated token** (If no token provided):
   ```bash
   # FluidMCP will generate a random secure token and display it
   fluidmcp run examples/secure-mode.json --file --start-server --secure
   # Output: "Secure mode enabled. Bearer token: <generated-token>"
   ```

**Servers included**:
- `filesystem`: File system operations server
- `memory`: In-memory storage server
- `brave-search`: Web search (requires BRAVE_API_KEY)

**Note**: When `--secure` flag is used, all API endpoints require a valid bearer token in the `Authorization` header. The token can be provided via `--token` flag, `FMCP_BEARER_TOKEN` environment variable, or will be auto-generated. This is recommended for production deployments to prevent unauthorized access.

## Quick Start for Developers

### Testing Basic Functionality

```bash
# 1. Create test directory
mkdir -p /tmp/test-directory

# 2. Run the sample config
fluidmcp run examples/sample-config.json --file --start-server

# Or with verbose logging for debugging
fluidmcp run examples/sample-config.json --file --start-server --verbose

# 3. In another terminal, test the endpoint
curl http://localhost:8099/filesystem/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

### Testing GitHub Repositories

```bash
# Run a Python MCP server directly from a GitHub repository
fluidmcp github modelcontextprotocol/python-sdk \
  --github-token YOUR_GITHUB_TOKEN \
  --branch main \
  --start-server

# Or use a config file (requires 'uv' for Python servers)
fluidmcp run examples/sample-github-config.json --file --start-server
```

### Testing Secure Mode

```bash
fluidmcp run examples/sample-config.json --file --start-server --secure --token mytoken123

# Test with authentication
curl http://localhost:8099/filesystem/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mytoken123" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

## Creating Your Own Test Configurations

FluidMCP supports three configuration formats:

### Format 1: Direct Server Configuration (Recommended for Testing)

Specify the command, args, and env directly. No installation required!

```json
{
  "mcpServers": {
    "your-server-name": {
      "command": "npx",
      "args": ["-y", "@scope/package-name"],
      "env": {
        "API_KEY": "value"
      }
    }
  }
}
```

### Format 2: GitHub Repository

Clone and run MCP servers directly from GitHub repositories, running the source code.

```json
{
  "github_token": "your-default-token",
  "mcpServers": {
    "python-server": {
      "github_repo": "modelcontextprotocol/python-sdk",
      "github_token": "optional-specific-token",
      "branch": "main",
      "command": "uv",
      "args": ["run", "examples/snippets/servers/fastmcp_quickstart.py"],
      "env": {}
    },
    "auto-detect-server": {
      "github_repo": "owner/repo",
      "branch": "main",
      "env": {}
    }
  }
}
```

**Features**:
- Automatically clones repos to `.fmcp-packages/owner/repo/branch/`
- **Two modes of operation**:
  - **Explicit command**: If `command` and `args` are provided, uses them directly (faster, no README parsing)
    - Example: `"command": "uv", "args": ["run", "path/to/script.py"]`
    - Example: `"command": "python", "args": ["-m", "module_name"]`
    - Example: `"command": "node", "args": ["path/to/server.js"]`
  - **Auto-extraction**: If no command specified, extracts metadata from README or existing metadata.json
- Supports per-server or default GitHub tokens
- Can mix with other configuration formats

### Format 3: Package String (Requires FluidMCP Registry)

Reference a package from the FluidMCP registry. The package will be installed first.

```json
{
  "mcpServers": {
    "your-server-name": "Author/Package@version"
  }
}
```

## Available MCP Servers for Testing

Here are some MCP servers you can use for testing (no API keys required):

- `@modelcontextprotocol/server-filesystem` - File system operations
- `@modelcontextprotocol/server-memory` - In-memory storage
- `@modelcontextprotocol/server-sqlite` - SQLite database operations
- `@modelcontextprotocol/server-puppeteer` - Web browser automation

Servers requiring API keys:
- `@google-maps/mcp-server` - Google Maps (GOOGLE_MAPS_API_KEY)
- `@modelcontextprotocol/server-brave-search` - Brave Search (BRAVE_API_KEY)
- `@modelcontextprotocol/server-slack` - Slack integration (SLACK_BOT_TOKEN)

## Notes

- Replace `/tmp/test-directory` with any directory path you want to test with
- Never commit files containing real API keys to the repository
- The examples use `npx -y` to automatically install and run packages
