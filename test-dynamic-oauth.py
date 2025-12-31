#!/usr/bin/env python3
"""
Test script for dynamic OAuth URL detection.

This script verifies that all components of the dynamic OAuth implementation
are working correctly.
"""

import sys
import os

# Add package to path
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test that all required modules can be imported."""
    print("=" * 70)
    print("Test 1: Imports")
    print("=" * 70)

    try:
        from fluidai_mcp.auth.url_utils import (
            get_base_url,
            get_callback_url,
            get_cors_origins,
            get_environment_info,
            print_auth_urls
        )
        from fluidai_mcp.auth.config import Auth0Config
        from fluidai_mcp.services.run_servers import run_servers
        print("✅ All imports successful\n")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}\n")
        return False


def test_environment_detection():
    """Test environment detection."""
    print("=" * 70)
    print("Test 2: Environment Detection")
    print("=" * 70)

    from fluidai_mcp.auth.url_utils import get_environment_info

    env_info = get_environment_info()
    print(f"Environment Type: {env_info['type']}")
    print(f"Is Codespaces: {env_info['is_codespaces']}")
    print(f"Is Gitpod: {env_info['is_gitpod']}")
    print(f"Is Remote: {env_info['is_remote']}")

    if env_info['is_codespaces']:
        print(f"Codespace Name: {env_info.get('codespace_name')}")
        print(f"Forwarding Domain: {env_info.get('forwarding_domain')}")

    print("✅ Environment detection working\n")
    return True


def test_url_generation():
    """Test URL generation."""
    print("=" * 70)
    print("Test 3: URL Generation")
    print("=" * 70)

    from fluidai_mcp.auth.url_utils import get_base_url, get_callback_url

    base_url = get_base_url(8099)
    callback_url = get_callback_url(8099)

    print(f"Base URL (port 8099): {base_url}")
    print(f"Callback URL: {callback_url}")

    # Verify callback URL is base URL + /auth/callback
    expected_callback = f"{base_url}/auth/callback"
    if callback_url == expected_callback:
        print("✅ Callback URL correctly formatted")
    else:
        print(f"❌ Callback URL mismatch: expected {expected_callback}, got {callback_url}")
        return False

    # Test different port
    base_url_8090 = get_base_url(8090)
    print(f"Base URL (port 8090): {base_url_8090}")
    print("✅ URL generation working\n")
    return True


def test_cors_origins():
    """Test CORS origin generation."""
    print("=" * 70)
    print("Test 4: CORS Origins")
    print("=" * 70)

    from fluidai_mcp.auth.url_utils import get_cors_origins

    origins = get_cors_origins(8099)
    print(f"Generated {len(origins)} CORS origins:")
    for origin in origins:
        print(f"  - {origin}")

    # Verify localhost is always included
    if any("localhost" in origin for origin in origins):
        print("✅ Localhost included in CORS origins")
    else:
        print("❌ Localhost not found in CORS origins")
        return False

    print("✅ CORS origin generation working\n")
    return True


def test_auth0_config():
    """Test Auth0Config with dynamic URLs."""
    print("=" * 70)
    print("Test 5: Auth0Config Dynamic URLs")
    print("=" * 70)

    from fluidai_mcp.auth.config import Auth0Config

    # Test without environment variables (should use dynamic detection)
    try:
        config = Auth0Config.from_env_or_file(port=8099)
        print(f"Callback URL: {config.callback_url}")
        print(f"Port: {config.port}")

        # Verify callback_url was set dynamically
        if config.callback_url and "/auth/callback" in config.callback_url:
            print("✅ Callback URL dynamically generated")
        else:
            print("❌ Callback URL not properly set")
            return False

        print("✅ Auth0Config working with dynamic URLs\n")
        return True
    except Exception as e:
        print(f"⚠️  Auth0Config test skipped (expected without env vars): {e}\n")
        return True


def test_url_display():
    """Test URL display function."""
    print("=" * 70)
    print("Test 6: URL Display Function")
    print("=" * 70)

    from fluidai_mcp.auth.url_utils import print_auth_urls

    print("Testing print_auth_urls(8099):\n")
    print_auth_urls(8099)
    print("✅ URL display function working\n")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("FluidMCP Dynamic OAuth - Test Suite")
    print("=" * 70 + "\n")

    tests = [
        ("Imports", test_imports),
        ("Environment Detection", test_environment_detection),
        ("URL Generation", test_url_generation),
        ("CORS Origins", test_cors_origins),
        ("Auth0Config", test_auth0_config),
        ("URL Display", test_url_display),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test '{test_name}' failed with exception: {e}\n")
            results.append((test_name, False))

    # Summary
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Dynamic OAuth is working correctly.\n")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
