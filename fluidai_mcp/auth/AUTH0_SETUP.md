# Auth0 Setup Guide for FluidMCP

This guide walks you through setting up Auth0 OAuth authentication for FluidMCP.

## Prerequisites

- An Auth0 account (sign up at https://auth0.com - free tier available)
- FluidMCP installed

## Step 1: Create Auth0 Tenant

1. Go to https://auth0.com and sign up/login
2. Create a new tenant (e.g., `fluidmcp`)
3. Choose a region closest to your users
4. Note your domain: `fluidmcp.us.auth0.com` (or your chosen region)

## Step 2: Create Application

1. In Auth0 Dashboard, go to **Applications** → **Applications**
2. Click **Create Application**
3. Name: `FluidMCP Gateway`
4. Type: **Regular Web Applications**
5. Click **Create**

## Step 3: Configure Application Settings

In your application settings:

### Basic Information
- Note your **Domain**, **Client ID**, and **Client Secret**

### Application URIs

**IMPORTANT:** FluidMCP automatically detects your environment and generates the correct URLs. When you run the server with `--auth0` flag, it will display the exact URLs you need to add to Auth0.

#### For Local Development:
```
Allowed Callback URLs:
http://localhost:8099/auth/callback

Allowed Logout URLs:
http://localhost:8099/

Allowed Web Origins:
http://localhost:8099
```

#### For GitHub Codespaces:
FluidMCP will detect your Codespace URL automatically. The URLs will look like:
```
Allowed Callback URLs:
https://your-codespace-name-8099.app.github.dev/auth/callback

Allowed Logout URLs:
https://your-codespace-name-8099.app.github.dev/

Allowed Web Origins:
https://your-codespace-name-8099.app.github.dev
```

**Tip:** Run `fluidmcp run all --start-server --auth0` and it will print the exact URLs to copy into Auth0.

#### For Gitpod:
FluidMCP will detect your Gitpod workspace URL automatically.

#### For Custom Domains:
Set the `FMCP_BASE_URL` environment variable:
```bash
export FMCP_BASE_URL="https://api.yourdomain.com"
```

### Advanced Settings (Optional)
- Grant Types: Ensure "Authorization Code" is enabled
- Save Changes

## Step 4: Enable Social Connections

### GitHub
1. Go to **Authentication** → **Social**
2. Click **GitHub**
3. Enable the connection
4. (Optional) Add your own GitHub OAuth app credentials
5. Connect to your FluidMCP application

### Google
1. Go to **Authentication** → **Social**
2. Click **Google**
3. Enable the connection
4. (Optional) Add your own Google OAuth credentials
5. Connect to your FluidMCP application

### Enterprise Connections (Zoho, Atlassian, Confluence)
1. Go to **Authentication** → **Enterprise**
2. Choose **SAML** or **OpenID Connect**
3. Follow provider-specific setup:
   - **Zoho**: Configure SAML with Zoho SAML settings
   - **Atlassian/Confluence**: Use OpenID Connect or SAML
4. Connect to your FluidMCP application

## Step 5: Set Environment Variables

Create environment variables for FluidMCP:

```bash
# Required: Auth0 Configuration
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id_here"
export AUTH0_CLIENT_SECRET="your_client_secret_here"

# Required: JWT Secret (generate a random secret)
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Optional: Override auto-detected callback URL
# export AUTH0_CALLBACK_URL="https://yourdomain.com/auth/callback"

# Optional: Custom base URL (for production deployments)
# export FMCP_BASE_URL="https://api.yourdomain.com"

# Optional: Custom CORS origins (comma-separated)
# export FMCP_ALLOWED_ORIGINS="https://app.yourdomain.com,https://admin.yourdomain.com"

# Optional: API Audience (if using Auth0 API)
# export AUTH0_AUDIENCE="https://your-api-identifier"
```

**For Windows (PowerShell):**
```powershell
$env:AUTH0_DOMAIN="your-tenant.us.auth0.com"
$env:AUTH0_CLIENT_ID="your_client_id_here"
$env:AUTH0_CLIENT_SECRET="your_client_secret_here"
$env:FMCP_JWT_SECRET="your_generated_secret"
```

### Environment Detection

FluidMCP automatically detects your environment:
- **Local Development**: Uses `http://localhost:8099`
- **GitHub Codespaces**: Automatically uses Codespaces URL
- **Gitpod**: Automatically uses Gitpod workspace URL
- **Custom Deployment**: Set `FMCP_BASE_URL` for your domain

**Note:** You don't need to set `AUTH0_CALLBACK_URL` unless you want to override the auto-detected URL.

## Step 6: Run FluidMCP with Auth0

```bash
fluidmcp run all --start-server --auth0
```

**The server will automatically display the URLs you need!** Look for output like:

```
======================================================================
🔐 Auth0 OAuth Configuration
======================================================================
📍 Environment: CODESPACES
🌐 Detected Remote Environment

🔗 URLs for your application:
   Base URL:     https://your-codespace-8099.app.github.dev
   Login URL:    https://your-codespace-8099.app.github.dev/
   Swagger UI:   https://your-codespace-8099.app.github.dev/docs
   Callback URL: https://your-codespace-8099.app.github.dev/auth/callback

⚙️  Auth0 Dashboard Configuration:
   Add these URLs to your Auth0 application settings:

   Allowed Callback URLs:
   https://your-codespace-8099.app.github.dev/auth/callback

   Allowed Logout URLs:
   https://your-codespace-8099.app.github.dev/

   Allowed Web Origins:
   https://your-codespace-8099.app.github.dev
======================================================================
```

**Copy these URLs and add them to your Auth0 application settings!**

## Step 7: Test Authentication

1. Open browser to the **Base URL** shown in the server output
2. Click "Sign in with Auth0"
3. Choose your identity provider (GitHub, Google, etc.)
4. Authorize the application
5. You'll be redirected back and logged in
6. Access Swagger UI at the **Swagger UI URL** shown in the output

## Troubleshooting

### "Invalid state parameter" error
- Check that cookies are enabled
- Ensure callback URL matches **exactly** in Auth0 settings (including https:// vs http://)
- If using Codespaces, make sure you added the correct Codespaces URL to Auth0
- Try clearing cookies and restarting the server

### "Callback URL mismatch" error
- The URL in Auth0 settings must **exactly match** the detected URL
- Copy the URL from the server startup output (not manually typed)
- In Codespaces, the URL changes each time you restart - update Auth0 accordingly
- Consider using `FMCP_BASE_URL` env var for a stable URL

### "Unauthorized" error
- Verify all environment variables are set correctly
- Check that your Auth0 application is not using development keys in production
- Ensure `FMCP_JWT_SECRET` is set

### Social connection not appearing
- Ensure the connection is enabled in Auth0 Dashboard
- Verify the connection is linked to your application

### Token expires too quickly
- Adjust token expiration: `export FMCP_JWT_ACCESS_EXPIRE_MIN=60`

### CORS errors in browser
- FluidMCP automatically configures CORS for detected environments
- For custom domains, set `FMCP_ALLOWED_ORIGINS`
- Check browser console for specific CORS error messages

### Codespaces-specific issues
- **Port not accessible**: Ensure port 8099 is set to "Public" in Codespaces ports panel
- **URL changed**: Restart changes the Codespace URL - update Auth0 with new URL
- **Cookie issues**: Some browsers block third-party cookies - try different browser

## Production Deployment

For production use:

1. **Use HTTPS**: Deploy behind a reverse proxy with SSL
2. **Update URLs**: Change callback URLs to your production domain
3. **Secure secrets**: Use secret management (AWS Secrets Manager, HashiCorp Vault, etc.)
4. **Enable MFA**: Configure Multi-Factor Authentication in Auth0
5. **Monitor**: Set up Auth0 logging and monitoring

## Example Production Setup

```bash
# Production environment variables
export AUTH0_DOMAIN="fluidmcp.us.auth0.com"
export AUTH0_CLIENT_ID="prod_client_id"
export AUTH0_CLIENT_SECRET="prod_client_secret"
export AUTH0_CALLBACK_URL="https://api.yourdomain.com/auth/callback"
export FMCP_JWT_SECRET="your_secure_random_secret"
export FMCP_ALLOWED_ORIGINS="https://yourdomain.com"
```

## Security Best Practices

1. **Never commit secrets** to version control
2. **Rotate secrets** regularly
3. **Use strong JWT secrets** (32+ characters, random)
4. **Enable Auth0 Anomaly Detection** in dashboard
5. **Review Auth0 logs** regularly
6. **Limit token lifetime** for sensitive operations

## Support

- Auth0 Documentation: https://auth0.com/docs
- FluidMCP Issues: https://github.com/your-org/fluidmcp/issues
- Auth0 Community: https://community.auth0.com
