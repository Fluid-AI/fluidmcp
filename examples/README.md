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

**Use case**: Testing the `fluidmcp run --file` command.

**Usage**:
```bash
# Create the test directory first
mkdir -p /tmp/test-directory

# Run with FluidMCP
fluidmcp run examples/sample-config.json --file --start-server
```

**Servers included**:
- `filesystem`: File system operations server
- `memory`: In-memory storage server

### 3. `sample-config-with-api-keys.json`
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

You can create custom configurations based on these examples:

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
