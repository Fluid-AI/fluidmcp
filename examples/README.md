# FluidMCP Examples

This directory contains sample configuration files for testing and development.

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

**Use case**: Testing GitHub repository cloning and automatic metadata extraction.

**Usage**:
```bash
# Replace the GitHub token in the file first
# Edit sample-github-config.json and add your GitHub personal access token

# Run with FluidMCP
fluidmcp run examples/sample-github-config.json --file --start-server
```

**Servers included**:
- `mcp-server-time`: MCP server cloned from GitHub (auto-extracts command from README)

**Note**: GitHub repositories are automatically cloned to `.fmcp-packages/owner/repo/branch/`. FluidMCP automatically extracts metadata from the README if no metadata.json exists.

### 4. `sample-github-with-command.json`
A configuration demonstrating GitHub servers with explicit command specification.

**Use case**: Running GitHub MCP servers when you already know the command (skips README extraction).

**Features**:
- **Mode 1 (Explicit Command)**: When `command` and `args` are provided, FluidMCP uses them directly without parsing README
- **Mode 2 (Auto-extraction)**: When no command specified, FluidMCP extracts from README (same as sample-github-config.json)

**Usage**:
```bash
# Replace the GitHub token in the file first
fluidmcp run examples/sample-github-with-command.json --file --start-server
```

**Servers included**:
- `github-with-command`: Uses explicit command `npx -y @modelcontextprotocol/server-time`
- `github-auto-extract`: Auto-extracts command from README

**When to use explicit commands**:
- You know the exact command to run the MCP server
- The README format is non-standard or missing
- You want faster startup (skips README parsing)
- You want to override the default command from the repository

### 5. `sample-mixed-config.json`
A configuration demonstrating all three server types in one file.

**Use case**: Running registry packages, direct commands, and GitHub repos together.

**Servers included**:
- `filesystem`: Direct command configuration
- `github-mcp`: GitHub repository (auto-extracts from README)

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

## Quick Start for Developers

### Testing Basic Functionality

```bash
# 1. Create test directory
mkdir -p /tmp/test-directory

# 2. Run the sample config
fluidmcp run examples/sample-config.json --file --start-server

# 3. In another terminal, test the endpoint
curl http://localhost:8099/filesystem/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

### Testing GitHub Repositories

```bash
# Run a GitHub MCP server directly from the command line
fluidmcp github modelcontextprotocol/servers \
  --github-token YOUR_GITHUB_TOKEN \
  --branch main \
  --start-server

# Or use a config file
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

Clone and run MCP servers directly from GitHub repositories.

```json
{
  "github_token": "your-default-token",
  "mcpServers": {
    "your-github-server": {
      "github_repo": "owner/repo",
      "github_token": "optional-specific-token",
      "branch": "main",
      "command": "npx",
      "args": ["-y", "@scope/package-name"],
      "env": {
        "API_KEY": "value"
      }
    }
  }
}
```

**Features**:
- Automatically clones repos to `.fmcp-packages/owner/repo/branch/`
- **Two modes of operation**:
  - **Explicit command**: If `command` and `args` are provided, uses them directly (faster, no README parsing)
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
