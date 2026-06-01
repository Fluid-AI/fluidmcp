"""
Authentication module for FluidMCP.

This module provides OAuth0 (Auth0) authentication with JWT validation,
dynamic URL detection for cloud environments, and FastAPI integration.
"""

from .config import Auth0Config
from .oauth_client import Auth0Client
from .jwt_validator import validate_oauth_jwt, JWKSCache
from .dependencies import get_current_user, get_optional_user
from .routes import auth_router, init_auth_routes
from .url_utils import (
    get_base_url,
    get_callback_url,
    get_cors_origins,
    get_environment_info,
    print_auth_urls
)

# Import verify_token from parent auth.py for backwards compatibility
#
# SECURITY: No fallback - fail closed if import fails
#
# Import resolution: When server.py does `from .auth import verify_token`,
# Python resolves .auth to this package (__init__.py), not auth.py module.
# We re-export verify_token from the auth.py module here.
#
# The verify_token function enforces secure-mode bearer token authentication
# for protected endpoints like /metrics. If this import fails, the server
# will fail to start rather than silently bypass authentication.
#
# DO NOT add a fallback stub here - that would create a security vulnerability
# by allowing protected endpoints to be accessed without authentication.
from ..auth import verify_token

__all__ = [
    # Configuration
    "Auth0Config",

    # OAuth client
    "Auth0Client",

    # JWT validation
    "validate_oauth_jwt",
    "JWKSCache",

    # FastAPI dependencies
    "get_current_user",
    "get_optional_user",

    # Routes
    "auth_router",
    "init_auth_routes",

    # URL utilities
    "get_base_url",
    "get_callback_url",
    "get_cors_origins",
    "get_environment_info",
    "print_auth_urls",

    # Bearer token auth
    "verify_token",
]
