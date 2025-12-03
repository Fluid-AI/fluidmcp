# Package-Specific OAuth 2.0 Authentication

FluidMCP supports package-specific OAuth 2.0 authentication, allowing individual MCP packages to authenticate with third-party services like Gmail, Jira, GitHub, etc.

## Overview

This feature enables:
- **Per-Package Authentication**: Each package manages its own OAuth tokens
- **PKCE Support**: Enhanced security using Proof Key for Code Exchange (RFC 7636)
- **Automatic Token Refresh**: Tokens are refreshed automatically when expired
- **Secure Storage**: Uses system keyring with fallback to encrypted local file
- **Headless Support**: Works in Docker, Codespaces, and other headless environments

## Difference from System-Wide OAuth

FluidMCP now supports **two types** of OAuth authentication:

| Feature | System-Wide OAuth | Package-Specific OAuth |
|---------|------------------|----------------------|
| **Commands** | `fluidmcp login/logout` | `fluidmcp auth <package>` |
| **Use Case** | Authenticate API gateway | Authenticate MCP packages |
| **Scope** | Protects all endpoints | Package-specific access |
| **Storage** | `~/.fluidmcp/oauth/tokens.json` | System keyring or `~/.fluidmcp/tokens.json` |
| **Documentation** | See OAuth2_SETUP.md | This document |

## Quick Start

### 1. Install a Package with OAuth Support

```bash
fluidmcp install gmail/gmail-mcp@1.0.0
```

### 2. Authenticate the Package

```bash
fluidmcp auth gmail/gmail-mcp
```

This will:
- Open your browser to the OAuth provider
- Request necessary permissions
- Store tokens securely
- Automatically refresh when needed

### 3. Run the Package

```bash
fluidmcp run gmail/gmail-mcp --start-server
```

The access token will be automatically injected into the package's environment.

## Package Configuration

To add OAuth support to your MCP package, add an `auth` block to `metadata.json`:

```json
{
  "mcpServers": {
    "your-package": {
      "command": "node",
      "args": ["server.js"],
      "env": {},
      "auth": {
        "authorization_url": "https://provider.com/oauth/authorize",
        "token_url": "https://provider.com/oauth/token",
        "client_id": "your-client-id",
        "scopes": ["read", "write"],
        "token_env_key": "ACCESS_TOKEN"
      }
    }
  }
}
```

### Configuration Fields

#### Required Fields

- **`authorization_url`**: OAuth provider's authorization endpoint
  - Example: `"https://accounts.google.com/o/oauth2/v2/auth"`

- **`token_url`**: OAuth provider's token endpoint
  - Example: `"https://oauth2.googleapis.com/token"`

- **`scopes`**: Array of OAuth scopes to request
  - Example: `["https://www.googleapis.com/auth/gmail.readonly"]`

#### OAuth Credentials (at least one required)

- **`client_id`**: OAuth client ID (hardcoded)
- **`client_id_env`**: Environment variable containing client ID
  - Recommended for security: `"client_id_env": "GMAIL_CLIENT_ID"`

- **`client_secret`**: OAuth client secret (hardcoded, not recommended)
- **`client_secret_env`**: Environment variable containing client secret
  - Example: `"client_secret_env": "GMAIL_CLIENT_SECRET"`

#### Optional Fields

- **`token_env_key`**: Environment variable name for the access token
  - Default: `"ACCESS_TOKEN"`
  - Example: `"GMAIL_ACCESS_TOKEN"`

## Real-World Examples

### Gmail MCP Package

```json
{
  "mcpServers": {
    "gmail": {
      "command": "node",
      "args": ["gmail-server.js"],
      "auth": {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "client_id_env": "GMAIL_CLIENT_ID",
        "client_secret_env": "GMAIL_CLIENT_SECRET",
        "scopes": [
          "https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/gmail.send"
        ],
        "token_env_key": "GMAIL_ACCESS_TOKEN"
      }
    }
  }
}
```

**Setup:**
```bash
export GMAIL_CLIENT_ID="123456.apps.googleusercontent.com"
export GMAIL_CLIENT_SECRET="your-secret"
fluidmcp auth gmail/gmail-mcp
fluidmcp run gmail/gmail-mcp --start-server
```

### GitHub MCP Package

```json
{
  "mcpServers": {
    "github": {
      "command": "python",
      "args": ["github_server.py"],
      "auth": {
        "authorization_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "client_id_env": "GITHUB_CLIENT_ID",
        "client_secret_env": "GITHUB_CLIENT_SECRET",
        "scopes": ["repo", "read:user"],
        "token_env_key": "GITHUB_TOKEN"
      }
    }
  }
}
```

