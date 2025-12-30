"""
Authentication middleware for FastAPI.

This module provides middleware for validating JWT tokens on protected routes.
"""

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from .token_manager import TokenManager
from .config import Auth0Config

security = HTTPBearer(auto_error=False)


class AuthMiddleware:
    """Authentication middleware for FastAPI"""

    def __init__(self, config: Auth0Config):
        self.token_manager = TokenManager(config)

    async def __call__(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials] = None):
        """Validate JWT token from Authorization header"""
        if not credentials:
            raise HTTPException(status_code=401, detail="Authentication required")

        # Verify token
        payload = self.token_manager.verify_token(credentials.credentials)

        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        # Store user data in request state
        request.state.user = payload

        return payload


def create_auth_dependency(config: Auth0Config):
    """Create authentication dependency for route protection"""
    middleware = AuthMiddleware(config)

    async def auth_dependency(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
        return await middleware(request, credentials)

    return auth_dependency
