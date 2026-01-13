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
- `examples/sample-oauth.json` - Full OAuth configuration example
- `examples/sample-oauth-minimal.json` - Minimal OAuth configuration
- `examples/sample-keycloak.json` - Simplified Keycloak configuration format
- `examples/keycloak-setup-guide.md` - Comprehensive Keycloak setup guide

## OAuth 2.0 (OIDC) Authentication

FluidMCP supports OAuth 2.0 authentication with Keycloak using JWT validation. FluidMCP acts as a **resource server** that validates JWT access tokens - it does NOT implement OAuth callback endpoints (those are handled by external clients like ChatGPT Apps SDK).

### Architecture Overview

**Resource Server Pattern:**
- External clients (ChatGPT, Apps SDK, curl) obtain JWT tokens from Keycloak
- FluidMCP validates JWT tokens using OIDC discovery and JWKS
- No custom OAuth callback endpoints (ChatGPT handles OAuth flows)
- Stateless JWT validation for scalability

**Key Features:**
- JWT signature validation using JWKS public keys
- Claims validation: expiry, audience, issuer, scopes
- Token caching (5-minute TTL) for performance
- JWKS caching (1-hour TTL)
- Bearer token fallback for backward compatibility
- MCP metadata endpoint for OAuth configuration

### Authentication Module Structure

All authentication code is organized in `fluidmcp/cli/auth/`:

```
fluidmcp/cli/auth/
├── __init__.py              # Package exports
├── config.py                # OAuth configuration models and loading
├── oidc_discovery.py        # OIDC discovery client (fetch JWKS, issuer)
├── jwt_validator.py         # JWT signature and claims validation
├── token_cache.py           # Token validation result caching
├── jwks_cache.py            # JWKS public key caching
├── middleware.py            # FastAPI authentication middleware
└── mcp_metadata.py          # MCP resource metadata endpoint
```

### Supported Grant Types

1. **Client Credentials (M2M)**: Machine-to-machine authentication
2. **Authorization Code + PKCE**: User authentication via external clients (ChatGPT, web apps)

Note: FluidMCP only **validates** tokens from these flows. External clients handle the OAuth authorization process.

### Configuration

Create `.oauth.json` in the same directory as your MCP configuration file:

**Full Configuration:**
```json
{
  "oauth": {
    "enabled": true,
    "provider": "keycloak",
    "keycloak": {
      "server_url": "https://keycloak.example.com",
      "realm": "mcp-realm",
      "well_known_url": "https://keycloak.example.com/realms/mcp-realm/.well-known/openid-configuration"
    },
    "jwt_validation": {
      "validate_signature": true,
      "validate_expiry": true,
      "validate_audience": true,
      "audience": ["fluidmcp-gateway"],
      "required_scopes": ["mcp:read", "mcp:write"],
      "issuer": "https://keycloak.example.com/realms/mcp-realm"
    },
    "caching": {
      "enable_token_cache": true,
      "token_cache_ttl_seconds": 300,
      "enable_jwks_cache": true,
      "jwks_cache_ttl_seconds": 3600
    },
    "fallback_to_bearer": true
  }
}
```

**Minimal Configuration** (uses sensible defaults):
```json
{
  "oauth": {
    "enabled": true,
    "provider": "keycloak",
    "keycloak": {
      "server_url": "https://keycloak.example.com",
      "realm": "mcp-realm"
    },
    "jwt_validation": {
      "audience": ["fluidmcp-gateway"]
    }
  }
}
```

**Simplified Keycloak Format** (`.keycloak.json`):
```json
{
  "keycloak": {
    "server_url": "https://keycloak.example.com",
    "realm": "mcp-realm",
    "audience": ["fluidmcp-gateway"]
  }
}
```

### Configuration Discovery

FluidMCP auto-discovers OAuth configuration in this order:

1. `FMCP_OAUTH_CONFIG` environment variable
2. Same directory as main config (`.oauth.json` or `.keycloak.json`)
3. `~/.fmcp/.oauth.json`
4. `./.fmcp/.oauth.json`

### Usage Examples

#### Client Credentials Flow (M2M)

```bash
# Step 1: Get JWT from Keycloak
TOKEN=$(curl -X POST https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=machine-client" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "scope=mcp:read mcp:write" \
  | jq -r '.access_token')

# Step 2: Run FluidMCP with OAuth
fluidmcp run examples/sample-config.json --file --start-server

# Step 3: Use JWT with FluidMCP
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

#### Authorization Code + PKCE Flow

External clients (ChatGPT, web apps) handle the authorization flow and present the JWT to FluidMCP:

```bash
# External client obtains JWT via Authorization Code + PKCE
# (handled by ChatGPT Apps SDK or custom implementation)