**Setup:**
```bash
export GITHUB_CLIENT_ID="your-github-oauth-app-id"
export GITHUB_CLIENT_SECRET="your-secret"
fluidmcp auth github/github-mcp
fluidmcp run github/github-mcp --start-server
```

### Jira MCP Package

```json
{
  "mcpServers": {
    "jira": {
      "command": "node",
      "args": ["jira-server.js"],
      "auth": {
        "authorization_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "client_id_env": "JIRA_CLIENT_ID",
        "client_secret_env": "JIRA_CLIENT_SECRET",
        "scopes": ["read:jira-work", "write:jira-work"],
        "token_env_key": "JIRA_ACCESS_TOKEN"
      }
    }
  }
}
```

## CLI Commands

### Authenticate a Package

```bash
# Authenticate with short package name (searches installed packages)
fluidmcp auth gmail

# Authenticate with full package identifier
fluidmcp auth author/package@version

# Force re-authentication (even if already authenticated)
fluidmcp auth gmail --force
```

### Run Authenticated Packages

```bash
# Run single package (token automatically injected)
fluidmcp run gmail --start-server

# Run all packages (authenticated packages get tokens)
fluidmcp run all --start-server

# If package requires auth but isn't authenticated:
# ⚠ Warning: No valid OAuth token for 'gmail'
# Please authenticate first using: fluidmcp auth gmail
# Skipping server 'gmail'
```

## Token Storage

### Primary: System Keyring

Tokens are stored in your operating system's secure keyring:

- **macOS**: Keychain Access
- **Linux**: GNOME Keyring, KWallet (via Secret Service API)
- **Windows**: Windows Credential Manager

Service name: `fluidmcp`
Username: `fluidmcp-{package_name}`

### Fallback: Encrypted File

If the system keyring is unavailable (common in Docker/Codespaces):

**Location**: `~/.fluidmcp/tokens.json`

**Permissions**: `0600` (owner read/write only)

**Format**:
```json
{
  "gmail_gmail-mcp": {
    "access_token": "ya29.a0...",
    "refresh_token": "1//0...",
    "expires_in": 3600,
    "created_at": 1234567890.123,
    "auth_config": {
      "authorization_url": "...",
      "token_url": "...",
      "scopes": ["..."]
    }
  }
}
```

## Token Lifecycle

### 1. Initial Authentication

```
┌──────────────┐
│ User runs    │
│ auth command │
└──────┬───────┘
       │
       v
┌──────────────┐
│ Generate     │
│ PKCE pair    │
└──────┬───────┘
       │
       v
┌──────────────┐
│ Open browser │
│ (port 8888)  │
└──────┬───────┘
       │
       v
┌──────────────┐
│ User         │
│ authorizes   │
└──────┬───────┘
       │
       v
┌──────────────┐
│ Callback     │
│ with code    │
└──────┬───────┘
       │
       v
┌──────────────┐
│ Exchange for │
│ tokens       │
└──────┬───────┘
       │
       v
┌──────────────┐
│ Store in     │
│ keyring/file │
└──────────────┘
```

### 2. Running with Token

```
┌──────────────┐
│ User runs    │
│ package      │
└──────┬───────┘
       │
       v
┌──────────────┐
│ Check        │
│ metadata     │
└──────┬───────┘
       │
   ┌───┴───┐
   │ Auth? │
   └───┬───┘
       │ Yes
       v
┌──────────────┐
│ Get token    │
│ from storage │
└──────┬───────┘
       │
   ┌───┴────┐
   │Expired?│
   └───┬────┘
       │ Yes
       v
┌──────────────┐
│ Refresh      │
│ token        │
└──────┬───────┘
       │
       v
┌──────────────┐
│ Inject into  │
│ environment  │
└──────┬───────┘
       │
       v
┌──────────────┐
│ Launch       │
│ server       │
└──────────────┘
```

### 3. Automatic Token Refresh

Tokens are automatically refreshed when:
- Expiration is within 60 seconds
- `get_valid_token()` is called
- A valid refresh token exists

**Refresh process:**
1. Use stored refresh token
2. Call provider's token endpoint
3. Receive new access token (and possibly new refresh token)
4. Update stored tokens
5. Return new access token

## Security Best Practices

### 1. Never Hardcode Secrets

❌ **Bad:**
```json
{
  "auth": {
    "client_id": "123456",
    "client_secret": "secret123"
  }
}
```

