# Auth0 Quick Start Guide

## Quick Start (3 Steps)

### Step 1: Run Interactive Setup
```bash
python setup-auth0-config.py
```

This will prompt you for:
- Auth0 Domain (e.g., `dev-xxxxx.us.auth0.com`)
- Client ID
- Client Secret
- Callback URL (auto-detects Codespaces URL)

### Step 2: Configure Auth0 Dashboard
Go to [Auth0 Dashboard](https://manage.auth0.com) → Applications → Your App → Settings

Set these URLs:
```
Allowed Callback URLs: YOUR_CALLBACK_URL/auth/callback
Allowed Logout URLs: YOUR_CALLBACK_URL/
Allowed Web Origins: YOUR_CALLBACK_URL
```

### Step 3: Start Server
```bash
fluidmcp run all --start-server --auth0
```

Done! Your server is now protected with Auth0 authentication.

---

## Auth File Structure

### Core Auth Module
Location: `/workspaces/fluidmcp/fluidai_mcp/auth/`

```
fluidai_mcp/auth/
├── __init__.py              # Module exports
├── config.py                # Auth0 configuration loader
├── oauth_client.py          # Auth0 OAuth client
├── routes.py                # FastAPI auth endpoints
├── token_manager.py         # JWT token creation/validation
├── session_store.py         # In-memory session storage
├── middleware.py            # Auth middleware for protected routes
├── AUTH0_SETUP.md          # Detailed setup instructions
└── static/                  # Frontend files
    ├── login.html           # Login page with provider buttons
    ├── css/
    │   └── auth0-styles.css # Styling
    └── js/
        └── auth0-handler.js # Client-side auth logic
```

### Configuration Files
Location: `/workspaces/fluidmcp/`

```
/workspaces/fluidmcp/
├── auth0-config.json         # Your Auth0 credentials (gitignored)
├── auth0-config.example.json # Template file
├── setup-auth0-config.py     # Interactive setup script
└── view-tokens.py            # Token debugging tool
```

### Integration Files
```
fluidai_mcp/
├── services/
│   └── run_servers.py        # Includes auth router (lines ~100-110)
└── cli.py                    # Adds --auth0 flag (line ~150)
```

---

## Authentication Workflow

### 1. User Authentication Flow

```
User Opens App
    ↓
http://localhost:8099/
    ↓
[Protected by Auth Middleware]
    ↓
Redirects to → /auth/static/login.html
    ↓
User Clicks Provider Button
(Google/GitHub/Zoho/Atlassian/Azure)
    ↓
GET /auth/login?connection=google-oauth2
    ↓
[routes.py - login() function]
    ↓
Creates OAuth state token
Stores in session_store
    ↓
Redirects to Auth0
https://YOUR_DOMAIN.auth0.com/authorize?
  client_id=...&
  redirect_uri=.../auth/callback&
  connection=google-oauth2&
  state=...
    ↓
[User Authenticates with Provider]
    ↓
Auth0 Redirects Back
GET /auth/callback?code=...&state=...
    ↓
[routes.py - callback() function]
    ↓
1. Validates state token
2. Exchanges code for Auth0 tokens
3. Gets user info from Auth0
4. Creates custom JWT token
5. Stores session in session_store
    ↓
Returns HTML with JavaScript
    ↓
Stores in Browser localStorage:
  - access_token (JWT)
  - session_id
    ↓
Redirects to Main App
    ↓
User Authenticated ✅
```

### 2. API Request Flow

```
Client Makes API Request
    ↓
GET /some-protected-endpoint
Headers: {
  Authorization: Bearer <JWT_TOKEN>
}
    ↓
[middleware.py - Auth Dependency]
    ↓
Extracts JWT from Authorization header
    ↓
[token_manager.py - verify_token()]
    ↓
Validates JWT signature
Checks expiration
    ↓
Valid? → Allow Request ✅
Invalid? → 401 Unauthorized ❌
```

### 3. Configuration Loading Flow

```
Server Starts with --auth0
    ↓
[run_servers.py]
    ↓
Checks: os.environ.get("FMCP_AUTH0_MODE")
    ↓
[config.py - Auth0Config.from_env_or_file()]
    ↓
Priority Order:
1. Environment Variables (highest)
   - AUTH0_DOMAIN
   - AUTH0_CLIENT_ID
   - AUTH0_CLIENT_SECRET
   - AUTH0_CALLBACK_URL
   - FMCP_JWT_SECRET
    ↓
2. Configuration File (medium)
   - ./auth0-config.json
    ↓
3. Default Values (lowest)
   - callback_url: http://localhost:8099/auth/callback
   - jwt_algorithm: HS256
   - jwt_expiration_minutes: 30
    ↓
Validates Required Fields
    ↓
Initializes:
- Auth0Client (oauth_client.py)
- TokenManager (token_manager.py)
- SessionStore (session_store.py)
    ↓
Mounts Static Files
Includes Auth Router
    ↓
Server Ready ✅
```

### 4. Token Lifecycle

```
User Logs In
    ↓
[token_manager.py - create_access_token()]
    ↓
Creates JWT with payload:
{
  "sub": "google-oauth2|12345",
  "email": "user@example.com",
  "name": "John Doe",
  "picture": "https://...",
  "provider": "Google",
  "exp": timestamp + 30 minutes,
  "iat": timestamp,
  "type": "access"
}
    ↓
Signs with FMCP_JWT_SECRET
    ↓
Returns JWT Token
    ↓
[Browser Stores in localStorage]
    ↓
Token Valid for 30 Minutes
    ↓
After 30 Minutes → Token Expires
    ↓
Next API Request → 401 Unauthorized
    ↓
User Must Login Again
```

### 5. Session Storage Flow

```
User Authenticates
    ↓
[session_store.py - create_session()]
    ↓
Generates session_id (32-byte token)
    ↓
Stores in Memory:
_sessions = {
  "session_id_abc123": {
    "user": {
      "sub": "google-oauth2|12345",
      "email": "user@example.com",
      "name": "John Doe",
      "picture": "https://..."
    },
    "created_at": datetime.utcnow()
  }
}
    ↓
Returns session_id to client
    ↓
[Session Stays in Memory]
Until server restart
```

---

## File Path Reference

### Configuration Loading
- **Entry Point**: `fluidai_mcp/services/run_servers.py:100-110`
- **Config Loader**: `fluidai_mcp/auth/config.py:Auth0Config.from_env_or_file()`
- **Priority**: Environment Variables → File → Defaults

### Authentication Routes
- **Login Endpoint**: `fluidai_mcp/auth/routes.py:login()` → `/auth/login`
- **Callback Endpoint**: `fluidai_mcp/auth/routes.py:callback()` → `/auth/callback`
- **Static Files**: `fluidai_mcp/auth/static/login.html`

### OAuth Client
- **Authorization URL**: `fluidai_mcp/auth/oauth_client.py:get_authorization_url()`
- **Token Exchange**: `fluidai_mcp/auth/oauth_client.py:exchange_code_for_tokens()`
- **User Info**: `fluidai_mcp/auth/oauth_client.py:get_user_info()`

### JWT Token Management
- **Create Token**: `fluidai_mcp/auth/token_manager.py:create_access_token()`
- **Verify Token**: `fluidai_mcp/auth/token_manager.py:verify_token()`
- **Extract Provider**: `fluidai_mcp/auth/token_manager.py:_extract_provider()`

### Session Management
- **Create Session**: `fluidai_mcp/auth/session_store.py:create_session()`
- **Get Session**: `fluidai_mcp/auth/session_store.py:get_session()`
- **Validate State**: `fluidai_mcp/auth/session_store.py:validate_state()`

### Middleware
- **Auth Dependency**: `fluidai_mcp/auth/middleware.py:create_auth_dependency()`
- **Token Extraction**: Reads `Authorization: Bearer <token>` header
- **Validation**: Calls `token_manager.verify_token()`

---

## Supported Identity Providers

FluidMCP supports the following authentication providers through Auth0:

| Provider | Connection ID | Button Label |
|----------|--------------|--------------|
| Google | `google-oauth2` | "Continue with Google" |
| GitHub | `github` | "Continue with GitHub" |
| Zoho | `zoho` | "Continue with Zoho" |
| Atlassian | `atlassian` | "Continue with Atlassian" |
| Azure AD | `waad` | "Continue with Microsoft/Azure" |

**How It Works:**
- Each button in `login.html` calls `loginWithProvider(connection)`
- This redirects to `/auth/login?connection=<provider>`
- Auth0 bypasses Universal Login and goes directly to the provider

---

## Environment Variables Reference

### Required
```bash
# Auth0 Configuration
AUTH0_DOMAIN=dev-xxxxx.us.auth0.com
AUTH0_CLIENT_ID=your_client_id
AUTH0_CLIENT_SECRET=your_client_secret

# JWT Configuration
FMCP_JWT_SECRET=your_jwt_secret_here
```

### Optional
```bash
# Override callback URL
AUTH0_CALLBACK_URL=https://custom-url.com/auth/callback

# OAuth audience (for Auth0 API)
AUTH0_AUDIENCE=https://your-api-identifier

# JWT settings
FMCP_JWT_ALGORITHM=HS256
FMCP_JWT_EXPIRATION_MINUTES=30
```

### Enable Auth0 Mode
```bash
# Set by --auth0 flag automatically
FMCP_AUTH0_MODE=true
```

---

## Debugging Tools

### View Active Sessions
```bash
python view-tokens.py
```

Shows:
- Active sessions in memory
- User information
- Pending OAuth states

### Decode JWT Token
```bash
python view-tokens.py YOUR_JWT_TOKEN_HERE
```

Shows:
- Token payload
- Expiration time
- User claims

### Browser DevTools
1. Open DevTools (F12)
2. Go to Application/Storage tab
3. Click Local Storage → Your Domain
4. Look for:
   - `access_token` - Your JWT
   - `session_id` - Your session ID

---

## Troubleshooting

### Issue: "Callback URL mismatch"
**Solution:** Update Auth0 Dashboard URLs to match your config

### Issue: "401 Unauthorized"
**Solution:** Check client secret is correct in `auth0-config.json`

### Issue: "Config file not found"
**Solution:** Run `python setup-auth0-config.py` to create it

### Issue: Token expired
**Solution:** Token expires after 30 minutes. User must login again.

---

## Security Best Practices

1. **Never commit secrets**
   - `auth0-config.json` is gitignored
   - Verify with `git status` before committing

2. **Set file permissions**
   ```bash
   chmod 600 auth0-config.json
   ```

3. **Use HTTPS in production**
   - Never use HTTP for authentication
   - Always use HTTPS callback URLs

4. **Rotate secrets regularly**
   - Update Auth0 Client Secret periodically
   - Generate new JWT secret

5. **Configure Auth0 properly**
   - Only whitelist your callback URLs
   - Enable MFA for admin accounts
   - Review Auth0 security settings

---

## Additional Resources

- [AUTH0_CONFIG_FILE_GUIDE.md](AUTH0_CONFIG_FILE_GUIDE.md) - Comprehensive config guide
- [fluidai_mcp/auth/AUTH0_SETUP.md](fluidai_mcp/auth/AUTH0_SETUP.md) - Detailed setup
- [Auth0 Documentation](https://auth0.com/docs)
- [OAuth 2.0 Specification](https://oauth.net/2/)

---

## Quick Commands Cheat Sheet

```bash
# Setup
python setup-auth0-config.py

# Start server with Auth0
fluidmcp run all --start-server --auth0

# View sessions
python view-tokens.py

# Decode token
python view-tokens.py YOUR_TOKEN

# Check config
cat auth0-config.json

# Verify file permissions
ls -la auth0-config.json

# Test login
open http://localhost:8099/auth/static/login.html
```

---

**Last Updated**: 2025-12-31
**Auth0 Version**: OAuth 2.0
**FluidMCP Version**: Latest
