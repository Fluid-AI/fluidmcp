"""
Auth module for FluidMCP.

This module provides Auth0 OAuth authentication with custom JWT tokens.
All authentication-related code is organized in this dedicated folder.

Features:
- Dynamic URL detection (Codespaces, Gitpod, custom domains)
- OAuth authentication via Auth0
- JWT token management
- Session management
"""

from .config import Auth0Config
from .routes import router as auth_router, init_auth_routes
from .middleware import create_auth_dependency
from .session_store import session_store
from .url_utils import (
    get_base_url,
    get_callback_url,
    get_cors_origins,
    get_environment_info,
    print_auth_urls
)

__all__ = [
    'Auth0Config',
    'auth_router',
    'init_auth_routes',
    'create_auth_dependency',
    'session_store',
    'get_base_url',
    'get_callback_url',
    'get_cors_origins',
    'get_environment_info',
    'print_auth_urls',
]
