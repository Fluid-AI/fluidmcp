# Keycloak Setup Guide for FluidMCP OAuth 2.0

This guide provides step-by-step instructions for configuring Keycloak to work with FluidMCP's OAuth 2.0 (OIDC) JWT validation.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Create Realm](#1-create-realm)
3. [Create Client Scopes](#2-create-client-scopes)
4. [Configure Audience Mappers](#3-configure-audience-mappers-critical)
5. [Create M2M Client](#4-create-machine-to-machine-m2m-client)
6. [Create Web Client with PKCE](#5-create-web-client-for-authorization-code--pkce)
7. [Configure Token Lifetimes](#6-configure-token-lifetimes)
8. [Create Test User](#7-create-test-user-optional)
9. [Verify Configuration](#8-verify-configuration)
10. [Testing](#9-testing)

---

## Prerequisites

- Keycloak instance running (local or remote)
- Admin access to Keycloak admin console
- FluidMCP installed with OAuth dependencies

---

## 1. Create Realm

A realm in Keycloak is an isolated space for managing users, clients, and configurations.

**Steps:**

1. Log into Keycloak Admin Console
2. Click the dropdown in the top-left corner (next to "Master")
3. Click **"Create Realm"**
4. **Name**: `mcp-realm` (or your preferred name)
5. **Enabled**: ON
6. Click **"Create"**

**Result:** You now have a dedicated realm for FluidMCP authentication.

---

## 2. Create Client Scopes

Client scopes define permissions that clients can request. We'll create two scopes for FluidMCP.

### Scope 1: mcp:read

1. Navigate to **"Client scopes"** in the left menu
2. Click **"Create client scope"**
3. Configure:
   - **Name**: `mcp:read`
   - **Description**: "Read access to MCP servers"
   - **Type**: Default
   - **Protocol**: openid-connect
   - **Display on consent screen**: ON
   - **Include in token scope**: ON
4. Click **"Save"**

### Scope 2: mcp:write

1. Click **"Create client scope"** again
2. Configure:
   - **Name**: `mcp:write`
   - **Description**: "Write access to MCP servers"
   - **Type**: Default
   - **Protocol**: openid-connect
   - **Display on consent screen**: ON
   - **Include in token scope**: ON
3. Click **"Save"**

**Result:** You now have `mcp:read` and `mcp:write` scopes available for clients.

---

## 3. Configure Audience Mappers (CRITICAL)

The audience mapper ensures JWTs contain the correct `aud` claim that FluidMCP validates. **Without this, JWT validation will fail.**

### Add Audience Mapper to mcp:read

1. Navigate to **"Client scopes"** → **"mcp:read"**
2. Click the **"Mappers"** tab
3. Click **"Add mapper"** → **"By configuration"** → **"Audience"**
4. Configure:
   - **Name**: `fluidmcp-audience`
   - **Included Client Audience**: `fluidmcp-gateway`
     (This must match the `audience` in your `.oauth.json` config)
   - **Add to ID token**: OFF
   - **Add to access token**: ON
5. Click **"Save"**

### Add Audience Mapper to mcp:write

Repeat the above steps for the `mcp:write` scope with the same configuration.

**Why this is critical:** FluidMCP validates the `aud` claim in JWT tokens. If this mapper is not configured, tokens will not contain the expected audience and validation will fail with "Invalid audience" errors.

---

## 4. Create Machine-to-Machine (M2M) Client

This client is for services that authenticate without user interaction using the Client Credentials grant.

### Create Client

1. Navigate to **"Clients"** → **"Create client"**
2. **Client ID**: `machine-client`
3. **Name**: "FluidMCP Machine Client"
4. **Description**: "M2M client for service-to-service authentication"
5. Click **"Next"**

### Configure Capability

1. **Client authentication**: ON (enables confidential client)
2. **Authorization**: OFF
3. **Authentication flow**:
   - **Standard flow**: OFF
   - **Direct access grants**: OFF
   - **Service accounts roles**: ON ✓ (this enables Client Credentials)
   - **Implicit flow**: OFF
4. Click **"Next"**

### Configure Access Settings

1. **Root URL**: (leave empty)
2. **Home URL**: (leave empty)
3. **Valid redirect URIs**: (not needed for M2M)
4. **Web origins**: (not needed for M2M)
5. Click **"Save"**

### Get Client Secret

1. Go to the **"Credentials"** tab
2. Copy the **Client Secret** (you'll need this to get tokens)
3. Store it securely (e.g., environment variable, secrets manager)

### Add Scopes

1. Go to the **"Client scopes"** tab
2. Click **"Add client scope"**
3. Select `mcp:read` and `mcp:write`
4. Click **"Add"** → **"Default"**

**Result:** The M2M client can now request tokens with `mcp:read` and `mcp:write` scopes using Client Credentials grant.

---

## 5. Create Web Client for Authorization Code + PKCE

This client is for user-facing applications (ChatGPT, custom web apps) that need user authentication.

### Create Client

1. Navigate to **"Clients"** → **"Create client"**
2. **Client ID**: `web-app`
3. **Name**: "FluidMCP Web Application"
4. **Description**: "Web client with PKCE for user authentication"
5. Click **"Next"**

### Configure Capability

1. **Client authentication**: OFF (public client, no secret)
2. **Authorization**: OFF
3. **Authentication flow**:
   - **Standard flow**: ON ✓ (enables Authorization Code flow)
   - **Direct access grants**: OFF
   - **Service accounts roles**: OFF
   - **Implicit flow**: OFF (deprecated, don't use)
4. Click **"Next"**

### Configure Access Settings

1. **Root URL**: `https://chat.openai.com` (or your app URL)
2. **Home URL**: `https://chat.openai.com`
3. **Valid redirect URIs**:
   - `https://chat.openai.com/*` (for ChatGPT)
   - `http://localhost:*` (for local testing)
4. **Web origins**: `+` (allows CORS from redirect URIs)
5. Click **"Save"**

### Enable PKCE

1. Go to the **"Advanced"** tab
2. Scroll to **"Proof Key for Code Exchange Code Challenge Method"**
3. Select **"S256"** (SHA-256, required for OAuth 2.1)
4. Click **"Save"**

### Add Scopes

1. Go to the **"Client scopes"** tab
2. Click **"Add client scope"**
3. Select `mcp:read` and `mcp:write`
4. Click **"Add"** → **"Default"**

**Result:** The web client can now initiate Authorization Code + PKCE flows for user authentication.

---

## 6. Configure Token Lifetimes

For security, use short-lived access tokens.

1. Navigate to **"Realm settings"** → **"Tokens"** tab
2. Configure:
   - **Access Token Lifespan**: `15 minutes` (recommended)
   - **Access Token Lifespan For Implicit Flow**: `15 minutes`
   - **Client login timeout**: `5 minutes`
   - **Refresh Token Max Reuse**: `0` (no reuse)
3. Click **"Save"**

**Why short-lived tokens?** Combined with FluidMCP's token cache (default 5 minutes), this provides effective token revocation within 15-20 minutes without requiring introspection endpoints.

---

## 7. Create Test User (Optional)

For testing Authorization Code + PKCE flow:

1. Navigate to **"Users"** → **"Add user"**
2. Configure:
   - **Username**: `testuser`
   - **Email**: `testuser@example.com`
   - **Email verified**: ON
   - **Enabled**: ON
3. Click **"Create"**

### Set Password

1. Go to the **"Credentials"** tab
2. Click **"Set password"**
3. **Password**: (your test password)
4. **Temporary**: OFF
5. Click **"Save"**

**Result:** You can now test user authentication flows with this test user.

---

## 8. Verify Configuration

### Test OIDC Discovery Endpoint

```bash
curl https://keycloak.example.com/realms/mcp-realm/.well-known/openid-configuration | jq
```

**Expected response includes:**
```json
{
  "issuer": "https://keycloak.example.com/realms/mcp-realm",
  "authorization_endpoint": "https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/auth",
  "token_endpoint": "https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/token",
  "jwks_uri": "https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/certs",
  "grant_types_supported": ["authorization_code", "client_credentials", "refresh_token"],
  "code_challenge_methods_supported": ["S256", "plain"]
}
```

### Test JWKS Endpoint

```bash
curl https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/certs | jq
```

**Expected response includes:**
```json
{
  "keys": [
    {
      "kid": "abc123...",
      "kty": "RSA",
      "alg": "RS256",
      "use": "sig",
      "n": "...",
      "e": "AQAB"
    }
  ]
}
```

---

## 9. Testing

### Test Client Credentials (M2M) Flow

#### Step 1: Get JWT from Keycloak

```bash
TOKEN=$(curl -X POST https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=machine-client" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "scope=mcp:read mcp:write" \
  | jq -r '.access_token')
```

#### Step 2: Inspect JWT (Optional)

```bash
echo $TOKEN | cut -d. -f2 | base64 -d | jq
```

**Look for:**
- `"aud": ["fluidmcp-gateway"]` ✓
- `"scope": "mcp:read mcp:write"` ✓
- `"iss": "https://keycloak.example.com/realms/mcp-realm"` ✓

#### Step 3: Create FluidMCP OAuth Config

Create `.oauth.json` in the same directory as your MCP config:

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
      "audience": ["fluidmcp-gateway"],
      "required_scopes": ["mcp:read", "mcp:write"]
    }
  }
}
```

#### Step 4: Run FluidMCP with OAuth

```bash
fluidmcp run examples/sample-config.json --file --start-server
```

#### Step 5: Test JWT with FluidMCP

```bash
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

**Expected:** Success response with tools list

**FluidMCP logs should show:**
```
INFO  OAuth configuration loaded successfully
INFO  Initializing OAuth JWT validator
INFO  OIDC configuration loaded successfully
INFO  JWKS fetched successfully: 2 keys loaded
INFO  OAuth JWT validation enabled
DEBUG JWT signature verified successfully
INFO  JWT validated successfully for subject: service-account-machine-client
```

### Test Authorization Code + PKCE Flow

This simulates a user authentication flow like ChatGPT would use.

#### Step 1: Generate PKCE Parameters

```bash
CODE_VERIFIER=$(openssl rand -base64 32 | tr -d '+/' | cut -c1-43)
CODE_CHALLENGE=$(echo -n $CODE_VERIFIER | openssl dgst -sha256 -binary | base64 | tr -d '+/=' | cut -c1-43)

echo "Code Verifier: $CODE_VERIFIER"
echo "Code Challenge: $CODE_CHALLENGE"
```

#### Step 2: Get Authorization Code (Browser)

Open this URL in a browser:

```
https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/auth?client_id=web-app&response_type=code&redirect_uri=http://localhost:3000/callback&scope=openid%20mcp:read%20mcp:write&code_challenge=YOUR_CODE_CHALLENGE&code_challenge_method=S256
```

Replace `YOUR_CODE_CHALLENGE` with the value from Step 1.

**Expected:**
1. Keycloak login page appears
2. Login with `testuser` credentials
3. Consent screen (if enabled)
4. Redirect to: `http://localhost:3000/callback?code=abc123...`

#### Step 3: Extract Authorization Code

Copy the `code` parameter from the redirect URL.

#### Step 4: Exchange Code for JWT

```bash
TOKEN=$(curl -X POST https://keycloak.example.com/realms/mcp-realm/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "client_id=web-app" \
  -d "code=abc123..." \
  -d "redirect_uri=http://localhost:3000/callback" \
  -d "code_verifier=$CODE_VERIFIER" \
  | jq -r '.access_token')
```

Replace `abc123...` with your authorization code.

#### Step 5: Use JWT with FluidMCP

```bash
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

**Expected:** Success response (same as M2M flow)

---

## Common Issues

### Issue: "Invalid audience" error

**Cause:** Audience mapper not configured on client scopes.

**Solution:** Follow [Step 3](#3-configure-audience-mappers-critical) to add audience mappers.

### Issue: "Missing required scopes" error

**Cause:** Client scopes not added to client's default scopes.

**Solution:** Ensure `mcp:read` and `mcp:write` are in the client's **Default** scopes (not optional).

### Issue: "Invalid issuer" error

**Cause:** Mismatch between Keycloak issuer and FluidMCP config.

**Solution:** Check that `issuer` in `.oauth.json` matches Keycloak's `issuer` from the discovery endpoint.

### Issue: "Token expired" error

**Cause:** Access token lifetime exceeded.

**Solution:** Either:
1. Request a new token (recommended)
2. Increase token lifetime in Keycloak (not recommended for production)

### Issue: OIDC discovery fails

**Cause:** Network issues, incorrect URL, or Keycloak not running.

**Solution:**
1. Verify Keycloak is accessible: `curl https://keycloak.example.com`
2. Check the well-known URL format: `{server_url}/realms/{realm}/.well-known/openid-configuration`
3. Check FluidMCP logs for detailed error messages

---

## Security Best Practices

1. **Use HTTPS**: Never run Keycloak or FluidMCP over HTTP in production
2. **Short token lifetimes**: 5-15 minutes for access tokens
3. **Rotate client secrets**: Regularly rotate M2M client secrets
4. **Scope minimization**: Only grant scopes that clients actually need
5. **PKCE for public clients**: Always use PKCE for web/mobile clients
6. **Monitor failed authentications**: Check Keycloak events for suspicious activity
7. **Environment variables**: Store client secrets in environment variables, not config files

---

## Summary Checklist

- ✅ Realm created (`mcp-realm`)
- ✅ Client scopes created (`mcp:read`, `mcp:write`)
- ✅ Audience mapper configured on each scope (points to `fluidmcp-gateway`)
- ✅ M2M client created with Client Credentials grant (`machine-client`)
- ✅ Web client created with Authorization Code + PKCE (`web-app`)
- ✅ Token lifetimes configured (15 minutes)
- ✅ OIDC discovery endpoint verified
- ✅ JWKS endpoint verified
- ✅ FluidMCP OAuth config created (`.oauth.json`)
- ✅ End-to-end testing completed

---

## Next Steps

1. **ChatGPT Integration**: Use the `web-app` client ID when configuring ChatGPT GPTs
2. **Production Deployment**:
   - Use production Keycloak instance with HTTPS
   - Store client secrets securely
   - Configure proper redirect URIs for your domain
3. **Monitoring**: Set up logging and alerts for authentication failures

---

## Additional Resources

- [Keycloak Documentation](https://www.keycloak.org/documentation)
- [OAuth 2.0 RFC 6749](https://datatracker.ietf.org/doc/html/rfc6749)
- [PKCE RFC 7636](https://datatracker.ietf.org/doc/html/rfc7636)
- [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [FluidMCP OAuth Documentation](../CLAUDE.md#oauth-20-oidc-authentication)

---

## Support

If you encounter issues:

1. Check FluidMCP logs for detailed error messages (`--verbose` flag)
2. Verify Keycloak event logs (Login Events / Admin Events)
3. Test OIDC discovery and JWKS endpoints manually
4. Review this guide's [Common Issues](#common-issues) section
5. Open an issue on GitHub with logs and configuration (redact secrets!)
