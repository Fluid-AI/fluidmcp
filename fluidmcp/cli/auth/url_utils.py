"""
URL utility functions for detecting and constructing URLs in different environments.

This module handles URL generation for local, Codespaces, and remote environments.
"""

import os


def get_base_url(port: int = 8099) -> str:
    """
    Detect the base URL based on the environment.

    Supports:
    - GitHub Codespaces (auto-detected)
    - Custom base URL (FMCP_BASE_URL env var)
    - Local development (fallback to localhost)

    Args:
        port: Port number (default: 8099)

    Returns:
        Base URL (e.g., "https://codespace-name-8099.app.github.dev" or "http://localhost:8099")
    """
    # 1. Check for custom base URL (highest priority)
    custom_base = os.getenv("FMCP_BASE_URL")
    if custom_base:
        # Remove trailing slash if present
        return custom_base.rstrip('/')

    # 2. Check for GitHub Codespaces
    if os.getenv("CODESPACES") == "true":
        codespace_name = os.getenv("CODESPACE_NAME")
        forwarding_domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")

        if codespace_name and forwarding_domain:
            return f"https://{codespace_name}-{port}.{forwarding_domain}"

    # 3. Check for Gitpod
    if os.getenv("GITPOD_WORKSPACE_ID"):
        workspace_url = os.getenv("GITPOD_WORKSPACE_URL")
        if workspace_url:
            # Gitpod format: https://8099-workspace-url
            workspace_url = workspace_url.replace("https://", "")
            return f"https://{port}-{workspace_url}"

    # 4. Check for other cloud IDEs (generic)
    # VSCode Remote, Cloud9, etc. typically use localhost

    # 5. Fallback to localhost
    return f"http://localhost:{port}"


def get_callback_url(port: int = 8099) -> str:
    """
    Get the OAuth callback URL for the current environment.

    Args:
        port: Port number (default: 8099)

    Returns:
        Full callback URL (e.g., "https://codespace-8099.app.github.dev/auth/callback")
    """
    base_url = get_base_url(port)
    return f"{base_url}/auth/callback"


def get_logout_url(port: int = 8099) -> str:
    """
    Get the logout URL for the current environment.

    Args:
        port: Port number (default: 8099)

    Returns:
        Full logout URL
    """
    base_url = get_base_url(port)
    return f"{base_url}/"


def get_cors_origins(port: int = 8099) -> list[str]:
    """
    Get appropriate CORS origins based on environment.

    Args:
        port: Port number (default: 8099)

    Returns:
        List of allowed origins
    """
    origins = []

    # 1. Add custom CORS origins from env var
    custom_origins = os.getenv("FMCP_ALLOWED_ORIGINS")
    if custom_origins:
        origins.extend([origin.strip() for origin in custom_origins.split(",")])

    # 2. Add detected base URL
    base_url = get_base_url(port)
    if base_url not in origins:
        origins.append(base_url)

    # 3. Always add localhost for local development
    if not any("localhost" in origin for origin in origins):
        origins.extend([
            f"http://localhost:{port}",
            f"http://127.0.0.1:{port}",
        ])

    # 4. In Codespaces, add wildcard for port forwarding
    if os.getenv("CODESPACES") == "true":
        codespace_name = os.getenv("CODESPACE_NAME")
        forwarding_domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")

        if codespace_name and forwarding_domain:
            origins.append(f"https://{codespace_name}-*.{forwarding_domain}")

    return origins


def get_environment_info() -> dict:
    """
    Get information about the current environment.

    Returns:
        Dictionary with environment details
    """
    env_info = {
        "type": "local",
        "is_codespaces": False,
        "is_gitpod": False,
        "is_remote": False,
    }

    if os.getenv("CODESPACES") == "true":
        env_info["type"] = "codespaces"
        env_info["is_codespaces"] = True
        env_info["is_remote"] = True
        env_info["codespace_name"] = os.getenv("CODESPACE_NAME")
        env_info["forwarding_domain"] = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    elif os.getenv("GITPOD_WORKSPACE_ID"):
        env_info["type"] = "gitpod"
        env_info["is_gitpod"] = True
        env_info["is_remote"] = True
        env_info["workspace_id"] = os.getenv("GITPOD_WORKSPACE_ID")
    elif os.getenv("REMOTE_CONTAINERS") or os.getenv("VSCODE_REMOTE_CONTAINERS_SESSION"):
        env_info["type"] = "remote_container"
        env_info["is_remote"] = True

    return env_info


def print_auth_urls(port: int = 8099) -> None:
    """
    Print authentication URLs for the current environment.

    Args:
        port: Port number (default: 8099)
    """
    base_url = get_base_url(port)
    callback_url = get_callback_url(port)
    env_info = get_environment_info()

    print("\n" + "=" * 70)
    print("🔐 Auth0 OAuth Configuration")
    print("=" * 70)

    if env_info["is_remote"]:
        print(f"📍 Environment: {env_info['type'].upper()}")
        print(f"🌐 Detected Remote Environment")
    else:
        print(f"📍 Environment: Local Development")

    print(f"\n🔗 URLs for your application:")
    print(f"   Base URL:     {base_url}")
    print(f"   Login URL:    {base_url}/")
    print(f"   Swagger UI:   {base_url}/docs")
    print(f"   Callback URL: {callback_url}")

    print(f"\n⚙️  Auth0 Dashboard Configuration:")
    print(f"   Add these URLs to your Auth0 application settings:")
    print(f"\n   Allowed Callback URLs:")
    print(f"   {callback_url}")
    print(f"\n   Allowed Logout URLs:")
    print(f"   {base_url}/")
    print(f"\n   Allowed Web Origins:")
    print(f"   {base_url}")

    if env_info["is_codespaces"]:
        print(f"\n💡 Codespaces Tip:")
        print(f"   Your Codespace URL will change if you restart the Codespace.")
        print(f"   Update Auth0 settings with the new URL if that happens.")
        print(f"   Or set FMCP_BASE_URL env var to a stable URL.")

    print("=" * 70 + "\n")
