# Token Storage Guide

This guide explains where Auth0 tokens are stored and how to view them.

## Token Storage Locations

### 1. Browser LocalStorage (Client-Side) 🌐

After successful authentication, tokens are stored in your browser's localStorage:

**Location:** Browser → DevTools → Application/Storage → Local Storage → Your Domain

**Stored Items:**
- `access_token` - JWT token for API authentication (expires in 30 minutes)
- `session_id` - Session identifier for server-side session lookup

**How to View:**

1. **Chrome/Edge:**
   - Press `F12` or `Ctrl+Shift+I` (Windows/Linux) / `Cmd+Option+I` (Mac)
   - Click the **"Application"** tab
   - Expand **"Local Storage"** in the left sidebar
   - Click on your domain: `https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev`
   - You'll see `access_token` and `session_id`

2. **Firefox:**
   - Press `F12` or `Ctrl+Shift+I`
   - Click the **"Storage"** tab
   - Expand **"Local Storage"**
   - Click on your domain
   - View `access_token` and `session_id`

### 2. Server Memory (Session Store) 💾

Server-side sessions are stored in memory:

**Location:** `fluidai_mcp/auth/session_store.py` - In-memory Python dictionary

**Stored Data:**
- OAuth state tokens (temporary, expire after 5 minutes)
- User sessions with user profile data
- Session creation timestamps

**How to View:**

Run the token viewer script:

```bash
python view-tokens.py
```

This will show:
- Active sessions with user data
- Pending OAuth states
- Session creation times

### 3. JWT Token Content 🔐

The JWT access token contains encrypted user information:

**Token Structure:**
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
  Header                                Payload (User Data)                                             Signature
```

**Payload Contains:**
- User email
- User name
- Auth0 user ID (sub)
- Token expiration time (exp)
- Token issued time (iat)

**How to Decode:**

```bash
# Decode a JWT token
python view-tokens.py YOUR_JWT_TOKEN_HERE
```

Or use online decoder: https://jwt.io (paste your token)

## Complete Token Viewer Script

Run this to see all stored authentication data:

```bash
python view-tokens.py
```

**Output Example:**
```
🔐 FluidMCP Auth0 Token Viewer

Auth0 Domain: dev-4anz4n3tvh3iyixx.us.auth0.com
Client ID: k80RDWadsrIXntnv7kbai1i3aL6ZgHRe
Callback URL: https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/auth/callback

============================================================
ACTIVE SESSIONS
============================================================

Session ID: abc123...
Created at: 2025-12-31 05:20:15
User data:
  email: user@example.com
  name: John Doe
  sub: github|12345
  picture: https://avatars.githubusercontent.com/...

============================================================
PENDING OAUTH STATES
============================================================

No pending OAuth states.

============================================================
JWT TOKEN DECODER
============================================================

To decode a JWT token, run:
  python view-tokens.py YOUR_JWT_TOKEN

============================================================

📱 To view tokens in your browser:

1. Open your browser DevTools (F12 or Ctrl+Shift+I)
2. Go to 'Application' tab (Chrome) or 'Storage' tab (Firefox)
3. Click 'Local Storage' in the left sidebar
4. Select your domain
5. Look for these keys:
   - access_token: Your JWT access token
   - session_id: Your session identifier
```

## Token Lifecycle

### 1. Login Flow
```
User clicks provider button
    ↓
Generate OAuth state (stored in memory for 5 min)
    ↓
Redirect to Auth0
    ↓
User authorizes
    ↓
Auth0 redirects back with code
    ↓
Exchange code for Auth0 tokens
    ↓
Create custom JWT token (stored in browser)
    ↓
Create session (stored in server memory)
    ↓
Store access_token + session_id in localStorage
```

### 2. API Request Flow
```
Browser sends request
    ↓
Include Authorization: Bearer {access_token}
    ↓
Server verifies JWT signature
    ↓
Extract user info from token
    ↓
Process request
```

### 3. Token Expiration
- **JWT Access Token:** 30 minutes (configurable via `FMCP_JWT_EXPIRATION_MINUTES`)
- **OAuth State:** 5 minutes (for CSRF protection)
- **Sessions:** No expiration (cleared on logout or server restart)

## How to Extract Token from Browser

### Method 1: DevTools Console
1. Open browser console (F12)
2. Type: `localStorage.getItem('access_token')`
3. Press Enter
4. Copy the token value

### Method 2: Manual Copy
1. Open DevTools → Application/Storage
2. Find `access_token` in Local Storage
3. Right-click the value → Copy
4. Paste it where needed

### Method 3: JavaScript
```javascript
// In browser console
const token = localStorage.getItem('access_token');
console.log('Access Token:', token);

// Decode JWT payload (without verification)
const payload = JSON.parse(atob(token.split('.')[1]));
console.log('Token Payload:', payload);
```

## Security Notes

- **Never share your tokens** - They provide full access to your authenticated session
- **Tokens are stored in plain text** in localStorage (standard practice for SPAs)
- **HTTPS is required** - Tokens sent over HTTP can be intercepted
- **Tokens expire** - Access tokens expire after 30 minutes for security
- **Server-side sessions** - Stored in memory, cleared on server restart

## Troubleshooting

### Token Not Found in Browser
- Make sure you completed the login flow
- Check if you were redirected to `/docs` after login
- Try logging in again

### Token Invalid/Expired
- JWT tokens expire after 30 minutes
- Log out and log in again to get a new token
- Check server logs for verification errors

### Session Not Found
- Server was restarted (sessions are in-memory, not persisted)
- Session expired or was manually deleted
- Log in again to create a new session

## Files Reference

- [fluidai_mcp/auth/routes.py](fluidai_mcp/auth/routes.py#L122) - Line 122-123: Stores token in localStorage
- [fluidai_mcp/auth/session_store.py](fluidai_mcp/auth/session_store.py) - In-memory session storage
- [fluidai_mcp/auth/token_manager.py](fluidai_mcp/auth/token_manager.py) - JWT token creation and verification
- [view-tokens.py](view-tokens.py) - Token viewer script
