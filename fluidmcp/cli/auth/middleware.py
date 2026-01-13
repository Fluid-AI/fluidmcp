"""
FastAPI authentication middleware for FluidMCP OAuth.

This module provides the enhanced get_token() dependency that integrates
JWT validation with the existing bearer token authentication.
"""

import os
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger

from .jwt_validator import (
    JWTValidator,
    JWTValidationError,
    JWTExpiredError,
    JWTAudienceError,
    JWTIssuerError,
    JWTScopeError,
    JWTSignatureError
)


# Global JWT validator instance (set during app initialization)
_jwt_validator: Optional[JWTValidator] = None

# FastAPI security scheme
security = HTTPBearer(auto_error=False)


def set_jwt_validator(validator: Optional[JWTValidator]) -> None:
    """
    Set the global JWT validator instance.

    Called during application startup to enable OAuth JWT validation.

    Args:
        validator: Initialized JWTValidator instance, or None to disable
    """
    global _jwt_validator
    _jwt_validator = validator

    if validator:
        logger.info("JWT validator enabled for OAuth authentication")
    else:
        logger.debug("JWT validator not configured")


def get_jwt_validator() -> Optional[JWTValidator]:
    """
    Get the global JWT validator instance.

    Returns:
        JWTValidator instance if OAuth is configured, None otherwise
    """
    return _jwt_validator


async def get_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency for authentication with OAuth JWT support.

    Authentication priority:
    1. OAuth JWT validation (if JWT validator configured)
    2. Bearer token validation (if FMCP_SECURE_MODE enabled)
    3. No authentication (if neither configured)

    Args:
        request: FastAPI request object
        credentials: HTTP Authorization credentials

    Returns:
        Decoded JWT claims (OAuth) or minimal claims dict (bearer token),
        or None if no authentication required

    Raises:
        HTTPException: 401 if authentication fails
    """
    # No credentials provided
    if not credentials:
        # Check if any auth is required
        if _jwt_validator is not None:
            raise HTTPException(
                status_code=401,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"}
            )

        secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"
        if secure_mode:
            raise HTTPException(
                status_code=401,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # No auth required
        return None

    # Validate credentials scheme
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication scheme. Expected 'Bearer'",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials

    # Priority 1: Try OAuth JWT validation (if configured)
    if _jwt_validator is not None:
        try:
            claims = await _jwt_validator.validate_jwt(token)
            logger.debug(f"OAuth JWT validated for subject: {claims.get('sub', 'unknown')}")
            return claims

        except JWTExpiredError as e:
            # Token expired - clear error message
            error_description = "Token expired"
            logger.warning(f"JWT validation failed: {error_description}")

            if _jwt_validator.config.fallback_to_bearer:
                logger.debug("Attempting bearer token fallback")
                # Fall through to bearer token validation
            else:
                raise HTTPException(
                    status_code=401,
                    detail=error_description,
                    headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{error_description}"'}
                )

        except JWTAudienceError as e:
            # Wrong audience - security error
            error_description = f"Invalid audience: {str(e)}"
            logger.warning(f"JWT validation failed: {error_description}")

            if _jwt_validator.config.fallback_to_bearer:
                logger.debug("Attempting bearer token fallback")
                # Fall through to bearer token validation
            else:
                raise HTTPException(
                    status_code=401,
                    detail=error_description,
                    headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="Invalid audience"'}
                )

        except JWTIssuerError as e:
            # Wrong issuer - security error
            error_description = f"Invalid issuer: {str(e)}"
            logger.warning(f"JWT validation failed: {error_description}")

            if _jwt_validator.config.fallback_to_bearer:
                logger.debug("Attempting bearer token fallback")
                # Fall through to bearer token validation
            else:
                raise HTTPException(
                    status_code=401,
                    detail=error_description,
                    headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="Invalid issuer"'}
                )

        except JWTScopeError as e:
            # Missing required scopes
            error_description = f"Insufficient scope: {str(e)}"
            logger.warning(f"JWT validation failed: {error_description}")

            if _jwt_validator.config.fallback_to_bearer:
                logger.debug("Attempting bearer token fallback")
                # Fall through to bearer token validation
            else:
                raise HTTPException(
                    status_code=403,  # 403 for insufficient scope
                    detail=error_description,
                    headers={"WWW-Authenticate": f'Bearer error="insufficient_scope", error_description="{str(e)}"'}
                )

        except JWTSignatureError as e:
            # Signature verification failed
            error_description = f"Signature verification failed: {str(e)}"
            logger.warning(f"JWT validation failed: {error_description}")

            if _jwt_validator.config.fallback_to_bearer:
                logger.debug("Attempting bearer token fallback")
                # Fall through to bearer token validation
            else:
                raise HTTPException(
                    status_code=401,
                    detail=error_description,
                    headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="Invalid signature"'}
                )

        except JWTValidationError as e:
            # Generic JWT validation error
            error_description = str(e)
            logger.warning(f"JWT validation failed: {error_description}")

            if _jwt_validator.config.fallback_to_bearer:
                logger.debug("Attempting bearer token fallback")
                # Fall through to bearer token validation
            else:
                raise HTTPException(
                    status_code=401,
                    detail=error_description,
                    headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{error_description}"'}
                )

        except Exception as e:
            # Unexpected error
            logger.exception(f"Unexpected error during JWT validation")

            if _jwt_validator.config.fallback_to_bearer:
                logger.debug("Attempting bearer token fallback after unexpected error")
                # Fall through to bearer token validation
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Internal authentication error"
                )

    # Priority 2: Bearer token validation (fallback or primary if no OAuth)
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"
    if secure_mode:
        bearer_token = os.environ.get("FMCP_BEARER_TOKEN")

        if not bearer_token:
            logger.error("FMCP_SECURE_MODE enabled but FMCP_BEARER_TOKEN not set")
            raise HTTPException(
                status_code=500,
                detail="Server authentication misconfigured"
            )

        if token != bearer_token:
            logger.warning("Bearer token validation failed")
            raise HTTPException(
                status_code=401,
                detail="Invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"}
            )

        logger.debug("Bearer token validated successfully")
        return {"auth_type": "bearer", "token": "***"}  # Minimal claims for bearer

    # No authentication configured
    logger.trace("No authentication required for this request")
    return None


def get_authentication_status() -> Dict[str, Any]:
    """
    Get current authentication configuration status.

    Returns:
        Dictionary with authentication status information
    """
    status = {
        "oauth_enabled": _jwt_validator is not None,
        "bearer_token_enabled": os.environ.get("FMCP_SECURE_MODE") == "true",
    }

    if _jwt_validator:
        status["oauth_config"] = {
            "provider": _jwt_validator.config.provider,
            "issuer": _jwt_validator.config.jwt_validation.issuer,
            "audience": _jwt_validator.config.jwt_validation.audience,
            "required_scopes": _jwt_validator.config.jwt_validation.required_scopes,
            "fallback_to_bearer": _jwt_validator.config.fallback_to_bearer,
        }

        if _jwt_validator._initialized:
            status["oauth_stats"] = _jwt_validator.get_stats()

    return status
