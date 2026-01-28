"""
Authentication utilities for FluidMCP.

This module provides shared authentication functions used across the FluidMCP application.
All authentication logic should use these functions to ensure consistency and security.
"""

import os
import secrets
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Initialize HTTPBearer security scheme
security = HTTPBearer(auto_error=False)


def _validate_bearer_token(credentials: HTTPAuthorizationCredentials, bearer_token: str) -> None:
    """
    Internal function to validate bearer token credentials.

    Security features:
    - Constant-time token comparison (prevents timing attacks)
    - Validates bearer token is configured before comparison
    - Returns 500 error for server misconfiguration
    - Returns 401 with WWW-Authenticate header for invalid tokens

    Args:
        credentials: HTTP Authorization header with bearer token
        bearer_token: Expected bearer token from environment

    Raises:
        HTTPException:
            - 401 if token is invalid or missing
            - 500 if bearer token not configured
    """
    # Validate bearer token is configured when secure mode is enabled
    if not bearer_token:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: FMCP_BEARER_TOKEN not set in secure mode"
        )

    # Validate credentials exist and scheme is correct
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing authorization token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(credentials.credentials, bearer_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing authorization token",
            headers={"WWW-Authenticate": "Bearer"}
        )


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> None:
    """
    Validate bearer token if secure mode is enabled.

    This dependency is used to protect endpoints when FMCP_SECURE_MODE=true.
    If secure mode is disabled, the endpoint is publicly accessible.

    Args:
        credentials: HTTP Authorization header with bearer token

    Raises:
        HTTPException:
            - 401 if token is invalid or missing in secure mode
            - 500 if secure mode enabled but FMCP_BEARER_TOKEN not configured

    Returns:
        None if authentication succeeds or secure mode is disabled

    Examples:
        >>> from fastapi import FastAPI, Depends
        >>> from fluidmcp.cli.auth import verify_token
        >>>
        >>> app = FastAPI()
        >>>
        >>> @app.get("/protected", dependencies=[Depends(verify_token)])
        >>> async def protected_endpoint():
        ...     return {"message": "Access granted"}
    """
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"

    if not secure_mode:
        # Public access when secure mode is disabled
        return None

    _validate_bearer_token(credentials, bearer_token)
    return None


def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[str]:
    """
    Validate bearer token and return the token value.

    This function is similar to verify_token() but returns the token value
    instead of None. Used by endpoints that need the token value for further processing.

    Args:
        credentials: HTTP Authorization header with bearer token

    Raises:
        HTTPException:
            - 401 if token is invalid or missing in secure mode
            - 500 if secure mode enabled but FMCP_BEARER_TOKEN not configured

    Returns:
        Token value (str) if authentication succeeds in secure mode, None if secure mode is disabled

    Examples:
        >>> from fastapi import FastAPI, Depends
        >>> from fluidmcp.cli.auth import get_token
        >>>
        >>> app = FastAPI()
        >>>
        >>> @app.get("/user-info")
        >>> async def user_info(token: str = Depends(get_token)):
        ...     return {"token": token}
    """
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"

    if not secure_mode:
        return None

    _validate_bearer_token(credentials, bearer_token)
    return credentials.credentials
