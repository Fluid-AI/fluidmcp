#!/bin/bash
# Auth0 Implementation Testing Script
# This script helps verify the Auth0 integration is working correctly

set -e

echo "========================================"
echo "Auth0 Implementation Testing Script"
echo "========================================"
echo ""

# Check if Auth0 environment variables are set
echo "1. Checking Auth0 Configuration..."
echo "-----------------------------------"

if [ -z "$FMCP_AUTH0_DOMAIN" ]; then
    echo "❌ FMCP_AUTH0_DOMAIN not set"
    MISSING_VARS=1
else
    echo "✅ FMCP_AUTH0_DOMAIN: $FMCP_AUTH0_DOMAIN"
fi

if [ -z "$FMCP_AUTH0_CLIENT_ID" ]; then
    echo "❌ FMCP_AUTH0_CLIENT_ID not set"
    MISSING_VARS=1
else
    echo "✅ FMCP_AUTH0_CLIENT_ID: $FMCP_AUTH0_CLIENT_ID"
fi

if [ -z "$FMCP_AUTH0_CLIENT_SECRET" ]; then
    echo "❌ FMCP_AUTH0_CLIENT_SECRET not set"
    MISSING_VARS=1
else
    echo "✅ FMCP_AUTH0_CLIENT_SECRET: ${FMCP_AUTH0_CLIENT_SECRET:0:4}****"
fi

if [ -z "$FMCP_AUTH0_AUDIENCE" ]; then
    echo "⚠️  FMCP_AUTH0_AUDIENCE not set (optional but recommended)"
else
    echo "✅ FMCP_AUTH0_AUDIENCE: $FMCP_AUTH0_AUDIENCE"
fi

if [ -n "$MISSING_VARS" ]; then
    echo ""
    echo "Missing required Auth0 environment variables!"
    echo "Please set them in .env file:"
    echo ""
    echo "FMCP_AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com"
    echo "FMCP_AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe"
    echo "FMCP_AUTH0_CLIENT_SECRET=your-secret-here"
    echo "FMCP_AUTH0_AUDIENCE=https://api.fluidmcp.com"
    echo ""
    exit 1
fi

echo ""
echo "2. Checking Backend Implementation..."
echo "--------------------------------------"

# Check if auth module files exist
AUTH_FILES=(
    "fluidmcp/cli/auth/__init__.py"
    "fluidmcp/cli/auth/config.py"
    "fluidmcp/cli/auth/oauth_client.py"
    "fluidmcp/cli/auth/jwt_validator.py"
    "fluidmcp/cli/auth/dependencies.py"
    "fluidmcp/cli/auth/routes.py"
    "fluidmcp/cli/auth/url_utils.py"
)

for file in "${AUTH_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file (missing)"
    fi
done

echo ""
echo "3. Checking Frontend Implementation..."
echo "---------------------------------------"

FRONTEND_FILES=(
    "fluidmcp/frontend/src/contexts/AuthContext.tsx"
    "fluidmcp/frontend/src/services/auth.ts"
)

for file in "${FRONTEND_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file (missing)"
    fi
done

echo ""
echo "4. Starting Backend Server..."
echo "------------------------------"
echo "Starting FluidMCP with Auth0 enabled..."
echo "Press Ctrl+C to stop the server and continue testing"
echo ""

# Start server in background
fmcp serve --auth0 --in-memory --allow-all-origins --port 8099 &
SERVER_PID=$!

# Wait for server to start
sleep 5

echo ""
echo "5. Testing Auth0 Endpoints..."
echo "-------------------------------"

# Test /auth/config endpoint
echo "Testing GET /auth/config..."
CONFIG_RESPONSE=$(curl -s http://localhost:8099/auth/config)
echo "Response: $CONFIG_RESPONSE"

if echo "$CONFIG_RESPONSE" | grep -q "\"enabled\":true"; then
    echo "✅ OAuth is enabled"
else
    echo "❌ OAuth not enabled or endpoint not working"
fi

echo ""
echo "Testing GET /health..."
HEALTH_RESPONSE=$(curl -s http://localhost:8099/health)
echo "Response: $HEALTH_RESPONSE"

echo ""
echo "========================================"
echo "Manual Testing Instructions"
echo "========================================"
echo ""
echo "Server is running at: http://localhost:8099"
echo ""
echo "Test the OAuth flow:"
echo "1. Open browser: http://localhost:8099/auth/config"
echo "   Expected: {\"enabled\": true, ...}"
echo ""
echo "2. Navigate to: http://localhost:8099/auth/login"
echo "   Expected: Redirect to Auth0 login page"
echo ""
echo "3. Login with test user"
echo "   Expected: Redirect back with success message"
echo ""
echo "4. Check: http://localhost:8099/auth/me"
echo "   Expected: User info displayed"
echo ""
echo "5. Frontend: http://localhost:8099/ui"
echo "   Expected: Dashboard loads (no login UI yet)"
echo ""
echo "Press Enter to stop the server..."
read

# Kill server
kill $SERVER_PID 2>/dev/null || true

echo ""
echo "========================================"
echo "Testing Complete"
echo "========================================"
echo ""
echo "Review the results above and check:"
echo "- All Auth0 environment variables are set"
echo "- All backend auth files exist"
echo "- Server starts with --auth0 flag"
echo "- /auth/config returns enabled:true"
echo ""
echo "For detailed analysis, see: AUTH0_IMPLEMENTATION_REVIEW.md"
