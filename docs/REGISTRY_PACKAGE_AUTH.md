# Securing Registry Packages with OAuth

When you install and run packages from the FluidMCP registry (like Airbnb, Google Maps, etc.), you can require OAuth authentication to protect your API endpoints.

---

## 🚀 Quick Start

```bash
# 1. Install package from registry
fluidmcp install Airbnb/airbnb@0.1.0

# 2. Set up Auth0 credentials (one-time setup)
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# 3. Run with OAuth authentication
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0
```

**That's it!** Your registry package is now protected with enterprise-grade OAuth authentication.

---

## 🔒 What Gets Protected?

When you run a registry package with `--auth0`, **all endpoints require authentication**:

| Endpoint | Description | Protected |
|----------|-------------|-----------|
| `/` | Login page | ✅ Redirects to Auth0 |
| `/docs` | Swagger UI | ✅ Requires login |
| `/airbnb/mcp` | JSON-RPC proxy | ✅ Requires JWT token |
| `/airbnb/sse` | Server-Sent Events | ✅ Requires JWT token |
| `/airbnb/mcp/tools/list` | List available tools | ✅ Requires JWT token |
| `/airbnb/mcp/tools/call` | Call specific tool | ✅ Requires JWT token |

---

## 👤 How Users Access the API

### Step 1: Navigate to Base URL

```bash
# After running the server, you'll see output like:
🚀 FluidMCP Server Starting
======================================================================
🔐 Auth0 OAuth: ENABLED
   Login at: https://your-codespace-8099.app.github.dev/
   Swagger UI: https://your-codespace-8099.app.github.dev/docs
======================================================================
```

### Step 2: Sign in with Auth0

1. Open the login URL in your browser
2. Click "Sign in with Auth0"
3. Choose your identity provider (GitHub, Google, Microsoft, etc.)
4. Authorize the application
5. You'll be redirected back with authentication

### Step 3: Use the API

**Option A: Via Swagger UI**
- Navigate to `/docs`
- You're already authenticated (session-based)
- Click "Try it out" on any endpoint
- Execute API calls directly

**Option B: Via API with JWT Token**
```bash
# Get your JWT token from the browser (check cookies or developer tools)
curl -X POST https://your-url/airbnb/mcp/tools/list \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

---

## 🧪 Testing Authentication

### Test 1: Access Without Authentication (Should Fail)

```bash
# Try to access API without token
curl -X POST https://your-url/airbnb/mcp/tools/list \
  -H "Content-Type: application/json"

# Expected Response:
# {
#   "detail": "Not authenticated"
# }
# Status Code: 401 Unauthorized
```

### Test 2: Access With Authentication (Should Succeed)

```bash
# First, log in via browser and get your JWT token
# Then access API with token
curl -X POST https://your-url/airbnb/mcp/tools/list \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"

# Expected Response:
# {
#   "jsonrpc": "2.0",
#   "id": 1,
#   "result": {
#     "tools": [...]
#   }
# }
# Status Code: 200 OK
```

---

## 🌐 Environment Support

FluidMCP automatically detects your environment and configures OAuth URLs:

| Environment | Auto-Detection | Example URL |
|-------------|----------------|-------------|
| **Local Development** | Default | `http://localhost:8099` |
| **GitHub Codespaces** | Automatic | `https://codespace-8099.app.github.dev` |
| **Gitpod** | Automatic | `https://8099-workspace-url` |
| **Custom Domain** | Via `FMCP_BASE_URL` | `https://api.yourdomain.com` |

**No manual configuration needed!** FluidMCP detects your environment and generates the correct callback URLs automatically.

---

## 🔧 Configuration Options

### Basic Configuration (Required)

```bash
# Auth0 credentials (from your Auth0 dashboard)
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"

# JWT secret (generate a secure random string)
export FMCP_JWT_SECRET=$(openssl rand -base64 32)
```

### Advanced Configuration (Optional)

```bash
# Custom base URL (for production deployments)
export FMCP_BASE_URL="https://api.yourdomain.com"

# Custom CORS origins (comma-separated)
export FMCP_ALLOWED_ORIGINS="https://app1.com,https://app2.com"

# Custom callback URL (override auto-detection)
export AUTH0_CALLBACK_URL="https://custom.com/auth/callback"

# Custom Auth0 audience
export AUTH0_AUDIENCE="https://your-api"
```

