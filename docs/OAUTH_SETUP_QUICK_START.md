# FluidMCP OAuth Setup - Quick Start Guide

FluidMCP now automatically detects your environment (Codespaces, Gitpod, local, custom) and generates the correct OAuth callback URLs! 🎉

## 🚀 Quick Setup (5 minutes)

### Step 1: Get Your URLs

Run this command to see your environment-specific URLs:

```bash
python print-auth0-urls.py
```

**In Codespaces, your URL will look like:**
```
https://your-codespace-name-8099.app.github.dev
```

### Step 2: Set Up Auth0 (Free Tier Available)

1. **Create Auth0 Account**: Go to https://auth0.com/signup
2. **Create Application**:
   - Go to Applications → Create Application
   - Name: "FluidMCP Gateway"
   - Type: "Regular Web Applications"
3. **Configure URLs with Wildcards** (⭐ RECOMMENDED):

   **For GitHub Codespaces (works forever!):**
   ```
   Allowed Callback URLs:
   https://*.app.github.dev/auth/callback,http://localhost:*/auth/callback

   Allowed Logout URLs:
   https://*.app.github.dev/,http://localhost:*/

   Allowed Web Origins:
   https://*.app.github.dev,http://localhost:*
   ```

   **Why wildcards?**
   - ✅ Works with ALL your Codespaces automatically
   - ✅ Never need to update Auth0 again
   - ✅ Secure (requires GitHub authentication)
   - ✅ Supports both Codespaces and local development

4. **Enable Social Connections** (optional):
   - Go to Authentication → Social
   - Enable: GitHub, Google, etc.
5. **Copy Credentials**:
   - Note your Domain, Client ID, and Client Secret

### Step 3: Set Environment Variables

```bash
# Required
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Optional (auto-detected if not set)
# export AUTH0_CALLBACK_URL="https://custom-domain.com/auth/callback"
# export FMCP_BASE_URL="https://api.yourdomain.com"
```

### Step 4: Run FluidMCP with Auth0

```bash
fluidmcp run examples/sample-config.json --file --start-server --auth0
```

The server will display the exact URLs you need! 🎯

### Step 5: Test It

1. Open the Base URL shown in the output
2. Click "Sign in with Auth0"
3. Choose your provider (GitHub, Google, etc.)
4. Done! You're authenticated 🔐

### Using with Registry Packages

When running packages from FluidMCP registry (like Airbnb, Google Maps):

```bash
# Install package
fluidmcp install Airbnb/airbnb@0.1.0

# Run with OAuth authentication
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0
```

**Result:**
- Users must authenticate before accessing the Airbnb API
- All `/docs` and API endpoints require JWT token
- Provides enterprise-grade security for registry packages

---

## 🌐 Environment Support

FluidMCP automatically detects and configures URLs for:

| Environment | Detection | URL Format |
|-------------|-----------|------------|
| **Local Development** | Default | `http://localhost:8099` |
| **GitHub Codespaces** | Automatic | `https://codespace-8099.app.github.dev` |
| **Gitpod** | Automatic | `https://8099-workspace-url` |
| **Custom Domain** | Via `FMCP_BASE_URL` | Your custom URL |

---

## 🔧 Advanced Configuration

### Custom Base URL

For production or custom deployments:

```bash
export FMCP_BASE_URL="https://api.yourdomain.com"
```

### Custom CORS Origins

To allow specific origins:

```bash
export FMCP_ALLOWED_ORIGINS="https://app.yourdomain.com,https://admin.yourdomain.com"
```

### Override Callback URL

If you need to manually set the callback URL:

```bash
export AUTH0_CALLBACK_URL="https://yourdomain.com/auth/callback"
```

---

## 🐛 Troubleshooting

### "Callback URL mismatch" Error

**Problem**: The URL in Auth0 doesn't match your detected URL.

**Solution**:
1. Run `python print-auth0-urls.py` to get the exact URL
2. Copy it to Auth0 settings (don't type manually)
3. Make sure protocol matches (http vs https)

### Codespaces Port Not Accessible

**Problem**: Port 8099 returns connection refused.

**Solution**:
1. Open Ports panel in VSCode (Cmd/Ctrl + Shift + P → "Ports: Focus on Ports View")
2. Find port 8099
3. Right-click → Change Port Visibility → **Public**

### Codespaces URL Changed

**Problem**: OAuth stopped working after restarting Codespace.

**Solution**: Codespace URLs change on restart. Two options:
1. **Quick Fix**: Update Auth0 with new URL (run `python print-auth0-urls.py`)
2. **Permanent**: Set `FMCP_BASE_URL` to a stable URL (use port forwarding or custom domain)

### CORS Errors in Browser

**Problem**: Browser shows CORS policy errors.

**Solution**: FluidMCP auto-configures CORS for detected environments. If you see errors:
1. Check that you're accessing the correct URL (shown in server output)
2. For custom domains, set `FMCP_ALLOWED_ORIGINS`
3. Clear browser cache and cookies

### "Invalid state parameter" Error

**Problem**: OAuth flow fails with state validation error.

**Solution**:
1. Ensure cookies are enabled in your browser
2. Try a different browser (some block third-party cookies)
3. Clear cookies and try again
4. Check that callback URL matches exactly in Auth0

---

## 📚 More Information

- **Wildcard Setup Guide**: See [AUTH0_WILDCARD_SETUP.md](AUTH0_WILDCARD_SETUP.md)
- **Registry Package Auth**: See [REGISTRY_PACKAGE_AUTH.md](REGISTRY_PACKAGE_AUTH.md)
- **Auth0 Documentation**: https://auth0.com/docs
- **Report Issues**: https://github.com/Fluid-AI/fluidmcp/issues

---

## 🎯 Summary

✅ **No manual URL configuration needed** - FluidMCP detects your environment
✅ **Works in Codespaces, Gitpod, local, and custom domains**
✅ **Automatic CORS configuration**
✅ **Clear error messages and troubleshooting**
✅ **Production-ready with custom domain support**

**That's it! Your OAuth is now dynamic and environment-aware.** 🚀
