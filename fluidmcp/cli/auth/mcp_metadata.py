"""
MCP OAuth metadata endpoint for FluidMCP.

This module provides the MCP resource metadata endpoint that exposes
OAuth/OIDC configuration to MCP clients per the MCP specification.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

from .jwt_validator import JWTValidator
from .oidc_discovery import OIDCConfiguration


def get_mcp_metadata_endpoint(jwt_validator: Optional[JWTValidator]) -> APIRouter:
    """
    Create MCP OAuth metadata endpoint router.

    Returns FastAPI router with the /.well-known/mcp-oauth-config endpoint
    that exposes OAuth configuration for MCP clients.

    Per MCP specification, this endpoint should return:
    - authorization_endpoint: Where to redirect users for auth
    - token_endpoint: Where to exchange codes for tokens
    - supported_grant_types: OAuth grant types supported
    - pkce_required: Whether PKCE is required
    - scopes_supported: Available OAuth scopes

    Args:
        jwt_validator: Initialized JWTValidator instance, or None if OAuth disabled

    Returns:
        FastAPI APIRouter with metadata endpoint

    Example:
        app = FastAPI()
        metadata_router = get_mcp_metadata_endpoint(jwt_validator)
        app.include_router(metadata_router)

        # Endpoint available at: GET /.well-known/mcp-oauth-config
    """
    router = APIRouter()

    @router.get("/.well-known/mcp-oauth-config")
    async def mcp_oauth_metadata() -> JSONResponse:
        """
        MCP OAuth metadata endpoint.

        Returns OAuth/OIDC configuration for MCP clients that need to
        authenticate with this server.

        Returns:
            JSON response with OAuth metadata
        """
        if jwt_validator is None or not jwt_validator._initialized:
            # OAuth not configured
            logger.debug("MCP OAuth metadata requested, but OAuth not configured")
            return JSONResponse(
                status_code=404,
                content={
                    "error": "oauth_not_configured",
                    "error_description": "OAuth authentication is not configured on this server"
                }
            )

        try:
            oidc_config = jwt_validator.oidc_config
            oauth_config = jwt_validator.config

            # Build metadata response per MCP spec
            metadata = {
                "authorization_endpoint": oidc_config.authorization_endpoint,
                "token_endpoint": oidc_config.token_endpoint,
                "issuer": oidc_config.issuer,
                "jwks_uri": oidc_config.jwks_uri,
                "supported_grant_types": _get_supported_grant_types(oidc_config),
                "pkce_required": _is_pkce_required(oidc_config),
                "scopes_supported": _get_scopes_supported(oidc_config, oauth_config),
                "token_endpoint_auth_methods_supported": [
                    "client_secret_post",
                    "client_secret_basic",
                    "none"  # For PKCE public clients
                ]
            }

            # Add optional fields if available
            if oidc_config.userinfo_endpoint:
                metadata["userinfo_endpoint"] = oidc_config.userinfo_endpoint

            if oidc_config.end_session_endpoint:
                metadata["end_session_endpoint"] = oidc_config.end_session_endpoint

            # Add audience requirement
            if oauth_config.jwt_validation.audience:
                metadata["audience"] = oauth_config.jwt_validation.audience

            # Add required scopes
            if oauth_config.jwt_validation.required_scopes:
                metadata["required_scopes"] = oauth_config.jwt_validation.required_scopes

            logger.debug("Returned MCP OAuth metadata")
            return JSONResponse(content=metadata)

        except Exception as e:
            logger.exception("Error generating MCP OAuth metadata")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_error",
                    "error_description": "Failed to generate OAuth metadata"
                }
            )

    return router


def _get_supported_grant_types(oidc_config: OIDCConfiguration) -> list:
    """
    Extract supported grant types from OIDC configuration.

    Args:
        oidc_config: OIDC configuration from discovery

    Returns:
        List of supported grant type strings
    """
    if oidc_config.grant_types_supported:
        return oidc_config.grant_types_supported

    # Default grant types for Keycloak
    return [
        "authorization_code",
        "client_credentials",
        "refresh_token"
    ]


def _is_pkce_required(oidc_config: OIDCConfiguration) -> bool:
    """
    Check if PKCE is supported/required.

    Args:
        oidc_config: OIDC configuration from discovery

    Returns:
        True if PKCE is supported, False otherwise
    """
    if oidc_config.code_challenge_methods_supported:
        # PKCE is supported if S256 method is available
        return "S256" in oidc_config.code_challenge_methods_supported

    # Conservative default: assume PKCE is available in modern Keycloak
    return True


def _get_scopes_supported(
    oidc_config: OIDCConfiguration,
    oauth_config
) -> list:
    """
    Get list of supported OAuth scopes.

    Args:
        oidc_config: OIDC configuration from discovery
        oauth_config: FluidMCP OAuth configuration

    Returns:
        List of supported scope strings
    """
    scopes = set()

    # Add scopes from OIDC discovery
    if oidc_config.scopes_supported:
        scopes.update(oidc_config.scopes_supported)

    # Add required scopes from config
    if oauth_config.jwt_validation.required_scopes:
        scopes.update(oauth_config.jwt_validation.required_scopes)

    # Ensure 'openid' is included (required for OIDC)
    scopes.add("openid")

    return sorted(list(scopes))


def create_auth_status_endpoint(jwt_validator: Optional[JWTValidator]) -> APIRouter:
    """
    Create authentication status endpoint for debugging.

    Provides a /.well-known/auth-status endpoint that shows current
    authentication configuration. Useful for troubleshooting.

    Args:
        jwt_validator: Initialized JWTValidator instance, or None if OAuth disabled

    Returns:
        FastAPI APIRouter with status endpoint
    """
    router = APIRouter()

    @router.get("/.well-known/auth-status")
    async def auth_status() -> JSONResponse:
        """
        Authentication status endpoint.

        Returns current authentication configuration and statistics.
        """
        from .middleware import get_authentication_status

        status = get_authentication_status()

        return JSONResponse(content=status)

    return router
