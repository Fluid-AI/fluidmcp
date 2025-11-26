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

**Use case**: Testing GitHub repository cloning and running.

**Usage**:
```bash
# Replace the GitHub token in the file first
# Edit sample-github-config.json and add your GitHub personal access token

# Run with FluidMCP
fluidmcp run examples/sample-github-config.json --file --start-server
```

**Servers included**:
- `mcp-server-time`: MCP server cloned from GitHub

**Note**: GitHub repositories are automatically cloned to `.fmcp-packages/owner/repo/branch/`. If no metadata.json exists, FluidMCP extracts it from the README.

### 4. `sample-mixed-config.json`
A configuration demonstrating all three server types in one file.

**Use case**: Running registry packages, direct commands, and GitHub repos together.

**Servers included**:
- `filesystem`: Direct command configuration
- `github-mcp`: GitHub repository

**Note**: You can set a default `github_token` at the top level of the config, which will be used for all GitHub servers that don't specify their own token.

### 5. `sample-config-with-api-keys.json`
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
      "env": {
        "API_KEY": "value"
      }
    }
  }
}
```

**Features**:
- Automatically clones repos to `.fmcp-packages/owner/repo/branch/`
- Extracts metadata from README if metadata.json doesn't exist
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

## Environment Variable Handling

FluidMCP provides flexible environment variable management with automatic inheritance and override capabilities.

### How Environment Variables Work

When FluidMCP launches an MCP server, it merges environment variables from two sources:

1. **System/Docker Environment Variables** - All environment variables from your shell, Docker container, or system
2. **Configuration File Variables** - Variables specified in the `env` object of your configuration

```python
# Internal behavior (package_launcher.py:68-69)
env_vars = servers.get("env", {})
env = {**dict(os.environ), **env_vars}  # Config overrides system
```

**Key behavior**: Configuration variables **override** system variables when there's a conflict.

### Example Scenarios

#### Scenario 1: Using Docker ENV as Defaults

Set common defaults in your Dockerfile:

```dockerfile
ENV NODE_ENV=production
ENV LOG_LEVEL=info
ENV OPENAI_API_KEY=default_key
```

Use minimal config - environment variables are automatically inherited:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "env": {
        "ALLOWED_DIRECTORY": "/tmp"
      }
    }
  }
}
```

**MCP server receives:**
- `NODE_ENV=production` ✓ (from Docker)
- `LOG_LEVEL=info` ✓ (from Docker)
- `OPENAI_API_KEY=default_key` ✓ (from Docker)
- `ALLOWED_DIRECTORY=/tmp` ✓ (from config)

#### Scenario 2: Overriding Docker/System Variables

Docker provides default, but config overrides for production:

```dockerfile
ENV OPENAI_API_KEY=dev_key_12345
```

```json
{
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "OPENAI_API_KEY": "prod_key_67890"
      }
    }
  }
}
```

**MCP server receives:**
- `OPENAI_API_KEY=prod_key_67890` ✓ (config overrides Docker)

#### Scenario 3: No env Section Needed

If all required environment variables are set in Docker/system:

```bash
export GOOGLE_MAPS_API_KEY=your_key
export ALLOWED_DIR=/tmp/test
```

```json
{
  "mcpServers": {
    "google-maps": {
      "command": "npx",
      "args": ["-y", "@google-maps/mcp-server"]
    }
  }
}
```

**MCP server receives all environment variables from the system automatically.**

### Best Practices

✅ **Set common/default values in Docker ENV or system environment**
```dockerfile
ENV NODE_ENV=production
ENV LOG_LEVEL=info
ENV DEFAULT_TIMEOUT=30000
```

✅ **Use config for server-specific or override values**
```json
{
  "env": {
    "API_KEY": "server_specific_key",
    "CUSTOM_SETTING": "special_value"
  }
}
```

✅ **Omit the env section entirely if system variables are sufficient**
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"]
    }
  }
}
```

❌ **Don't duplicate environment variables unnecessarily**
```json
// If already set in Docker/system, no need to repeat:
{
  "env": {
    "NODE_ENV": "production"  // Not needed if in Docker
  }
}
```

### Docker-Specific Patterns

When using FluidMCP in Docker with the entrypoint script:

```dockerfile
# Set defaults in Dockerfile
ENV NODE_ENV=production
ENV LOG_LEVEL=info

# Or pass at runtime
docker run -e OPENAI_API_KEY=your_key \
           -e CUSTOM_VAR=value \
           fluidmcp
```

The `entrypoint.sh` script automatically passes all Docker environment variables to FluidMCP, which then merges them with config variables before launching MCP servers.

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
