"""
Bearer token authentication utilities (legacy/simple auth mode).

Used by endpoints that need simple bearer token validation
independent of the OAuth2/Auth0 flow.
"""

import os
import secrets
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)


def _validate_bearer_token(credentials: HTTPAuthorizationCredentials, bearer_token: str) -> None:
    if not bearer_token:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: FMCP_BEARER_TOKEN not set in secure mode"
        )

    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing authorization token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not secrets.compare_digest(credentials.credentials, bearer_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing authorization token",
            headers={"WWW-Authenticate": "Bearer"}
        )


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> None:
    """Validate bearer token if secure mode is enabled."""
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"

    if not secure_mode:
        return None

    _validate_bearer_token(credentials, bearer_token)
    return None


def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[str]:
    """Validate bearer token and return the token value."""
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"

    if not secure_mode:
        return None

    _validate_bearer_token(credentials, bearer_token)
    return credentials.credentials
