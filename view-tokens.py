#!/usr/bin/env python3
"""
Script to view Auth0 tokens and sessions stored in FluidMCP.

This helps debug and inspect authentication state.
"""

import sys
import os

# Add the fluidai_mcp package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fluidai_mcp.auth.session_store import session_store
from fluidai_mcp.auth.config import Auth0Config
from fluidai_mcp.auth.token_manager import TokenManager
from datetime import datetime
import json


def view_sessions():
    """Display all active sessions"""
    print("=" * 60)
    print("ACTIVE SESSIONS")
    print("=" * 60)
    print()

    if not session_store._sessions:
        print("No active sessions found.")
        print()
        return

    for session_id, session_data in session_store._sessions.items():
        print(f"Session ID: {session_id}")
        print(f"Created at: {session_data['created_at']}")
        print(f"User data:")
        user = session_data['user']
        for key, value in user.items():
            print(f"  {key}: {value}")
        print()


def view_oauth_states():
    """Display pending OAuth states"""
    print("=" * 60)
    print("PENDING OAUTH STATES")
    print("=" * 60)
    print()

    if not session_store._states:
        print("No pending OAuth states.")
        print()
        return

    now = datetime.utcnow()
    for state, created_at in session_store._states.items():
        age = (now - created_at).total_seconds()
        print(f"State: {state}")
        print(f"Created: {created_at}")
        print(f"Age: {age:.1f} seconds")
        print(f"Expires in: {300 - age:.1f} seconds")
        print()


def decode_jwt_token(token_string: str):
    """Decode and display JWT token contents"""
    print("=" * 60)
    print("JWT TOKEN DECODER")
    print("=" * 60)
    print()

    try:
        # Load Auth0 config
        config = Auth0Config.from_env()
        token_manager = TokenManager(config)

        # Verify and decode token
        payload = token_manager.verify_token(token_string)

        if payload:
            print("✅ Token is valid!")
            print()
            print("Token payload:")
            for key, value in payload.items():
                print(f"  {key}: {value}")
            print()
        else:
            print("❌ Token is invalid or expired")
            print()
    except Exception as e:
        print(f"❌ Error decoding token: {e}")
        print()


def main():
    """Main function"""
    print()
    print("🔐 FluidMCP Auth0 Token Viewer")
    print()

    # Check if Auth0 is configured
    try:
        config = Auth0Config.from_env_or_file()
        if config.domain and config.client_id:
            print(f"Auth0 Domain: {config.domain}")
            print(f"Client ID: {config.client_id}")
            print(f"Callback URL: {config.callback_url}")
            print()
    except Exception as e:
        print(f"⚠️  Auth0 not configured: {e}")
        print()

    # View sessions
    view_sessions()

    # View OAuth states
    view_oauth_states()

    # Decode JWT if provided as argument
    if len(sys.argv) > 1:
        token = sys.argv[1]
        decode_jwt_token(token)
    else:
        print("=" * 60)
        print("JWT TOKEN DECODER")
        print("=" * 60)
        print()
        print("To decode a JWT token, run:")
        print(f"  python {sys.argv[0]} YOUR_JWT_TOKEN")
        print()

    print("=" * 60)
    print()

    # Browser instructions
    print("📱 To view tokens in your browser:")
    print()
    print("1. Open your browser DevTools (F12 or Ctrl+Shift+I)")
    print("2. Go to 'Application' tab (Chrome) or 'Storage' tab (Firefox)")
    print("3. Click 'Local Storage' in the left sidebar")
    print("4. Select your domain")
    print("5. Look for these keys:")
    print("   - access_token: Your JWT access token")
    print("   - session_id: Your session identifier")
    print()
    print("💡 Tip: Copy the access_token value and run:")
    print(f"   python {sys.argv[0]} YOUR_TOKEN_HERE")
    print()


if __name__ == "__main__":
    main()
