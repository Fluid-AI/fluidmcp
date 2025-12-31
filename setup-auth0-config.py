#!/usr/bin/env python3
"""
Interactive Auth0 Configuration Setup

This script helps you create an auth0-config.json file with your Auth0 credentials.
Run this once, and you won't need to set environment variables every time.
"""

import json
import os
import sys
import secrets
from pathlib import Path


def print_header():
    """Print welcome header"""
    print()
    print("=" * 60)
    print("🔐 Auth0 Configuration Setup")
    print("=" * 60)
    print()
    print("This script will help you create an auth0-config.json file")
    print("with your Auth0 credentials. Run this once, and FluidMCP")
    print("will automatically load your configuration on startup.")
    print()


def detect_codespaces_url():
    """Detect if running in GitHub Codespaces and return URL"""
    codespace_name = os.getenv('CODESPACE_NAME')
    forwarding_domain = os.getenv('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN')

    if codespace_name and forwarding_domain:
        return f"https://{codespace_name}-8099.{forwarding_domain}"
    return None


def get_input(prompt, default=None, required=True):
    """Get user input with optional default"""
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "

    while True:
        value = input(full_prompt).strip()

        if value:
            return value
        elif default:
            return default
        elif not required:
            return None
        else:
            print("  ❌ This field is required. Please enter a value.")


def main():
    """Main setup flow"""
    print_header()

    # Check if config already exists
    config_path = Path('auth0-config.json')
    if config_path.exists():
        print(f"⚠️  Warning: {config_path} already exists!")
        response = input("Do you want to overwrite it? (y/n): ").strip().lower()
        if response != 'y':
            print("Setup cancelled.")
            return

    print("Let's set up your Auth0 configuration.")
    print()

    # Get Auth0 credentials
    print("📋 Step 1: Auth0 Application Credentials")
    print("-" * 60)
    print("Get these from: https://manage.auth0.com")
    print("Navigate to: Applications → Your App → Settings")
    print()

    domain = get_input("Auth0 Domain (e.g., dev-xxxxx.us.auth0.com)")
    client_id = get_input("Auth0 Client ID")
    client_secret = get_input("Auth0 Client Secret")

    print()
    print("✅ Auth0 credentials configured")
    print()

    # Get callback URL
    print("📋 Step 2: Callback URL Configuration")
    print("-" * 60)

    # Try to detect Codespaces
    codespaces_url = detect_codespaces_url()
    if codespaces_url:
        print(f"✓ Detected GitHub Codespaces environment")
        print(f"  Your URL: {codespaces_url}")
        print()
        callback_url = get_input(
            "Callback URL",
            default=f"{codespaces_url}/auth/callback"
        )
    else:
        print("Enter your callback URL.")
        print("For local development: http://localhost:8099/auth/callback")
        print("For Codespaces: https://your-codespace-url.app.github.dev/auth/callback")
        print()
        callback_url = get_input(
            "Callback URL",
            default="http://localhost:8099/auth/callback"
        )

    print()
    print("✅ Callback URL configured")
    print()

    # JWT Secret
    print("📋 Step 3: JWT Secret Generation")
    print("-" * 60)
    print("Generating secure JWT secret...")

    jwt_secret = secrets.token_urlsafe(32)
    print(f"✓ Generated JWT secret: {jwt_secret[:20]}...")

    print()
    print("✅ JWT secret generated")
    print()

    # Optional settings
    print("📋 Step 4: Optional Settings")
    print("-" * 60)

    audience = get_input("Auth0 Audience (optional, press Enter to skip)", required=False)

    jwt_expiration = get_input(
        "JWT token expiration (minutes)",
        default="30"
    )

    # Create config dictionary
    config = {
        "domain": domain,
        "client_id": client_id,
        "client_secret": client_secret,
        "callback_url": callback_url,
        "jwt_secret": jwt_secret,
        "jwt_expiration_minutes": int(jwt_expiration)
    }

    if audience:
        config["audience"] = audience

    # Save to file
    print()
    print("📝 Saving configuration...")
    print("-" * 60)

    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        # Set restrictive permissions (Unix-like systems only)
        try:
            os.chmod(config_path, 0o600)
            print(f"✓ Set file permissions to 600 (owner read/write only)")
        except:
            print(f"⚠️  Could not set file permissions (Windows or permission denied)")

        print(f"✓ Configuration saved to: {config_path}")

    except Exception as e:
        print(f"❌ Error saving configuration: {e}")
        return

    # Update .gitignore
    gitignore_path = Path('.gitignore')
    if gitignore_path.exists():
        with open(gitignore_path, 'r') as f:
            gitignore_content = f.read()

        if 'auth0-config.json' not in gitignore_content:
            with open(gitignore_path, 'a') as f:
                f.write('\n# Auth0 configuration (contains secrets)\n')
                f.write('auth0-config.json\n')
                f.write('auth0-config-*.json\n')
            print(f"✓ Added auth0-config.json to .gitignore")
        else:
            print(f"✓ auth0-config.json already in .gitignore")
    else:
        print("⚠️  No .gitignore file found")

    # Show Auth0 Dashboard URLs
    print()
    print("=" * 60)
    print("🎯 Important: Update Auth0 Dashboard")
    print("=" * 60)
    print()
    print("You MUST configure these URLs in your Auth0 Dashboard:")
    print("https://manage.auth0.com → Applications → Your App → Settings")
    print()
    print("Allowed Callback URLs:")
    print(f"  {callback_url}")
    print()
    print("Allowed Logout URLs:")
    base_url = callback_url.rsplit('/auth/callback', 1)[0]
    print(f"  {base_url}/")
    print()
    print("Allowed Web Origins:")
    print(f"  {base_url}")
    print()
    print("Click 'Save Changes' and wait 30-60 seconds for propagation.")
    print()

    # Show next steps
    print("=" * 60)
    print("✅ Setup Complete!")
    print("=" * 60)
    print()
    print("Your Auth0 configuration has been saved to auth0-config.json")
    print()
    print("Next steps:")
    print("  1. Update Auth0 Dashboard with the URLs shown above")
    print("  2. Start FluidMCP with Auth0 enabled:")
    print()
    print("     fluidmcp run all --start-server --auth0")
    print()
    print("FluidMCP will automatically load your configuration from auth0-config.json")
    print()
    print("🎉 You're all set! No need to set environment variables anymore.")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        sys.exit(1)
