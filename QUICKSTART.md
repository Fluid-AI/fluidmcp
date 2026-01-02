# FluidMCP Quick Start - Airbnb Package

Get started with FluidMCP and run the Airbnb package with OAuth authentication in under 5 minutes!

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start - Airbnb Without Authentication](#quick-start---airbnb-without-authentication)
- [Run Airbnb With OAuth Authentication](#run-airbnb-with-oauth-authentication)
- [GitHub Codespaces Setup](#github-codespaces-setup)
- [Testing Airbnb API](#testing-airbnb-api)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before you begin, ensure you have:

- **Python 3.11 or higher** installed
- **Node.js and npm** installed (required for MCP servers)
- **Git** installed

---

## Installation

Clone and install FluidMCP:

```bash
# Clone repository
git clone https://github.com/Fluid-AI/fluidmcp.git
cd fluidmcp

# Install dependencies
pip install -r requirements.txt

# Install FluidMCP in development mode
pip install -e .

# Verify installation
fluidmcp --version
```

**Expected output:**
```
FluidMCP CLI version 0.1.0
```

---

## Quick Start - Airbnb Without Authentication

This is the fastest way to test the Airbnb package:

### Step 1: Install Airbnb Package

```bash
fluidmcp install Airbnb/airbnb@0.1.0
```

**Expected output:**
```
✓ Successfully installed Airbnb/airbnb@0.1.0
```

### Step 2: Run Airbnb Server

```bash
fluidmcp run Airbnb/airbnb@0.1.0 --start-server
```

**Expected output:**
```
🚀 FluidMCP Server Starting
======================================================================
   Server running on http://localhost:8099
   Swagger UI: http://localhost:8099/docs
======================================================================
```

### Step 3: Access Swagger UI

Open your browser and navigate to:
```
http://localhost:8099/docs
```

### Step 4: Test Airbnb API

You can now test the Airbnb endpoints:

**Example 1: List available tools**
```bash
curl -X POST http://localhost:8099/airbnb/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

**Expected response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "search_properties",
        "description": "Search for Airbnb properties",
        "inputSchema": {...}
      },
      {
        "name": "get_property_details",
        "description": "Get detailed information about a property",
        "inputSchema": {...}
      }
    ]
  }
}
```

**Example 2: Search Airbnb properties**
```bash
curl -X POST http://localhost:8099/airbnb/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "search_properties",
      "arguments": {
        "location": "San Francisco",
        "checkin": "2024-03-01",
        "checkout": "2024-03-05"
      }
    }
  }'
```

---

## Run Airbnb With OAuth Authentication

Secure your Airbnb API with enterprise-grade OAuth authentication using Auth0.

### Step 1: Create Auth0 Account

1. Go to [https://auth0.com/signup](https://auth0.com/signup)
2. Sign up for a free account
3. Complete the registration process

### Step 2: Create Auth0 Application

1. Navigate to **Dashboard → Applications → Create Application**
2. **Name**: `FluidMCP Gateway`
3. **Type**: Select `Regular Web Applications`
4. Click **Create**

### Step 3: Get Your Environment URLs

Run the URL detection script:

```bash
python print-auth0-urls.py
```

**Example output:**
```
FluidMCP Auth0 URL Configuration Tool
======================================================================

📍 Environment: CODESPACES
🌐 Detected Remote Environment

🔗 URLs for your application:
   Base URL:     https://effective-journey-xxxxx-8099.app.github.dev
   Login URL:    https://effective-journey-xxxxx-8099.app.github.dev/
   Swagger UI:   https://effective-journey-xxxxx-8099.app.github.dev/docs
   Callback URL: https://effective-journey-xxxxx-8099.app.github.dev/auth/callback

📋 Copy these URLs to your Auth0 Application Settings
======================================================================
```

### Step 4: Configure Auth0 Application URLs

In your Auth0 application settings, configure the following URLs:

#### For GitHub Codespaces (Recommended - Works Forever!)

Use wildcard URLs so you don't need to update Auth0 every time:

**Allowed Callback URLs:**
```
https://*.app.github.dev/auth/callback,http://localhost:8099/auth/callback
```

**Allowed Logout URLs:**
```
https://*.app.github.dev/,http://localhost:8099/
```

**Allowed Web Origins:**
```
https://*.app.github.dev,http://localhost:8099
```

#### For Local Development

**Allowed Callback URLs:**
```
http://localhost:8099/auth/callback
```

**Allowed Logout URLs:**
```
http://localhost:8099/
```

**Allowed Web Origins:**
```
http://localhost:8099
```

### Step 5: Enable Social Connections (Optional)

To allow users to sign in with GitHub, Google, Microsoft, etc.:

1. Go to **Authentication → Social**
2. Enable your desired providers:
   - ✅ GitHub
   - ✅ Google
   - ✅ Microsoft
   - ✅ LinkedIn
3. Configure each provider with their credentials
4. Click **Save**

### Step 6: Copy Auth0 Credentials

From your Auth0 application settings, copy:

- **Domain** (e.g., `dev-xxxxx.us.auth0.com`)
- **Client ID** (e.g., `k80RDWadsrIXntnv7kbai1i3aL6ZgHRe`)
- **Client Secret** (click "Show" to reveal)

### Step 7: Set Environment Variables

Export your Auth0 credentials as environment variables:

```bash
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id_here"
export AUTH0_CLIENT_SECRET="your_client_secret_here"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)
```

**Example with actual values:**
```bash
export AUTH0_DOMAIN="dev-4anz4n3tvh3iyixx.us.auth0.com"
export AUTH0_CLIENT_ID="k80RDWadsrIXntnv7kbai1i3aL6ZgHRe"
export AUTH0_CLIENT_SECRET="TGIB02bymxvstSX-XWjTMp2WJd-uw1WFEWjyJDPFCMfsiwzITDYP11OLTdgzwaF-"
export FMCP_JWT_SECRET="a8f3j9dk2m4n5b7c9e1f3g5h7j9k2m4n5p7q9r2s4t6u8v1w3x5y7z9"
```

**Alternative: Save to .env file**

```bash
cat > .env <<'EOF'
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_CLIENT_ID=your_client_id_here
AUTH0_CLIENT_SECRET=your_client_secret_here
FMCP_JWT_SECRET=$(openssl rand -base64 32)
EOF

# Load environment variables
source .env
```

### Step 8: Install Airbnb Package

```bash
fluidmcp install Airbnb/airbnb@0.1.0
```

### Step 9: Run Airbnb With OAuth

```bash
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0
```

**Expected output:**
```
🔐 Auth0 OAuth authentication enabled
   Supported providers: GitHub, Google, Microsoft

======================================================================
🔐 Auth0 OAuth Configuration
======================================================================
📍 Environment: CODESPACES
🌐 Detected Remote Environment

🔗 URLs for your application:
   Base URL:     https://effective-journey-xxxxx-8099.app.github.dev
   Login URL:    https://effective-journey-xxxxx-8099.app.github.dev/
   Swagger UI:   https://effective-journey-xxxxx-8099.app.github.dev/docs
   Callback URL: https://effective-journey-xxxxx-8099.app.github.dev/auth/callback
======================================================================

Launching server 'airbnb' from: /workspaces/fluidmcp/.fmcp-packages/Airbnb/airbnb/0.1.0
Added airbnb endpoints
Successfully launched 1 MCP server(s)

======================================================================
🚀 FluidMCP Server Starting
======================================================================
🔐 Auth0 OAuth: ENABLED
   Login at: https://effective-journey-xxxxx-8099.app.github.dev/
   Swagger UI: https://effective-journey-xxxxx-8099.app.github.dev/docs
======================================================================

Server running on https://effective-journey-xxxxx-8099.app.github.dev
```

### Step 10: Access and Authenticate

1. **Open the Login URL** shown in the terminal output
2. **Click "Sign in with Auth0"**
3. **Choose your identity provider** (GitHub, Google, etc.)
4. **Authorize the application**
5. **You'll be redirected back** to the FluidMCP interface

### Step 11: Test Authenticated API

Now all Airbnb endpoints require authentication:

**Access Swagger UI:**
```
https://your-codespace-url-8099.app.github.dev/docs
```

You'll automatically be authenticated via session cookies when using the browser.

**Test with curl (requires JWT token):**

First, extract your JWT token from the browser:
1. Open Developer Tools (F12)
2. Go to Application → Cookies
3. Copy the `access_token` value

```bash
curl -X POST https://your-codespace-url-8099.app.github.dev/airbnb/mcp/tools/list \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

**Expected response with authentication:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [...]
  }
}
```

**Without authentication (will fail):**
```bash
curl -X POST https://your-codespace-url-8099.app.github.dev/airbnb/mcp/tools/list \
  -H "Content-Type: application/json"
```

**Expected error:**
```json
{
  "detail": "Not authenticated"
}
```

---

## GitHub Codespaces Setup

If you're running FluidMCP in GitHub Codespaces, follow these additional steps:

### Make Port 8099 Public

By default, Codespaces ports are private. Make port 8099 public to access it from your browser:

**Method 1: Using Command Palette**
1. Press `Cmd/Ctrl + Shift + P`
2. Type `Ports: Focus on Ports View`
3. Find port **8099**
4. Right-click → **Change Port Visibility → Public**

**Method 2: Using Ports Panel**
1. Open the **Ports** tab in VSCode (bottom panel)
2. Find port **8099**
3. Right-click → **Port Visibility → Public**

### Configure Auth0 with Wildcards

Use wildcard URLs in Auth0 (one-time setup) so all your Codespaces work automatically:

```
Allowed Callback URLs:
https://*.app.github.dev/auth/callback

Allowed Logout URLs:
https://*.app.github.dev/

Allowed Web Origins:
https://*.app.github.dev
```

This works for **all your Codespaces forever** - no need to update Auth0 again!

### Run Airbnb in Codespaces

```bash
# Set Auth0 credentials
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Run with OAuth
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0
```

FluidMCP **automatically detects** your Codespace URL and configures OAuth correctly!

---

## Testing Airbnb API

### Test 1: List Available Tools (No Auth)

```bash
# Run server without authentication
fluidmcp run Airbnb/airbnb@0.1.0 --start-server

# Test tools list endpoint
curl -X POST http://localhost:8099/airbnb/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

**Expected: Success (200 OK)**

### Test 2: Search Airbnb Properties (No Auth)

```bash
curl -X POST http://localhost:8099/airbnb/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "search_properties",
      "arguments": {
        "location": "New York",
        "checkin": "2024-04-01",
        "checkout": "2024-04-05",
        "guests": 2
      }
    }
  }'
```

**Expected: Success (200 OK) with property listings**

### Test 3: Access Without Authentication (With OAuth Enabled)

```bash
# Run server with OAuth
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0

# Try to access without token (should fail)
curl -X POST https://your-url/airbnb/mcp/tools/list \
  -H "Content-Type: application/json"
```

**Expected: Unauthorized (401)**
```json
{
  "detail": "Not authenticated"
}
```

### Test 4: Access With Authentication (With OAuth Enabled)

```bash
# Get JWT token from browser (Developer Tools → Application → Cookies)
curl -X POST https://your-url/airbnb/mcp/tools/list \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

**Expected: Success (200 OK)**

### Test 5: Run OAuth Test Suite

FluidMCP includes a comprehensive test suite:

```bash
python test-dynamic-oauth.py
```

**Expected output:**
```
======================================================================
Test 1: Imports
======================================================================
✓ All imports successful

======================================================================
Test 2: Environment Detection
======================================================================
✓ Environment: CODESPACES
✓ Base URL: https://effective-journey-xxxxx-8099.app.github.dev

======================================================================
Test 3: Auth0 Configuration
======================================================================
✓ Auth0 domain configured
✓ Client ID configured
✓ JWT secret configured

All tests passed! ✓
```

---

## Protected Endpoints with OAuth

When you run Airbnb with `--auth0`, all endpoints require authentication:

| Endpoint | Description | Method | Protected |
|----------|-------------|--------|-----------|
| `/` | Login page | GET | ✅ Redirects to Auth0 |
| `/docs` | Swagger UI documentation | GET | ✅ Requires login |
| `/airbnb/mcp` | JSON-RPC proxy endpoint | POST | ✅ Requires JWT token |
| `/airbnb/sse` | Server-Sent Events stream | GET | ✅ Requires JWT token |
| `/airbnb/mcp/tools/list` | List available Airbnb tools | POST | ✅ Requires JWT token |
| `/airbnb/mcp/tools/call` | Call specific Airbnb tool | POST | ✅ Requires JWT token |

**Authentication Methods:**
- **Browser/Swagger UI**: Session-based (automatic after login)
- **API/curl**: JWT Bearer token required in `Authorization` header

---

## Troubleshooting

### Issue 1: Port Already in Use

**Problem:**
```
Error: Address already in use (port 8099)
```

**Solution:**
```bash
# Option A: Force reload
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --force-reload

# Option B: Kill process manually
lsof -ti:8099 | xargs kill -9

# Option C: Use different port
export MCP_CLIENT_SERVER_ALL_PORT=8100
fluidmcp run Airbnb/airbnb@0.1.0 --start-server
```

### Issue 2: Auth0 Configuration Missing

**Problem:**
```
Error: AUTH0_DOMAIN not configured
```

**Solution:**
```bash
# Check environment variables
echo $AUTH0_DOMAIN
echo $AUTH0_CLIENT_ID
echo $AUTH0_CLIENT_SECRET
echo $FMCP_JWT_SECRET

# Set them if missing
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Verify
env | grep -E "AUTH0|FMCP_JWT"
```

### Issue 3: Callback URL Mismatch

**Problem:**
```
Error: Callback URL mismatch - redirecting to wrong URL
```

**Solution:**
```bash
# Get correct URLs for your environment
python print-auth0-urls.py

# Copy the exact URLs to Auth0 application settings
# Ensure protocol matches (http vs https)
# For Codespaces, use wildcard: https://*.app.github.dev/auth/callback
```

### Issue 4: Codespaces Port Not Accessible

**Problem:** External users can't access the server URL

**Solution:**
1. Open **Ports** panel in VSCode (bottom panel)
2. Find port **8099**
3. Right-click → **Change Port Visibility → Public**
4. Copy the forwarded URL (not localhost)

### Issue 5: MCP Server Initialization Failed

**Problem:**
```
Error: Failed to initialize MCP server
```

**Solution:**
```bash
# Check Node.js is installed
node --version
npm --version

# If not installed:
# Ubuntu/Debian
sudo apt update && sudo apt install nodejs npm

# macOS
brew install node

# Verify Airbnb package exists
ls -la .fmcp-packages/Airbnb/airbnb/0.1.0/

# Reinstall if needed
fluidmcp install Airbnb/airbnb@0.1.0 --force
```

### Issue 6: JWT Token Expired

**Problem:**
```json
{
  "detail": "Token expired"
}
```

**Solution:**
1. Open your browser
2. Navigate to the login URL
3. Sign in again to get a new token
4. Extract the new JWT token from cookies

---

## Complete Example - Airbnb with OAuth

Here's a complete end-to-end example:

```bash
# 1. Clone and install FluidMCP
git clone https://github.com/Fluid-AI/fluidmcp.git
cd fluidmcp
pip install -r requirements.txt
pip install -e .

# 2. Set Auth0 credentials (replace with your values)
export AUTH0_DOMAIN="dev-4anz4n3tvh3iyixx.us.auth0.com"
export AUTH0_CLIENT_ID="k80RDWadsrIXntnv7kbai1i3aL6ZgHRe"
export AUTH0_CLIENT_SECRET="TGIB02bymxvstSX-XWjTMp2WJd-uw1WFEWjyJDPFCMfsiwzITDYP11OLTdgzwaF-"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# 3. Install Airbnb package
fluidmcp install Airbnb/airbnb@0.1.0

# 4. Run with OAuth
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0

# 5. Open browser to login URL (shown in terminal)
# 6. Sign in with GitHub/Google
# 7. Access Swagger UI at /docs
# 8. Test Airbnb API endpoints
```

**Result:** Secure, authenticated Airbnb API running with OAuth! 🎉

---

## Next Steps

### Learn More

- **[Full Documentation](docs/INDEX.md)** - Complete FluidMCP documentation
- **[OAuth Setup Guide](docs/OAUTH_SETUP_QUICK_START.md)** - Detailed Auth0 configuration
- **[Registry Package Auth](docs/REGISTRY_PACKAGE_AUTH.md)** - Securing registry packages
- **[How to Run](docs/HOW_TO_RUN.md)** - All run modes and options
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions

### Run Other Packages

FluidMCP supports many packages from the registry:

```bash
# List all installed packages
fluidmcp list

# Install other packages
fluidmcp install GoogleMaps/googlemaps@1.0.0
fluidmcp install Slack/slack@0.2.0

# Run with OAuth
fluidmcp run GoogleMaps/googlemaps@1.0.0 --start-server --auth0
```

---

## Summary

You've learned how to:

✅ Install FluidMCP
✅ Run Airbnb package without authentication
✅ Set up Auth0 for OAuth authentication
✅ Run Airbnb with OAuth security
✅ Test Airbnb API with and without authentication
✅ Configure GitHub Codespaces for public access
✅ Use wildcard URLs for Codespaces
✅ Troubleshoot common issues
✅ Secure your Airbnb API with enterprise-grade OAuth

---

## Need Help?

- **Documentation**: [docs/](docs/)
- **GitHub Issues**: [https://github.com/Fluid-AI/fluidmcp/issues](https://github.com/Fluid-AI/fluidmcp/issues)
- **Examples**: [examples/](examples/)

---

🚀 **Happy coding with FluidMCP and Airbnb!**