---

## 🎯 Common Use Cases

### Use Case 1: Development with GitHub Codespaces

```bash
# 1. Set up Auth0 with wildcard URLs (one-time)
# In Auth0 dashboard, add:
#   Allowed Callback URLs: https://*.app.github.dev/auth/callback
#   Allowed Logout URLs: https://*.app.github.dev/
#   Allowed Web Origins: https://*.app.github.dev

# 2. Set environment variables in Codespace
export AUTH0_DOMAIN="dev-xxx.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# 3. Run registry package with OAuth
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0

# 4. Make port 8099 public (in VSCode Ports panel)
# 5. Access the URL shown in terminal output
```

### Use Case 2: Production Deployment

```bash
# 1. Set custom domain
export FMCP_BASE_URL="https://api.yourdomain.com"

# 2. Configure Auth0 with production URLs
# In Auth0 dashboard, add:
#   Allowed Callback URLs: https://api.yourdomain.com/auth/callback
#   Allowed Logout URLs: https://api.yourdomain.com/
#   Allowed Web Origins: https://api.yourdomain.com

# 3. Set Auth0 credentials
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# 4. Run with OAuth
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0

# 5. Set up reverse proxy (Nginx, Caddy, etc.) for SSL/TLS
```

### Use Case 3: Multiple Registry Packages

```bash
# Install multiple packages
fluidmcp install Airbnb/airbnb@0.1.0
fluidmcp install GoogleMaps/googlemaps@1.0.0

# Create configuration file
cat > config.json <<EOF
{
  "mcpServers": {
    "airbnb": "Airbnb/airbnb@0.1.0",
    "googlemaps": "GoogleMaps/googlemaps@1.0.0"
  }
}
EOF

# Run all with OAuth
fluidmcp run config.json --file --start-server --auth0

# All packages now require authentication!
```

---

## 🐛 Troubleshooting

### Issue 1: "Callback URL mismatch" Error

**Problem**: Auth0 shows callback URL doesn't match.

**Solution**:
```bash
# Get your exact callback URL
python print-auth0-urls.py

# Copy the exact URL to Auth0 application settings
# Make sure protocol (http vs https) matches
```

### Issue 2: "Not authenticated" on All Requests

**Problem**: Every API call returns 401 Unauthorized.

**Causes**:
- OAuth not enabled (missing `--auth0` flag)
- Auth0 credentials not set
- JWT token expired or invalid

**Solution**:
```bash
# Verify OAuth is enabled
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0

# Check environment variables
echo $AUTH0_DOMAIN
echo $AUTH0_CLIENT_ID
echo $FMCP_JWT_SECRET

# Log in again to get fresh JWT token
```

### Issue 3: Port Not Accessible in Codespaces

**Problem**: External users can't access the server.

**Solution**:
```
1. Open Ports panel in VSCode (Cmd/Ctrl + Shift + P)
2. Search "Ports: Focus on Ports View"
3. Find port 8099
4. Right-click → Change Port Visibility → Public
```

### Issue 4: CORS Errors in Browser

**Problem**: Browser console shows CORS policy errors.

**Solution**:
```bash
# FluidMCP auto-configures CORS, but if you have custom origins:
export FMCP_ALLOWED_ORIGINS="https://your-frontend.com,https://app.com"

# Restart server
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0
```

---

## 📚 Related Documentation

- **OAuth Setup Guide**: [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md)
- **Running FluidMCP**: [HOW_TO_RUN.md](HOW_TO_RUN.md)
- **Auth0 Wildcards**: [AUTH0_WILDCARD_SETUP.md](AUTH0_WILDCARD_SETUP.md)
- **Full Documentation**: [INDEX.md](INDEX.md)

---

## 💡 Key Takeaways

✅ **Simple Setup**: Just add `--auth0` flag to your run command
✅ **No Code Changes**: OAuth is already built into FluidMCP
✅ **Automatic Detection**: URLs configured automatically for your environment
✅ **Production Ready**: Use custom domains for production deployments
✅ **Secure by Default**: All endpoints protected when OAuth is enabled
✅ **Multiple Providers**: Support GitHub, Google, Microsoft, and more

---

**Need help?** Check [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md) for detailed Auth0 setup instructions.
