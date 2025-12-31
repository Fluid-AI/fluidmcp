#!/usr/bin/env python3
"""
Quick script to print Auth0 configuration URLs for your environment.

Usage:
    python print-auth0-urls.py [port]

Example:
    python print-auth0-urls.py 8099
"""

import sys
import os

# Add the package to path
sys.path.insert(0, os.path.dirname(__file__))

from fluidai_mcp.auth.url_utils import print_auth_urls

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099

    print(f"FluidMCP Auth0 URL Configuration Tool")
    print(f"{'='*70}\n")

    print_auth_urls(port)

    print("\n📋 Next Steps:")
    print("   1. Copy the URLs above")
    print("   2. Go to https://manage.auth0.com")
    print("   3. Select your application")
    print("   4. Paste the URLs into Application URIs settings")
    print("   5. Set your environment variables (see AUTH0_SETUP.md)")
    print("   6. Run: fluidmcp run all --start-server --auth0")
    print()

if __name__ == "__main__":
    main()
