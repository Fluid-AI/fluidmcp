#!/bin/bash

echo "🔐 FluidMCP Auth0 Setup Helper"
echo "==============================="
echo ""

# Check if .env.auth0 exists
if [ ! -f ".env.auth0" ]; then
    echo "❌ Error: .env.auth0 file not found!"
    echo "Please create .env.auth0 with your Auth0 credentials."
    exit 1
fi

# Generate JWT secret if needed
if grep -q "your_random_jwt_secret_here" .env.auth0; then
    echo "📝 Generating JWT secret..."
    JWT_SECRET=$(openssl rand -base64 32)
    sed -i "s|your_random_jwt_secret_here|${JWT_SECRET}|g" .env.auth0
    echo "✅ JWT secret generated"
fi

# Load environment variables
echo "📥 Loading Auth0 configuration..."
export $(cat .env.auth0 | grep -v '^#' | xargs)

# Check if CLIENT_SECRET is set
if [ "$AUTH0_CLIENT_SECRET" = "your_client_secret_here" ]; then
    echo ""
    echo "⚠️  You need to set your Auth0 Client Secret!"
    echo ""
    echo "To get your Client Secret:"
    echo "1. Go to https://manage.auth0.com"
    echo "2. Navigate to Applications > Applications"
    echo "3. Click on your 'FluidMCP Gateway' application"
    echo "4. Copy the 'Client Secret' value"
    echo "5. Update AUTH0_CLIENT_SECRET in .env.auth0"
    echo ""
    exit 1
fi

# Display configuration
echo ""
echo "✅ Auth0 Configuration Loaded:"
echo "   Domain: $AUTH0_DOMAIN"
echo "   Client ID: $AUTH0_CLIENT_ID"
echo "   Callback URL: $AUTH0_CALLBACK_URL"
echo ""

# Check Auth0 Application Settings
echo "📋 Please verify your Auth0 Application Settings:"
echo ""
echo "In your Auth0 Dashboard (https://manage.auth0.com):"
echo "1. Go to Applications > Applications > FluidMCP Gateway"
echo "2. Under 'Application URIs' section, set:"
echo ""
echo "   Allowed Callback URLs:"
echo "   http://localhost:8099/auth/callback"
echo ""
echo "   Allowed Logout URLs:"
echo "   http://localhost:8099/"
echo ""
echo "   Allowed Web Origins:"
echo "   http://localhost:8099"
echo ""
echo "3. Click 'Save Changes'"
echo ""
echo "Then run: source .env.auth0 && fluidmcp run all --start-server --auth0"
