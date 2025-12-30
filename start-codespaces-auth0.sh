#!/bin/bash

echo "🔐 Starting FluidMCP with Auth0 on GitHub Codespaces"
echo "====================================================="
echo ""

# Check if CLIENT_SECRET is provided
if [ -z "$1" ]; then
    echo "❌ Error: Auth0 Client Secret not provided"
    echo ""
    echo "Usage: ./start-codespaces-auth0.sh YOUR_CLIENT_SECRET"
    echo ""
    echo "To get your Client Secret:"
    echo "1. Go to https://manage.auth0.com"
    echo "2. Navigate to Applications > Applications"
    echo "3. Click on your application"
    echo "4. Copy the 'Client Secret' value"
    echo ""
    exit 1
fi

# Detect Codespaces URL
if [ -n "$CODESPACE_NAME" ] && [ -n "$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN" ]; then
    CODESPACES_URL="https://${CODESPACE_NAME}-8099.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
    CALLBACK_URL="${CODESPACES_URL}/auth/callback"
else
    echo "⚠️  Warning: Unable to detect Codespaces environment"
    echo "Using detected URL: https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev"
    CODESPACES_URL="https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev"
    CALLBACK_URL="${CODESPACES_URL}/auth/callback"
fi

# Set environment variables for Codespaces
export AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com
export AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe
export AUTH0_CLIENT_SECRET=$1
export AUTH0_CALLBACK_URL=$CALLBACK_URL
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

echo "✅ Environment variables configured"
echo "   Domain: $AUTH0_DOMAIN"
echo "   Client ID: $AUTH0_CLIENT_ID"
echo "   Callback URL: $AUTH0_CALLBACK_URL"
echo "   Codespaces URL: $CODESPACES_URL"
echo ""

echo "⚠️  IMPORTANT: Verify your Auth0 Application Settings"
echo ""
echo "In Auth0 Dashboard (https://manage.auth0.com):"
echo "Application > Settings > Application URIs should have:"
echo ""
echo "  Allowed Callback URLs:"
echo "  $CALLBACK_URL"
echo ""
echo "  Allowed Logout URLs:"
echo "  $CODESPACES_URL/"
echo ""
echo "  Allowed Web Origins:"
echo "  $CODESPACES_URL"
echo ""
read -p "Have you configured these URLs in Auth0? (y/n): " confirm

if [ "$confirm" != "y" ]; then
    echo ""
    echo "Please configure Auth0 first:"
    echo "1. Go to https://manage.auth0.com"
    echo "2. Applications > Your App > Settings"
    echo "3. Update the URLs shown above"
    echo "4. Click 'Save Changes'"
    echo "5. Wait 30-60 seconds"
    echo "6. Run this script again"
    exit 0
fi

echo ""
echo "🚀 Starting FluidMCP server..."
echo ""
echo "Access FluidMCP at: $CODESPACES_URL"
echo ""

# Start the server
fluidmcp run all --start-server --auth0