✅ **Good:**
```json
{
  "auth": {
    "client_id_env": "GMAIL_CLIENT_ID",
    "client_secret_env": "GMAIL_CLIENT_SECRET"
  }
}
```

### 2. Use Environment Variables

```bash
# In ~/.bashrc or ~/.zshrc
export GMAIL_CLIENT_ID="your-id"
export GMAIL_CLIENT_SECRET="your-secret"

# Or in a .env file (add to .gitignore!)
echo "GMAIL_CLIENT_ID=your-id" >> .env
echo "GMAIL_CLIENT_SECRET=your-secret" >> .env
```

### 3. Limit OAuth Scopes

Only request scopes your package actually needs:

❌ **Bad:**
```json
{
  "scopes": ["*", "full_access"]
}
```

✅ **Good:**
```json
{
  "scopes": ["gmail.readonly", "gmail.send"]
}
```

### 4. Protect Token Files

The CLI automatically sets `~/.fluidmcp/tokens.json` to `0600`, but verify:

```bash
ls -la ~/.fluidmcp/tokens.json
# Should show: -rw------- (600)
```

### 5. Rotate Credentials Regularly

```bash
# Re-authenticate periodically
fluidmcp auth gmail --force
```

## Troubleshooting

### "Package does not require OAuth authentication"

Your package's `metadata.json` doesn't have an `auth` block. Add it following the configuration section above.

### "No valid OAuth token for 'package'"

You haven't authenticated yet:
```bash
fluidmcp auth package-name
```

### "client_id not found in auth config or environment"

Set the required environment variable:
```bash
export GMAIL_CLIENT_ID="your-client-id"
```

Or add `client_id` directly to metadata.json (not recommended).

### Browser Doesn't Open

The authorization URL is printed to the console. Copy and paste it manually:
```
Open this URL to authenticate: https://...
```

### "Authentication failed - no authorization code received"

Possible causes:
- Callback server timed out (took too long to authorize)
- Wrong redirect URI in OAuth app configuration
- Firewall blocking port 8888

**Solution**: Ensure your OAuth app's redirect URI includes:
```
http://localhost:8888/callback
```

### "Token refresh failed"

Your refresh token may be invalid or expired. Re-authenticate:
```bash
fluidmcp auth package-name --force
```

### Keyring Unavailable in Docker

This is expected behavior. The CLI automatically falls back to file storage:
```
Keyring unavailable (...), using file fallback
```

Check the file was created:
```bash
cat ~/.fluidmcp/tokens.json
```

### Permission Denied on Token File

Fix permissions:
```bash
chmod 600 ~/.fluidmcp/tokens.json
```

## Advanced Usage

### Custom Callback Server Behavior

The OAuth callback server:
- Listens on `localhost:8888`
- Waits indefinitely for callback (no timeout)
- Handles one request then shuts down
- Shows success/error page to user

### Manual Token Management

If you need to manually manage tokens:

```python
from fluidai_mcp.services.token_storage import save_token, get_token, delete_token

# Save tokens
save_token("package_name", {
    "access_token": "...",
    "refresh_token": "...",
    "expires_in": 3600,
    "created_at": time.time(),
    "auth_config": {...}
})

# Retrieve tokens
tokens = get_token("package_name")
print(tokens["access_token"])

# Delete tokens
delete_token("package_name")
```

### Debug Mode

Enable detailed logging:
```bash
export LOGURU_LEVEL=DEBUG
fluidmcp auth package-name
```

Output includes:
- PKCE verifier/challenge generation
- Authorization URL
- Token exchange requests/responses
- Token storage operations
- Refresh attempts

## Integration for Package Developers

### Step 1: Add Auth Config to Metadata

```json
{
  "mcpServers": {
    "your-package": {
      "command": "node",
      "args": ["server.js"],
      "auth": {
        "authorization_url": "https://provider.com/oauth/authorize",
        "token_url": "https://provider.com/oauth/token",
        "client_id_env": "YOUR_PACKAGE_CLIENT_ID",
        "scopes": ["scope1", "scope2"],
        "token_env_key": "YOUR_PACKAGE_TOKEN"
      }
    }
  }
}
```

### Step 2: Read Token in Your Server

Your server receives the access token via environment variable:

**Node.js:**
```javascript
const accessToken = process.env.YOUR_PACKAGE_TOKEN;

// Use in API requests
fetch('https://api.provider.com/data', {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});
```

**Python:**
```python
import os

access_token = os.environ.get('YOUR_PACKAGE_TOKEN')

# Use in API requests
response = requests.get(
    'https://api.provider.com/data',
    headers={'Authorization': f'Bearer {access_token}'}
)
```

