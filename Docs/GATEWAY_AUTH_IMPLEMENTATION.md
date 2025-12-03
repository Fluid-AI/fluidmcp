# On-Demand Gateway Authentication Implementation

## Overview

FluidMCP has been upgraded with **on-demand gateway-based OAuth 2.0 authentication**. Instead of requiring users to authenticate via CLI before starting the server, the FastAPI Gateway (running on localhost:8099) now hosts authentication endpoints that enable dynamic, on-demand authentication.

## Architecture Changes

### Previous Architecture (CLI-based)
```
User → CLI → OAuth Flow → Token Storage (keyring/file) → Start Server
```

### New Architecture (Gateway-based)
```
User/LLM → Gateway Login Endpoint → OAuth Flow → Return Token → Client holds token
          → Use token in API requests with Authorization header
```

## Key Components

### 1. `fluidai_mcp/services/oauth_service.py` (Refactored)

**Purpose**: Stateless helper service for OAuth 2.0 PKCE flow

**Key Functions**:
- `generate_pkce_pair()` - Generates PKCE verifier and challenge
- `build_authorization_url()` - Constructs OAuth authorization URL with PKCE
- `exchange_code_for_token()` - Exchanges authorization code for access token
- `get_env_var()` - Helper to retrieve environment variables

**Changes**:
- ✅ No longer uses keyring or file storage
- ✅ All functions are stateless
- ✅ Tokens are returned to the client to manage

### 2. `fluidai_mcp/services/package_launcher.py` (Enhanced)

**Purpose**: Launch MCP servers and create FastAPI routers with dynamic auth endpoints

**Key Changes**:

#### Global State Management
```python
# In-memory storage for pending OAuth states
pending_auth_states: Dict[str, Dict[str, Any]] = {}
```

#### Enhanced Function Signature
```python
def launch_mcp_using_fastapi_proxy(dest_dir: Union[str, Path]):
    # Now returns 3 values instead of 2
    return pkg, router, server_config  # server_config is new
```

#### Dynamic Auth Route Creation
When a package has an `"auth"` block in `metadata.json`, two endpoints are automatically created:

**1. Login Endpoint**: `GET /{package_name}/auth/login`
- Generates PKCE verifier/challenge
- Creates random state for CSRF protection
- Stores verifier in-memory with state key
- Redirects user to OAuth provider

**2. Callback Endpoint**: `GET /{package_name}/auth/callback`
- Receives authorization code and state
- Retrieves stored verifier
- Exchanges code for access token
- Returns token to client as JSON

#### Token Detection in Proxy
```python
@router.post(f"/{package_name}/mcp")
async def proxy_jsonrpc(request_obj: Request, ...):
    # Check for Authorization header
    auth_header = request_obj.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        bearer_token = auth_header[7:]
        logger.info(f"Received authenticated request for {package_name}")
```

### 3. `fluidai_mcp/services/run_servers.py` (Updated)

**Changes**:
- Updated to handle new 3-value return from `launch_mcp_using_fastapi_proxy`
- Removed old CLI-based OAuth token injection logic
- Added logging for packages with OAuth configuration
- Displays login URL when server starts

### 4. `fluidai_mcp/cli.py` (Updated)

**Changes**:
- `fluidmcp auth` command now provides gateway authentication instructions
- Removed dependency on old OAuth service functions
- Guides users to use gateway endpoints instead

## Usage Guide

### For Package Authors

Add an `"auth"` block to your package's `metadata.json`:

```json
{
  "mcpServers": {
    "gmail-mock": {
      "command": "echo",
      "args": ["Gmail MCP Started with Token: "],
      "auth": {
        "type": "oauth2",
        "flow": "pkce",
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        "client_id_env": "GOOGLE_CLIENT_ID",
        "env_var_name": "GMAIL_ACCESS_TOKEN"
      }
    }
  }
}
```

### For End Users

#### 1. Install and Start the Server
```bash
fluidmcp install test/gmail-mock@1.0.0
fluidmcp run test/gmail-mock@1.0.0 --start-server
```

#### 2. Authenticate via Browser
```
Visit: http://localhost:8099/gmail-mock/auth/login
```

This will:
- Redirect you to the OAuth provider
- After you grant permissions, redirect back to the callback endpoint
- Return your access token as JSON

**Example Response**:
```json
{
  "success": true,
  "package": "gmail-mock",
  "token_data": {
    "access_token": "ya29.a0AfH6SMB...",
    "refresh_token": "1//0gW...",
    "expires_in": 3600,
    "token_type": "Bearer"
  },
  "message": "Authentication successful! Use the access_token in Authorization header."
}
```

#### 3. Use the Token in API Requests
```bash
curl -X POST http://localhost:8099/gmail-mock/mcp \
  -H "Authorization: Bearer ya29.a0AfH6SMB..." \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
  }'
```

### For LLM/MCP Clients

#### Step 1: Discover Authentication Requirements
```http
GET http://localhost:8099/docs
```

Look for packages with `/auth/login` endpoints in the Swagger documentation.

