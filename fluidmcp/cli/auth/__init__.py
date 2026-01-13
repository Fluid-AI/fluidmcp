"""
FluidMCP OAuth 2.0 (OIDC) Authentication Module.

This module provides JWT validation for Keycloak OAuth 2.0 authentication
in FluidMCP's FastAPI gateway. FluidMCP acts as a resource server that
validates JWT access tokens issued by Keycloak.

Key Features:
- JWT signature validation using JWKS
- Claims validation (exp, aud, iss, scope)
- Token caching for performance (5-minute default TTL)
- JWKS caching (1-hour default TTL)
- Bearer token fallback for backward compatibility
- MCP metadata endpoint for OAuth configuration

Architecture:
- Resource Server pattern (validates tokens, doesn't issue them)
- External clients (ChatGPT, Apps SDK) obtain tokens from Keycloak
- FluidMCP validates JWT tokens using OIDC discovery and JWKS

Usage:
    from fluidmcp.cli.auth import (
        load_oauth_config,
        JWTValidator,
        set_jwt_validator,
        get_token
    )

    # Load OAuth configuration
    config = load_oauth_config(Path(".oauth.json"))

    # Initialize JWT validator
    validator = JWTValidator(config)
    await validator.initialize()

    # Set global validator for middleware
    set_jwt_validator(validator)

    # Use in FastAPI endpoints
    @app.post("/api/endpoint")
    async def endpoint(token_data: dict = Depends(get_token)):
        # token_data contains validated JWT claims
        pass
"""

from .config import (
    OAuthConfig,
    KeycloakConfig,
    JWTValidationConfig,
    CachingConfig,
    load_oauth_config,
    find_oauth_config,
    validate_oauth_config
)

from .jwt_validator import (
    JWTValidator,
    JWTValidationError,
    JWTSignatureError,
    JWTExpiredError,
    JWTAudienceError,
    JWTIssuerError,
    JWTScopeError
)

from .middleware import (
    get_token,
    set_jwt_validator,
    get_jwt_validator,
    get_authentication_status
)

from .mcp_metadata import (
    get_mcp_metadata_endpoint,
    create_auth_status_endpoint
)

from .oidc_discovery import (
    OIDCDiscoveryClient,
    OIDCConfiguration,
    construct_well_known_url
)

from .token_cache import TokenCache
from .jwks_cache import JWKSCache


__all__ = [
    # Configuration
    "OAuthConfig",
    "KeycloakConfig",
    "JWTValidationConfig",
    "CachingConfig",
    "load_oauth_config",
    "find_oauth_config",
    "validate_oauth_config",

    # JWT Validation
    "JWTValidator",
    "JWTValidationError",
    "JWTSignatureError",
    "JWTExpiredError",
    "JWTAudienceError",
    "JWTIssuerError",
    "JWTScopeError",

    # Middleware
    "get_token",
    "set_jwt_validator",
    "get_jwt_validator",
    "get_authentication_status",

    # MCP Metadata
    "get_mcp_metadata_endpoint",
    "create_auth_status_endpoint",

    # OIDC Discovery
    "OIDCDiscoveryClient",
    "OIDCConfiguration",
    "construct_well_known_url",

    # Caching
    "TokenCache",
    "JWKSCache",
]
