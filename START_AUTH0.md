# Quick Start Guide - Auth0 Authentication

## Current Status
Your Auth0 configuration:
- **Domain**: `dev-4anz4n3tvh3iyixx.us.auth0.com`
- **Client ID**: `k80RDWadsrIXntnv7kbai1i3aL6ZgHRe`

## Step 1: Fix Auth0 Application Settings (IMPORTANT!)

1. Go to https://manage.auth0.com
2. Navigate to **Applications** → **Applications**
3. Click on your application
4. Under **Application URIs**, update these URLs to use **HTTP** (not HTTPS):

```
Allowed Callback URLs:
http://localhost:8099/auth/callback

Allowed Logout URLs:
http://localhost:8099/

Allowed Web Origins:
http://localhost:8099
```

5. Click **Save Changes** at the bottom

## Step 2: Set Environment Variables and Start Server

Run these commands in your terminal:

```bash
# Navigate to fluidmcp directory
cd /workspaces/fluidmcp

# Set Auth0 credentials
export AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com
export AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe
export AUTH0_CLIENT_SECRET=YOUR_ACTUAL_CLIENT_SECRET_HERE

# Generate JWT secret
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Start the server with Auth0
fluidmcp run all --start-server --auth0
```

## Step 3: Test Authentication

1. Open browser to: `http://localhost:8099/`
2. Click on "Continue with Google" (or any other provider)
3. Login with your Google account
4. You should be redirected back with authentication

## Troubleshooting

### If you still get "Callback URL mismatch" error:

1. **Double-check Auth0 settings** - Make sure you saved the changes in Auth0 Dashboard
2. **Wait 1-2 minutes** - Auth0 sometimes takes a moment to propagate configuration changes
3. **Clear browser cache** - The error page might be cached
4. **Verify environment variables** in the terminal where you run the server:
   ```bash
   echo $AUTH0_DOMAIN
   echo $AUTH0_CLIENT_ID
   ```

### If environment variables are not set:

Make sure you run the `export` commands in the **same terminal window** where you'll run `fluidmcp`.

### To persist environment variables:

Add them to your `~/.bashrc` or create a startup script:

```bash
# Create a file to source
cat > /workspaces/fluidmcp/.env.local << 'EOF'
export AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com
export AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe
export AUTH0_CLIENT_SECRET=YOUR_SECRET_HERE
export FMCP_JWT_SECRET=$(openssl rand -base64 32)
EOF

# Then source it before running:
source .env.local
fluidmcp run all --start-server --auth0
```

## Need Help?

If you're still having issues, check:
1. Is your Auth0 application configured with HTTP callback URLs?
2. Are the environment variables set in the current shell?
3. Did you save the changes in Auth0 Dashboard?