# Client presents JWT to FluidMCP
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Authorization: Bearer $OBTAINED_JWT" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

### MCP Metadata Endpoint

FluidMCP exposes OAuth configuration for MCP clients:

```bash
curl http://localhost:8099/.well-known/mcp-oauth-config | jq
```

**Response:**
```json
{
  "authorization_endpoint": "https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/auth",
  "token_endpoint": "https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/token",
  "issuer": "https://keycloak.example.com/realms/mcp-realm",
  "jwks_uri": "https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/certs",
  "supported_grant_types": ["authorization_code", "client_credentials"],
  "pkce_required": true,
  "scopes_supported": ["openid", "mcp:read", "mcp:write"],
  "audience": ["fluidmcp-gateway"],
  "required_scopes": ["mcp:read", "mcp:write"]
}
```

### Authentication Status Endpoint

Check current authentication configuration:

```bash
curl http://localhost:8099/.well-known/auth-status | jq
```

### Keycloak Setup

FluidMCP requires specific Keycloak configuration:

**Critical Requirements:**
1. **Audience Mapper**: Must be configured on each client scope to add `aud` claim
   - Without this, JWT validation will fail with "Invalid audience"
2. **Client Scopes**: Create `mcp:read` and `mcp:write` scopes
3. **M2M Client**: Configure with Client Credentials grant
4. **Web Client**: Configure with Authorization Code flow and PKCE (S256)

**Detailed Setup Guide:** See [examples/keycloak-setup-guide.md](examples/keycloak-setup-guide.md)

### JWT Validation Process

FluidMCP validates JWTs in this order:

1. **Check token cache** (5-minute TTL) - Fast path (~0.1ms)
2. **Decode JWT header** - Extract `kid` (key ID)
3. **Fetch public key** - From JWKS cache using `kid`
4. **Verify signature** - Using RS256/ES256 public key (~1-2ms)
5. **Validate claims**:
   - `exp` (expiry): Token not expired
   - `aud` (audience): Must match configured audience
   - `iss` (issuer): Must match Keycloak issuer
   - `scope`: Must contain required scopes
6. **Cache result** - Store validated claims for 5 minutes
7. **Return claims** - Allow request through

### Performance Characteristics

- **Token cache hit**: ~0.1ms (immediate return)
- **Token cache miss**: ~1-2ms (full JWT validation)
- **JWKS cache hit**: ~0.5ms (public key lookup)
- **JWKS cache miss**: ~50-100ms (fetch from Keycloak, happens once per hour)

### Backward Compatibility

OAuth is completely opt-in:
- No OAuth config = No OAuth validation (existing behavior preserved)
- `fallback_to_bearer: true` = Try bearer token if JWT validation fails
- Bearer token authentication still works independently

### Why No Token Introspection?

FluidMCP uses JWT validation instead of token introspection for:

1. **Performance**: JWT validation is local (~1-2ms) vs introspection network call (~50-100ms)
2. **Scalability**: No dependency on Keycloak availability after JWKS cached
3. **Standard practice**: JWT validation is the norm for OAuth 2.0 resource servers

**Token revocation**: Use short-lived JWTs (5-15 minutes) + token cache TTL for effective revocation.

### Security Considerations

1. **HTTPS Required**: Always use HTTPS in production for Keycloak and FluidMCP
2. **Short Token Lifetimes**: 15-minute access tokens + 5-minute cache = effective revocation
3. **Audience Validation**: Prevents token reuse across different APIs
4. **Scope Validation**: Enforces fine-grained permissions
5. **No Secrets in FluidMCP**: Client secrets stay with OAuth clients, not resource servers

### Troubleshooting

**"Invalid audience" error:**
- Ensure audience mapper is configured in Keycloak client scopes
- Verify `audience` in `.oauth.json` matches mapper configuration

**"Missing required scopes" error:**
- Ensure client scopes (`mcp:read`, `mcp:write`) are added to client's default scopes
- Check token contains required scopes: `echo $TOKEN | cut -d. -f2 | base64 -d | jq`

**"Invalid issuer" error:**
- Verify `issuer` in `.oauth.json` matches Keycloak's `issuer` from discovery endpoint

**OIDC discovery fails:**
- Check Keycloak is accessible and well-known URL format is correct
- Format: `{server_url}/realms/{realm}/.well-known/openid-configuration`

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
