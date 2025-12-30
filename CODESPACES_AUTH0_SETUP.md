# Auth0 Setup for GitHub Codespaces

## Your Codespaces Configuration

**Your FluidMCP URL**: `https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev`

## Step 1: Update Auth0 Application Settings

1. Go to https://manage.auth0.com
2. Navigate to **Applications** → **Applications**
3. Click on your application
4. Under **Application URIs**, update these URLs:

### Copy and Paste These Exact URLs:

```
Allowed Callback URLs:
https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/auth/callback

Allowed Logout URLs:
https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/

Allowed Web Origins:
https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev
```

5. **Click "Save Changes"** at the bottom
6. **Wait 30-60 seconds** for changes to propagate

## Step 2: Set Environment Variables with Codespaces URL

Run these commands in your Codespaces terminal:

```bash
# Set Auth0 credentials
export AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com
export AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe
export AUTH0_CLIENT_SECRET=YOUR_CLIENT_SECRET_HERE

# Set Codespaces callback URL
export AUTH0_CALLBACK_URL=https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/auth/callback

# Generate JWT secret
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Start the server with Auth0
fluidmcp run all --start-server --auth0
```

## Step 3: Test Authentication

1. Open your browser to: `https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/`
2. You should see the login page with individual provider buttons
3. Click on **"Continue with Google"** or any other provider
4. Login with your account
5. You should be redirected back to FluidMCP successfully

## Troubleshooting

### If you still get callback URL mismatch:

1. **Double-check Auth0 settings** - Make sure you copied the exact URLs above
2. **Save changes** - Don't forget to click "Save Changes" in Auth0 Dashboard
3. **Wait** - Auth0 sometimes takes 30-60 seconds to propagate changes
4. **Clear browser cache** - Try opening in an incognito/private window
5. **Restart server** - Stop and restart FluidMCP after Auth0 changes

### Verify environment variables:

```bash
echo "AUTH0_DOMAIN: $AUTH0_DOMAIN"
echo "AUTH0_CLIENT_ID: $AUTH0_CLIENT_ID"
echo "AUTH0_CALLBACK_URL: $AUTH0_CALLBACK_URL"
```

### Check server logs:

The server will show the actual callback URL being used when you try to login. Look for lines containing "redirect_uri" in the authorization URL.

## Important Notes

- **Codespaces URLs are unique** - Your URL `studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev` is specific to this Codespace instance
- **HTTPS required** - Codespaces always uses HTTPS, not HTTP
- **Port in URL** - The `-8099` in the URL corresponds to the FluidMCP server port
- **URL changes** - If you create a new Codespace, the URL will be different and you'll need to update Auth0 again

## Quick Start Script

Save this as `start-codespaces-auth0.sh`:

```bash
#!/bin/bash

echo "🔐 Starting FluidMCP with Auth0 on GitHub Codespaces"
echo "====================================================="
echo ""

# Check if CLIENT_SECRET is provided
if [ -z "$1" ]; then
    echo "❌ Error: Auth0 Client Secret not provided"
    echo ""
    echo "Usage: ./start-codespaces-auth0.sh YOUR_CLIENT_SECRET"
    exit 1
fi

# Set environment variables for Codespaces
export AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com
export AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe
export AUTH0_CLIENT_SECRET=$1
export AUTH0_CALLBACK_URL=https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/auth/callback
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

echo "✅ Environment variables configured"
echo "   Domain: $AUTH0_DOMAIN"
echo "   Client ID: $AUTH0_CLIENT_ID"
echo "   Callback URL: $AUTH0_CALLBACK_URL"
echo ""

echo "⚠️  Make sure Auth0 is configured with:"
echo "   https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/auth/callback"
echo ""

echo "🚀 Starting FluidMCP server..."
echo ""

# Start the server
fluidmcp run all --start-server --auth0
```

Make it executable:
```bash
chmod +x start-codespaces-auth0.sh
```

Run it:
```bash
./start-codespaces-auth0.sh YOUR_CLIENT_SECRET
```
