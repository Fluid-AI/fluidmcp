#!/bin/bash

echo "🔐 Starting FluidMCP with Auth0 Authentication"
echo "=============================================="
echo ""

# Check if CLIENT_SECRET is provided as argument
if [ -z "$1" ]; then
    echo "❌ Error: Auth0 Client Secret not provided"
    echo ""
    echo "Usage: ./start-with-auth0.sh YOUR_CLIENT_SECRET"
    echo ""
    echo "To get your Client Secret:"
    echo "1. Go to https://manage.auth0.com"
    echo "2. Navigate to Applications > Applications"
    echo "3. Click on your application"
    echo "4. Copy the 'Client Secret' value"
    echo ""
    exit 1
fi

# Set environment variables
export AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com
export AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe
export AUTH0_CLIENT_SECRET=$1
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

echo "✅ Environment variables configured"
echo "   Domain: $AUTH0_DOMAIN"
echo "   Client ID: $AUTH0_CLIENT_ID"
echo ""

echo "⚠️  IMPORTANT: Before continuing, verify your Auth0 settings:"
echo ""
echo "In Auth0 Dashboard (https://manage.auth0.com):"
echo "Application > Settings > Application URIs should have:"
echo ""
echo "  Allowed Callback URLs: http://localhost:8099/auth/callback"
echo "  Allowed Logout URLs: http://localhost:8099/"
echo "  Allowed Web Origins: http://localhost:8099"
echo ""
read -p "Have you configured these URLs? (y/n): " confirm

if [ "$confirm" != "y" ]; then
    echo ""
    echo "Please configure Auth0 first, then run this script again."
    exit 0
fi

echo ""
echo "🚀 Starting FluidMCP server..."
echo ""

# Start the server
fluidmcp run all --start-server --auth0
