"""
Bearer token authentication for FluidMCP.

This module provides the bearer token verifier used to protect FastAPI endpoints
when FMCP_SECURE_MODE=true. It is defined inside the auth/ package so that
`from fluidmcp.cli.auth import verify_token` resolves unambiguously to this
module, without relying on the auth.py module which is shadowed by the package.
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
    """Validate bearer token if FMCP_SECURE_MODE=true, pass through otherwise."""
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"
    if not secure_mode:
        return None
    _validate_bearer_token(credentials, bearer_token)
    return None


def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[str]:
    """Validate bearer token and return its value; returns None when secure mode is off."""
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"
    if not secure_mode:
        return None
    _validate_bearer_token(credentials, bearer_token)
    return credentials.credentials
