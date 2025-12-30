#!/usr/bin/env python3
"""
Debug script to verify Auth0 configuration and callback URL
"""

import os
import sys

print("🔍 Auth0 Configuration Debug")
print("=" * 60)
print()

# Check environment variables
print("Environment Variables:")
print(f"  AUTH0_DOMAIN: {os.getenv('AUTH0_DOMAIN', '❌ NOT SET')}")
print(f"  AUTH0_CLIENT_ID: {os.getenv('AUTH0_CLIENT_ID', '❌ NOT SET')}")
print(f"  AUTH0_CLIENT_SECRET: {'✅ SET' if os.getenv('AUTH0_CLIENT_SECRET') else '❌ NOT SET'}")
print(f"  FMCP_JWT_SECRET: {'✅ SET' if os.getenv('FMCP_JWT_SECRET') else '❌ NOT SET'}")
print(f"  AUTH0_CALLBACK_URL: {os.getenv('AUTH0_CALLBACK_URL', 'Using default: http://localhost:8099/auth/callback')}")
print()

# Check if config module can be loaded
try:
    sys.path.insert(0, '/workspaces/fluidmcp')
    from fluidai_mcp.auth.config import Auth0Config

    config = Auth0Config.from_env()

    print("Auth0Config Loaded:")
    print(f"  Domain: {config.domain}")
    print(f"  Client ID: {config.client_id}")
    print(f"  Callback URL: {config.callback_url}")
    print()

    # Generate authorization URL to see what's being sent
    from fluidai_mcp.auth.oauth_client import Auth0Client

    client = Auth0Client(config)
    test_url = client.get_authorization_url(
        state="test_state_123",
        redirect_uri=config.callback_url,
        connection="google-oauth2"
    )

    print("Generated Authorization URL:")
    print(f"  {test_url}")
    print()

    # Check redirect_uri parameter in URL
    if "redirect_uri=" in test_url:
        import urllib.parse
        parsed = urllib.parse.urlparse(test_url)
        params = urllib.parse.parse_qs(parsed.query)
        redirect_uri = params.get('redirect_uri', ['NOT FOUND'])[0]

        print(f"Extracted redirect_uri parameter: {redirect_uri}")
        print()

        print("✅ This is the EXACT URL you need to add in Auth0 Dashboard:")
        print()
        print(f"  {urllib.parse.unquote(redirect_uri)}")
        print()

except Exception as e:
    print(f"❌ Error loading Auth0 config: {e}")
    print()
    print("Make sure environment variables are set:")
    print("  export AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com")
    print("  export AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe")
    print("  export AUTH0_CLIENT_SECRET=your_secret_here")
    print("  export FMCP_JWT_SECRET=$(openssl rand -base64 32)")
    print()

print("=" * 60)
print()
print("To fix the callback URL mismatch:")
print("1. Copy the exact redirect_uri shown above")
print("2. Go to https://manage.auth0.com")
print("3. Applications > Your App > Settings")
print("4. Paste it in 'Allowed Callback URLs'")
print("5. Click 'Save Changes'")
print("6. Wait 30-60 seconds for changes to propagate")
