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
Configure these URLs (adjust port if needed):

```
Allowed Callback URLs:
http://localhost:8099/auth/callback

Allowed Logout URLs:
http://localhost:8099/

Allowed Web Origins:
http://localhost:8099
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
# Auth0 Configuration
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id_here"
export AUTH0_CLIENT_SECRET="your_client_secret_here"
export AUTH0_CALLBACK_URL="http://localhost:8099/auth/callback"  # Optional, has default

# JWT Secret (generate a random secret)
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Optional: API Audience (if using Auth0 API)
export AUTH0_AUDIENCE="https://your-api-identifier"
```

**For Windows (PowerShell):**
```powershell
$env:AUTH0_DOMAIN="your-tenant.us.auth0.com"
$env:AUTH0_CLIENT_ID="your_client_id_here"
$env:AUTH0_CLIENT_SECRET="your_client_secret_here"
$env:FMCP_JWT_SECRET="your_generated_secret"
```

## Step 6: Run FluidMCP with Auth0

```bash
fluidmcp run all --start-server --auth0
```

## Step 7: Test Authentication

1. Open browser to `http://localhost:8099/`
2. Click "Sign in with Auth0"
3. Choose your identity provider (GitHub, Google, etc.)
4. Authorize the application
5. You'll be redirected back and logged in
6. Access Swagger UI at `http://localhost:8099/docs`

## Troubleshooting

### "Invalid state parameter" error
- Check that cookies are enabled
- Ensure callback URL matches exactly in Auth0 settings

### "Unauthorized" error
- Verify all environment variables are set correctly
- Check that your Auth0 application is not using development keys in production

### Social connection not appearing
- Ensure the connection is enabled in Auth0 Dashboard
- Verify the connection is linked to your application

### Token expires too quickly
- Adjust token expiration: `export FMCP_JWT_ACCESS_EXPIRE_MIN=60`

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
