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

# Bearer token authentication - imported from bearer.py inside this package.
# The auth/ package directory shadows the auth.py module at the same level,
# so `from ..auth import verify_token` would resolve back to this package
# (circular) and never reach auth.py. Defining the verifier in bearer.py and
# re-exporting it here makes the import path unambiguous.
from .bearer import verify_token, get_token

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
    "get_token",
]
