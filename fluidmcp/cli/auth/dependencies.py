"""
FastAPI authentication dependencies for OAuth and bearer token auth.

This module provides unified authentication dependencies that support
both OAuth JWT tokens and simple bearer token authentication.
"""

import os
from typing import Dict, Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger


# Security scheme for HTTP Bearer authentication
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Optional[str]]:
    """
    Extract user from OAuth JWT or bearer token.

    This dependency checks for both OAuth and bearer token authentication
    modes and validates tokens accordingly. Supports three token sources:
    1. Authorization header (Bearer token) - for API clients
    2. httpOnly cookie (fmcp_auth_token) - for browser-based OAuth
    3. Anonymous mode (no token)

    Args:
        request: FastAPI request object (to access cookies)
        credentials: HTTP Authorization credentials (Bearer token)

    Returns:
        User context dictionary with:
        - user_id: Unique user identifier
        - email: User's email address (None for bearer tokens)
        - name: User's display name
        - auth_method: 'oauth', 'bearer', or 'none'

    Raises:
        HTTPException: 401 if authentication is required but fails
    """
    auth0_mode = os.getenv("FMCP_AUTH0_MODE") == "true"
    secure_mode = os.getenv("FMCP_SECURE_MODE") == "true"

    # Anonymous mode - no authentication required
    if not auth0_mode and not secure_mode:
        return {
            "user_id": "anonymous",
            "email": None,
            "name": "Anonymous",
            "auth_method": "none"
        }

    # Try to get token from multiple sources
    token = None

    # 1. Authorization header (highest priority - for API clients)
    if credentials:
        token = credentials.credentials

    # 2. httpOnly cookie (for browser-based OAuth)
    elif "fmcp_auth_token" in request.cookies:
        token = request.cookies["fmcp_auth_token"]

    # Authentication required but no token found
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide a valid token."
        )

    # Try OAuth JWT validation first (if enabled)
    if auth0_mode:
        try:
            from .jwt_validator import validate_oauth_jwt
            user = await validate_oauth_jwt(token)
            logger.debug(f"OAuth authentication successful for user: {user['user_id']}")
            return user
        except Exception as e:
            logger.warning(f"OAuth JWT validation failed: {e}")
            # Fall through to try bearer token if secure mode also enabled
            if not secure_mode:
                raise HTTPException(
                    status_code=401,
                    detail=f"Invalid or expired OAuth token: {str(e)}"
                )

    # Try bearer token validation (if enabled)
    if secure_mode:
        bearer_token = os.getenv("FMCP_BEARER_TOKEN")
        if not bearer_token:
            raise HTTPException(
                status_code=500,
                detail="Bearer token authentication is enabled but FMCP_BEARER_TOKEN is not set"
            )

        if token == bearer_token:
            logger.debug(f"Bearer token authentication successful")
            return {
                "user_id": f"bearer_{token[:8]}",
                "email": None,
                "name": f"Bearer User {token[:8]}",
                "auth_method": "bearer"
            }

    # No valid authentication method succeeded
    raise HTTPException(
        status_code=401,
        detail="Invalid or expired token"
    )


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Optional[str]]]:
    """
    Optional authentication - returns None if no valid credentials.

    Use this dependency for endpoints that support both authenticated
    and anonymous access.

    Args:
        request: FastAPI request object (to access cookies)
        credentials: HTTP Authorization credentials (Bearer token)

    Returns:
        User context dictionary or None if no valid credentials
    """
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None
