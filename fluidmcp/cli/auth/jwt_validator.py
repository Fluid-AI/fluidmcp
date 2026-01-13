"""
JWT token validation for FluidMCP OAuth.

This module provides the main JWT validator that orchestrates signature
verification and claims validation using JWKS and token caching.
"""

from typing import Dict, Any, Optional
from jose import jwt, JWTError
from loguru import logger

from .config import OAuthConfig
from .oidc_discovery import OIDCDiscoveryClient, OIDCConfiguration
from .jwks_cache import JWKSCache
from .token_cache import TokenCache


class JWTValidationError(Exception):
    """Base exception for JWT validation errors."""
    pass


class JWTSignatureError(JWTValidationError):
    """JWT signature verification failed."""
    pass


class JWTExpiredError(JWTValidationError):
    """JWT token has expired."""
    pass


class JWTAudienceError(JWTValidationError):
    """JWT audience claim validation failed."""
    pass


class JWTIssuerError(JWTValidationError):
    """JWT issuer claim validation failed."""
    pass


class JWTScopeError(JWTValidationError):
    """JWT scope validation failed."""
    pass


class JWTValidator:
    """
    Main JWT token validator.

    Orchestrates the complete JWT validation process:
    1. Check token cache (fast path)
    2. Decode JWT header to get kid
    3. Fetch public key from JWKS cache
    4. Verify JWT signature
    5. Validate claims (exp, aud, iss, scope)
    6. Cache validation result
    7. Return decoded claims

    Example:
        config = load_oauth_config(Path(".oauth.json"))
        validator = JWTValidator(config)
        await validator.initialize()

        try:
            claims = await validator.validate_jwt(token)
            print(f"Token valid for user: {claims.get('sub')}")
        except JWTValidationError as e:
            print(f"Token validation failed: {e}")
    """

    def __init__(self, config: OAuthConfig):
        """
        Initialize JWT validator.

        Args:
            config: OAuth configuration
        """
        self.config = config

        # Initialize OIDC discovery client
        self.oidc_client = OIDCDiscoveryClient(
            well_known_url=config.keycloak.well_known_url,
            cache_ttl_seconds=config.caching.jwks_cache_ttl_seconds
        )

        # These will be initialized after OIDC discovery
        self.jwks_cache: Optional[JWKSCache] = None
        self.token_cache: Optional[TokenCache] = None
        self.oidc_config: Optional[OIDCConfiguration] = None

        self._initialized = False

        logger.debug("JWTValidator created (not yet initialized)")

    async def initialize(self) -> None:
        """
        Initialize the validator by fetching OIDC configuration.

        Must be called before validate_jwt(). Performs OIDC discovery
        and initializes JWKS and token caches.

        Raises:
            ValueError: If OIDC discovery fails
        """
        if self._initialized:
            logger.debug("JWTValidator already initialized")
            return

        logger.info("Initializing JWTValidator with OIDC discovery")

        try:
            # Fetch OIDC configuration
            self.oidc_config = await self.oidc_client.get_configuration()

            # Initialize JWKS cache with discovered JWKS URI
            self.jwks_cache = JWKSCache(
                jwks_uri=self.oidc_config.jwks_uri,
                cache_ttl_seconds=self.config.caching.jwks_cache_ttl_seconds
            )

            # Initialize token cache
            if self.config.caching.enable_token_cache:
                self.token_cache = TokenCache(
                    ttl_seconds=self.config.caching.token_cache_ttl_seconds
                )
            else:
                self.token_cache = None
                logger.debug("Token caching disabled")

            # Prefetch JWKS to warm up cache
            if self.jwks_cache:
                await self.jwks_cache.prefetch()

            self._initialized = True
            logger.info("JWTValidator initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize JWTValidator: {e}")
            raise ValueError(f"JWT validator initialization failed: {e}")

    async def validate_jwt(self, token: str) -> Dict[str, Any]:
        """
        Validate JWT token and return decoded claims.

        Validation steps:
        1. Check token cache (if enabled)
        2. Decode JWT header to extract kid
        3. Fetch public key from JWKS cache
        4. Verify JWT signature
        5. Validate claims (exp, aud, iss, scope)
        6. Cache result (if enabled)
        7. Return claims

        Args:
            token: JWT token string (without "Bearer " prefix)

        Returns:
            Decoded JWT claims dictionary

        Raises:
            JWTValidationError: If validation fails (with specific subclass)
        """
        if not self._initialized:
            raise RuntimeError("JWTValidator not initialized. Call initialize() first.")

        # Check token cache first (fast path)
        if self.token_cache:
            cached_claims = self.token_cache.get(token)
            if cached_claims:
                logger.debug("Token validation cache hit")
                return cached_claims

        # Decode JWT header to get kid (without verification)
        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')

            if not kid:
                raise JWTSignatureError("JWT header missing 'kid' (key ID)")

            logger.trace(f"JWT kid: {kid}")

        except JWTError as e:
            logger.error(f"Failed to decode JWT header: {e}")
            raise JWTSignatureError(f"Invalid JWT format: {e}")

        # Get public key from JWKS cache
        try:
            public_key = await self.jwks_cache.get_key(kid)
            if not public_key:
                raise JWTSignatureError(f"Public key not found for kid: {kid}")

        except ValueError as e:
            logger.error(f"Failed to fetch JWKS: {e}")
            raise JWTSignatureError(f"Failed to fetch public keys: {e}")

        # Verify JWT signature and decode claims
        try:
            # Build verification options
            options = {
                'verify_signature': self.config.jwt_validation.validate_signature,
                'verify_exp': self.config.jwt_validation.validate_expiry,
                'verify_aud': self.config.jwt_validation.validate_audience,
            }

            # Set expected audience if validation enabled
            audience = None
            if self.config.jwt_validation.validate_audience:
                audience = self.config.jwt_validation.audience

            # Set expected issuer
            issuer = self.config.jwt_validation.issuer or self.oidc_config.issuer

            # Decode and verify JWT
            claims = jwt.decode(
                token,
                public_key,
                algorithms=['RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512'],
                audience=audience,
                issuer=issuer,
                options=options
            )

            logger.debug(f"JWT signature verified successfully")
            logger.trace(f"JWT claims: {claims}")

        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            raise JWTExpiredError("Token expired")

        except jwt.JWTClaimsError as e:
            # This catches audience and issuer errors from jose
            error_msg = str(e).lower()
            if 'audience' in error_msg:
                logger.warning(f"JWT audience validation failed: {e}")
                raise JWTAudienceError(f"Invalid audience: {e}")
            elif 'issuer' in error_msg:
                logger.warning(f"JWT issuer validation failed: {e}")
                raise JWTIssuerError(f"Invalid issuer: {e}")
            else:
                logger.warning(f"JWT claims validation failed: {e}")
                raise JWTValidationError(f"Invalid token claims: {e}")

        except JWTError as e:
            logger.warning(f"JWT signature verification failed: {e}")
            raise JWTSignatureError(f"Signature verification failed: {e}")

        # Validate scopes (custom validation, not handled by jose)
        if self.config.jwt_validation.required_scopes:
            self._validate_scopes(claims)

        # Cache validated token
        if self.token_cache:
            self.token_cache.set(token, claims)

        logger.info(f"JWT validated successfully for subject: {claims.get('sub', 'unknown')}")
        return claims

    def _validate_scopes(self, claims: Dict[str, Any]) -> None:
        """
        Validate that required scopes are present in token.

        Args:
            claims: Decoded JWT claims

        Raises:
            JWTScopeError: If required scopes are missing
        """
        # Extract scopes from token
        # Keycloak uses 'scope' claim as space-separated string
        scope_claim = claims.get('scope', '')
        if isinstance(scope_claim, str):
            token_scopes = set(scope_claim.split())
        elif isinstance(scope_claim, list):
            token_scopes = set(scope_claim)
        else:
            token_scopes = set()

        # Check required scopes
        required_scopes = set(self.config.jwt_validation.required_scopes)
        missing_scopes = required_scopes - token_scopes

        if missing_scopes:
            logger.warning(f"JWT missing required scopes: {missing_scopes}")
            logger.debug(f"Token scopes: {token_scopes}")
            logger.debug(f"Required scopes: {required_scopes}")
            raise JWTScopeError(f"Missing required scopes: {missing_scopes}")

        logger.trace(f"JWT scopes validated: {token_scopes}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get validator statistics.

        Returns:
            Dictionary with statistics from all components
        """
        stats = {
            "initialized": self._initialized,
            "config": {
                "provider": self.config.provider,
                "validate_signature": self.config.jwt_validation.validate_signature,
                "validate_expiry": self.config.jwt_validation.validate_expiry,
                "validate_audience": self.config.jwt_validation.validate_audience,
                "required_scopes": self.config.jwt_validation.required_scopes,
            }
        }

        if self._initialized:
            stats["oidc"] = {
                "issuer": self.oidc_config.issuer,
                "jwks_uri": self.oidc_config.jwks_uri,
            }

            if self.jwks_cache:
                stats["jwks_cache"] = self.jwks_cache.get_stats()

            if self.token_cache:
                stats["token_cache"] = self.token_cache.get_stats()

        return stats
