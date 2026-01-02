#!/bin/bash

echo "🔍 Verifying Auth0 Setup for Codespaces"
echo "========================================"
echo ""

# Detect Codespaces URL
if [ -n "$CODESPACE_NAME" ] && [ -n "$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN" ]; then
    EXPECTED_URL="https://${CODESPACE_NAME}-8099.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
else
    EXPECTED_URL="https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev"
fi

echo "✅ Expected Codespaces URL: $EXPECTED_URL"
echo ""

# Check environment variables
echo "📋 Environment Variables:"
echo "   AUTH0_DOMAIN: ${AUTH0_DOMAIN:-❌ NOT SET}"
echo "   AUTH0_CLIENT_ID: ${AUTH0_CLIENT_ID:-❌ NOT SET}"
echo "   AUTH0_CLIENT_SECRET: ${AUTH0_CLIENT_SECRET:+✅ SET}"
echo "   FMCP_JWT_SECRET: ${FMCP_JWT_SECRET:+✅ SET}"
echo "   AUTH0_CALLBACK_URL: ${AUTH0_CALLBACK_URL:-❌ NOT SET}"
echo ""

# Check if callback URL matches expected
if [ "$AUTH0_CALLBACK_URL" == "${EXPECTED_URL}/auth/callback" ]; then
    echo "✅ AUTH0_CALLBACK_URL is correctly set!"
else
    echo "❌ AUTH0_CALLBACK_URL mismatch!"
    echo "   Current:  $AUTH0_CALLBACK_URL"
    echo "   Expected: ${EXPECTED_URL}/auth/callback"
    echo ""
    echo "Run this command to fix:"
    echo "   export AUTH0_CALLBACK_URL=${EXPECTED_URL}/auth/callback"
fi

echo ""
echo "📝 Auth0 Dashboard Configuration Required:"
echo ""
echo "Go to: https://manage.auth0.com"
echo "Navigate to: Applications > Your App > Settings"
echo ""
echo "Paste these URLs:"
echo ""
echo "Allowed Callback URLs:"
echo "${EXPECTED_URL}/auth/callback"
echo ""
echo "Allowed Logout URLs:"
echo "${EXPECTED_URL}/"
echo ""
echo "Allowed Web Origins:"
echo "${EXPECTED_URL}"
echo ""
echo "Then click 'Save Changes' and wait 60 seconds!"
