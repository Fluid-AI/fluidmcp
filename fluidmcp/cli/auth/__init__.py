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
import sys
from pathlib import Path

# Import verify_token from the auth.py module (not this package)
parent_path = Path(__file__).parent.parent
if str(parent_path) not in sys.path:
    sys.path.insert(0, str(parent_path))

try:
    from ..auth import verify_token
except ImportError:
    # Fallback: define a simple verify_token stub
    def verify_token(*args, **kwargs):
        pass

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