### Step 3: Document Setup for Users

Create a README with:
1. How to create OAuth app with provider
2. Required scopes
3. Environment variables to set
4. Authentication command

**Example:**

```markdown
## Setup

1. Create a Google OAuth app at https://console.cloud.google.com/
2. Add redirect URI: `http://localhost:8888/callback`
3. Enable Gmail API
4. Set environment variables:
   ```bash
   export GMAIL_CLIENT_ID="your-id"
   export GMAIL_CLIENT_SECRET="your-secret"
   ```
5. Authenticate:
   ```bash
   fluidmcp auth gmail/gmail-mcp
   ```
6. Run:
   ```bash
   fluidmcp run gmail/gmail-mcp --start-server
   ```
```

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────┐
│         fluidai_mcp/cli.py                  │
│  ┌──────────────────────────────────────┐   │
│  │  auth_command()                      │   │
│  │  - Parse package name                │   │
│  │  - Load metadata.json                │   │
│  │  - Call authenticate_package()       │   │
│  └──────────────────────────────────────┘   │
└─────────────────┬───────────────────────────┘
                  │
                  v
┌─────────────────────────────────────────────┐
│   fluidai_mcp/services/oauth_service.py     │
│  ┌──────────────────────────────────────┐   │
│  │  authenticate_package()              │   │
│  │  - Generate PKCE pair                │   │
│  │  - Start callback server (port 8888) │   │
│  │  - Open browser                      │   │
│  │  - Exchange code for tokens          │   │
│  │  - Call save_token()                 │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  get_valid_token()                   │   │
│  │  - Call get_token()                  │   │
│  │  - Check expiration                  │   │
│  │  - Call refresh_token() if needed    │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  refresh_token()                     │   │
│  │  - Use refresh_token                 │   │
│  │  - Call token endpoint               │   │
│  │  - Call save_token()                 │   │
│  └──────────────────────────────────────┘   │
└─────────────────┬───────────────────────────┘
                  │
                  v
┌─────────────────────────────────────────────┐
│   fluidai_mcp/services/token_storage.py     │
│  ┌──────────────────────────────────────┐   │
│  │  save_token()                        │   │
│  │  - Try system keyring                │   │
│  │  - Fallback to ~/.fluidmcp/tokens.json│  │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  get_token()                         │   │
│  │  - Try system keyring                │   │
│  │  - Fallback to ~/.fluidmcp/tokens.json│  │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Flow During `fluidmcp run`

```
┌─────────────────────────────────────────────┐
│   fluidai_mcp/services/run_servers.py       │
│  ┌──────────────────────────────────────┐   │
│  │  run_servers()                       │   │
│  │  - Loop through server configs       │   │
│  │  - Load metadata.json                │   │
│  │  - Check for 'auth' block            │   │
│  │  - If auth: call get_valid_token()   │   │
│  │  - Inject token into metadata env    │   │
│  │  - Write updated metadata            │   │
│  │  - Call launch_mcp_using_fastapi...  │   │
│  └──────────────────────────────────────┘   │
└─────────────────┬───────────────────────────┘
                  │
                  v
┌─────────────────────────────────────────────┐
│   fluidai_mcp/services/package_launcher.py  │
│  ┌──────────────────────────────────────┐   │
│  │  launch_mcp_using_fastapi_proxy()    │   │
│  │  - Load metadata.json                │   │
│  │  - Extract env vars (includes token) │   │
│  │  - Launch subprocess with env        │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## Future Enhancements

Potential improvements:
- Support for OAuth 2.0 Device Code Flow (TV/console apps)
- Support for OAuth 1.0a (Twitter API v1)
- Web UI for token management
- Token revocation on package uninstall
- Integration with external secret managers (Vault, AWS Secrets Manager)
- Support for custom redirect URIs and ports

## Related Documentation

- [OAuth2_SETUP.md](./OAuth2_SETUP.md) - System-wide OAuth for API gateway
- [README.md](./README.md) - General FluidMCP documentation
- [CLAUDE.md](./CLAUDE.md) - Development guide for Claude Code

## Contributing

When adding OAuth support to MCP packages:
1. Follow the metadata.json schema
2. Use `client_id_env` instead of hardcoded credentials
3. Request minimal scopes needed
4. Document the OAuth setup process
5. Test both initial auth and token refresh
6. Test in both system keyring and fallback mode

For issues or feature requests, please visit: https://github.com/Fluid-AI/fluidmcp
