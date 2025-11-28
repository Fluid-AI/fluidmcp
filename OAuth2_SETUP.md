# OAuth2 PKCE Authentication Setup

FluidMCP supports OAuth2 PKCE (Proof Key for Code Exchange) authentication to secure your FastAPI gateway endpoints. This guide explains how to set up and use OAuth2 authentication.

## Overview

OAuth2 PKCE provides secure authentication without requiring client secrets, making it ideal for CLI tools. FluidMCP supports two modes:

1. **Automatic Mode**: Browser-based login flow with token storage and automatic refresh
2. **Manual Mode**: Manually provide access tokens via environment variables

## Configuration

### 1. Set Up OAuth2 Provider

Configure your OAuth2 provider by setting environment variables:

```bash
# Required
export FMCP_OAUTH_AUTH_ENDPOINT="https://your-provider.com/oauth/authorize"
export FMCP_OAUTH_TOKEN_ENDPOINT="https://your-provider.com/oauth/token"
export FMCP_OAUTH_CLIENT_ID="your_client_id"

# Optional (defaults shown)
export FMCP_OAUTH_REDIRECT_URI="http://localhost:8088/callback"
export FMCP_OAUTH_SCOPE="openid profile email"
```

### 2. Common OAuth2 Providers

#### Auth0
```bash
export FMCP_OAUTH_AUTH_ENDPOINT="https://your-domain.auth0.com/authorize"
export FMCP_OAUTH_TOKEN_ENDPOINT="https://your-domain.auth0.com/oauth/token"
export FMCP_OAUTH_CLIENT_ID="your_client_id"
```

#### Okta
```bash
export FMCP_OAUTH_AUTH_ENDPOINT="https://your-domain.okta.com/oauth2/default/v1/authorize"
export FMCP_OAUTH_TOKEN_ENDPOINT="https://your-domain.okta.com/oauth2/default/v1/token"
export FMCP_OAUTH_CLIENT_ID="your_client_id"
```

#### Azure AD
```bash
export FMCP_OAUTH_AUTH_ENDPOINT="https://login.microsoftonline.com/your-tenant-id/oauth2/v2.0/authorize"
export FMCP_OAUTH_TOKEN_ENDPOINT="https://login.microsoftonline.com/your-tenant-id/oauth2/v2.0/token"
export FMCP_OAUTH_CLIENT_ID="your_client_id"
```

#### Google
```bash
export FMCP_OAUTH_AUTH_ENDPOINT="https://accounts.google.com/o/oauth2/v2/auth"
export FMCP_OAUTH_TOKEN_ENDPOINT="https://oauth2.googleapis.com/token"
export FMCP_OAUTH_CLIENT_ID="your_client_id"
```

## Usage

### Automatic Mode (Browser-Based Login)

1. **Login**
   ```bash
   fluidmcp login
   ```
   This will:
   - Open your browser for authentication
   - Store tokens securely in `~/.fluidmcp/oauth/tokens.json`
   - Automatically refresh tokens when needed

2. **Run servers with OAuth**
   ```bash
   fluidmcp run mypackage --start-server --oauth
   ```

3. **Logout**
   ```bash
   fluidmcp logout
   ```

### Manual Mode (Token Input)

If you prefer to manage tokens manually or are in a headless environment:

1. **Obtain an access token** from your OAuth provider

2. **Set the token as an environment variable**
   ```bash
   export FMCP_OAUTH_ACCESS_TOKEN="your_access_token_here"
   ```

3. **Run servers with OAuth**
   ```bash
   fluidmcp run mypackage --start-server --oauth
   ```

## Making Authenticated Requests

When OAuth2 is enabled, clients must include the access token in the `Authorization` header:

```bash
curl -X POST http://localhost:8090/mypackage/mcp \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

### Python Example

```python
import requests

access_token = "your_access_token"
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

response = requests.post(
    "http://localhost:8090/mypackage/mcp",
    headers=headers,
    json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list"
    }
)

print(response.json())
```

## Token Storage

Tokens are stored securely in:
```
~/.fluidmcp/oauth/tokens.json
```

This file contains:
- `access_token`: The current access token
- `refresh_token`: Token used to obtain new access tokens
- `expires_at`: ISO timestamp when the token expires

File permissions are set to `0600` (owner read/write only).

## Token Refresh

FluidMCP automatically refreshes access tokens when:
- The token is expired (checked 5 minutes before actual expiration)
- A refresh token is available

## Backward Compatibility

OAuth2 mode is completely optional. You can still use:
- **No authentication**: Run without `--secure` or `--oauth` flags
- **Simple bearer token**: Use `--secure` flag with optional `--token`

## Security Best Practices

1. **Never commit tokens or OAuth secrets to version control**
2. **Use environment variables** for sensitive configuration
3. **Rotate tokens regularly** via your OAuth provider
4. **Use HTTPS** in production environments
5. **Limit token scopes** to only what's necessary
6. **Monitor token usage** and set up alerts for suspicious activity

## Troubleshooting

### "Error: OAuth2 is not configured"
Set the required environment variables (see Configuration section).

### "Error: Not logged in"
Run `fluidmcp login` to authenticate.

### "Token refresh failed"
Your refresh token may be expired. Run `fluidmcp logout` and then `fluidmcp login` again.

### Browser doesn't open during login
The authorization URL will be printed to the console. Copy and paste it into your browser manually.

### "Authentication timeout"
The OAuth callback server waited 5 minutes but received no response. Try again and complete the authentication flow more quickly.

## Implementation Details

FluidMCP implements OAuth2 PKCE according to [RFC 7636](https://tools.ietf.org/html/rfc7636):

- **Code Verifier**: 32-byte random value, base64url-encoded (43 characters)
- **Code Challenge Method**: S256 (SHA-256 hash)
- **Redirect URI**: Local HTTP server on port 8088 (configurable)
- **Grant Type**: `authorization_code` with PKCE

The implementation is in `fluidai_mcp/services/oauth2_pkce.py`.