#### Step 2: Trigger Authentication
```http
GET http://localhost:8099/{package}/auth/login
```

This will redirect to the OAuth provider. The user completes authentication in their browser.

#### Step 3: Receive Token
After OAuth callback, the client receives:
```json
{
  "success": true,
  "package": "gmail-mock",
  "token_data": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_in": 3600
  }
}
```

#### Step 4: Use Token in Requests
```http
POST http://localhost:8099/{package}/mcp
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
```

## API Endpoints

### Standard Endpoints (All Packages)
- `POST /{package}/mcp` - JSON-RPC proxy to MCP server
- `POST /{package}/sse` - Server-Sent Events streaming
- `GET /{package}/mcp/tools/list` - List available tools
- `POST /{package}/mcp/tools/call` - Call a specific tool

### OAuth Endpoints (Packages with auth config)
- `GET /{package}/auth/login` - Initiate OAuth flow
- `GET /{package}/auth/callback` - OAuth callback handler

### Documentation
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc documentation

## Security Considerations

### PKCE (Proof Key for Code Exchange)
- Protects against authorization code interception
- Verifier stored server-side, challenge sent to OAuth provider
- State parameter prevents CSRF attacks

### Token Management
- Tokens are returned to the client (not stored server-side)
- Client is responsible for secure token storage
- Tokens should be treated as sensitive credentials

### Authorization Headers
- Gateway detects `Authorization: Bearer <token>` headers
- Logs when authenticated requests are received
- Future enhancement: Inject tokens into MCP subprocess environment

## Environment Variables

### Required for OAuth-enabled Packages
```bash
# Example for Gmail integration
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"

# Optional: Client secret if required by provider
export GOOGLE_CLIENT_SECRET="your-client-secret"
```

### Gateway Configuration
```bash
# Port configuration
MCP_CLIENT_SERVER_PORT=8090        # Single package port
MCP_CLIENT_SERVER_ALL_PORT=8099    # Unified gateway port

# Legacy auth modes (not related to package OAuth)
FMCP_SECURE_MODE=true              # Simple bearer token auth
FMCP_BEARER_TOKEN=your_token       # Bearer token value
FMCP_OAUTH_MODE=true               # System-wide OAuth2 PKCE
```

## Testing

### Test the gmail-mock Package

1. **Set up environment**:
```bash
export GOOGLE_CLIENT_ID="your-test-client-id"
```

2. **Start the server**:
```bash
fluidmcp run test/gmail-mock@1.0.0 --start-server
```

3. **Test the login flow**:
```bash
# Open in browser
open http://localhost:8099/gmail-mock/auth/login
```

4. **Verify endpoints**:
```bash
# View API documentation
open http://localhost:8099/docs

# Test authenticated request
curl -X POST http://localhost:8099/gmail-mock/mcp \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Migration Guide

### For Existing Package Users

**Before** (CLI-based auth):
```bash
fluidmcp auth test/gmail-mock@1.0.0
fluidmcp run test/gmail-mock@1.0.0 --start-server
```

**After** (Gateway-based auth):
```bash
# Just start the server
fluidmcp run test/gmail-mock@1.0.0 --start-server

# Authenticate via browser when needed
open http://localhost:8099/gmail-mock/auth/login
```

### Benefits of New Approach

1. **No Pre-authentication Required**: Users don't need to auth before starting the server
2. **Client-Managed Tokens**: Tokens are returned to the client for flexible management
3. **Multi-User Support**: Different clients can authenticate independently
4. **Better for LLMs**: LLMs can trigger auth flows programmatically
5. **REST-ful**: Follows standard OAuth 2.0 web flow patterns

## Future Enhancements

1. **Token Injection**: Automatically inject tokens into MCP subprocess environment
2. **Token Refresh**: Implement automatic token refresh using refresh_token
3. **Multiple Auth Providers**: Support for different OAuth providers per package
4. **Token Validation**: Validate tokens before proxying to MCP server
5. **Token Revocation**: Endpoint to revoke/clear tokens

## Troubleshooting

### "client_id not found" Error
- Ensure the required environment variable is set (check `client_id_env` in metadata.json)
- Example: `export GOOGLE_CLIENT_ID="your-id"`

### "Invalid or expired state parameter"
- State is stored in-memory and cleared after use
- Don't refresh the callback page
- Restart the auth flow if this occurs

### OAuth Provider Errors
- Check that redirect_uri matches your gateway: `http://localhost:8099/{package}/auth/callback`
- Verify scopes are correct in metadata.json
- Ensure OAuth client is properly configured with your provider

## Summary

The on-demand gateway authentication architecture provides a modern, flexible approach to OAuth 2.0 authentication in FluidMCP. By moving authentication to the gateway level, we enable:

- Dynamic, on-demand authentication
- Client-managed tokens
- Better integration with LLMs and MCP clients
- Simplified user experience
- Standards-compliant OAuth 2.0 PKCE flow

All authentication is now handled through REST endpoints, making it easy for any HTTP client (including LLMs) to authenticate and use MCP packages that require OAuth.
