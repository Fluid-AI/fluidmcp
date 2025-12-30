"""
Auth module for FluidMCP.

This module provides Auth0 OAuth authentication with custom JWT tokens.
All authentication-related code is organized in this dedicated folder.
"""

from .config import Auth0Config
from .routes import router as auth_router, init_auth_routes
from .middleware import create_auth_dependency
from .session_store import session_store

__all__ = [
    'Auth0Config',
    'auth_router',
    'init_auth_routes',
    'create_auth_dependency',
    'session_store'
]
