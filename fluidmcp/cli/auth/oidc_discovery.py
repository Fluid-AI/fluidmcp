"""
OIDC discovery client for FluidMCP OAuth.

This module handles OpenID Connect discovery, fetching configuration from
Keycloak's .well-known/openid-configuration endpoint.
"""

import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
import httpx
from loguru import logger


@dataclass
class OIDCConfiguration:
    """OIDC provider configuration from discovery document."""
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: Optional[str] = None
    end_session_endpoint: Optional[str] = None
    scopes_supported: Optional[list] = None
    grant_types_supported: Optional[list] = None
    code_challenge_methods_supported: Optional[list] = None


class OIDCDiscoveryClient:
    """
    OpenID Connect Discovery client.

    Fetches and caches OIDC configuration from the provider's well-known
    discovery endpoint. This configuration includes important URLs like
    the JWKS endpoint, token endpoint, and authorization endpoint.

    The discovery document is cached to minimize network requests to Keycloak.

    Example:
        client = OIDCDiscoveryClient(
            well_known_url="https://keycloak.example.com/realms/mcp/.well-known/openid-configuration"
        )

        config = await client.get_configuration()
        print(f"JWKS URI: {config.jwks_uri}")
        print(f"Issuer: {config.issuer}")
    """

    def __init__(
        self,
        well_known_url: str,
        cache_ttl_seconds: int = 3600,
        timeout_seconds: int = 10
    ):
        """
        Initialize OIDC discovery client.

        Args:
            well_known_url: URL to .well-known/openid-configuration endpoint
            cache_ttl_seconds: How long to cache discovery document (default: 3600 = 1 hour)
            timeout_seconds: HTTP request timeout (default: 10 seconds)
        """
        self.well_known_url = well_known_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds

        self._cached_config: Optional[OIDCConfiguration] = None
        self._cached_at: Optional[float] = None

        logger.debug(f"OIDCDiscoveryClient initialized: {well_known_url}")

    def _is_cache_valid(self) -> bool:
        """Check if cached configuration is still valid."""
        if self._cached_config is None or self._cached_at is None:
            return False

        age = time.time() - self._cached_at
        return age < self.cache_ttl_seconds

    async def get_configuration(self, force_refresh: bool = False) -> OIDCConfiguration:
        """
        Fetch OIDC configuration from discovery endpoint.

        Args:
            force_refresh: If True, bypass cache and fetch fresh configuration

        Returns:
            OIDCConfiguration object with provider configuration

        Raises:
            httpx.HTTPError: If discovery request fails
            ValueError: If discovery document is invalid
        """
        # Return cached config if valid
        if not force_refresh and self._is_cache_valid():
            logger.trace("Using cached OIDC configuration")
            return self._cached_config

        logger.debug(f"Fetching OIDC discovery document from {self.well_known_url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.well_known_url)
                response.raise_for_status()

                discovery_doc = response.json()

                # Parse and validate required fields
                config = self._parse_discovery_document(discovery_doc)

                # Cache the configuration
                self._cached_config = config
                self._cached_at = time.time()

                logger.info(f"OIDC configuration loaded successfully")
                logger.debug(f"Issuer: {config.issuer}")
                logger.debug(f"JWKS URI: {config.jwks_uri}")
                logger.debug(f"Token Endpoint: {config.token_endpoint}")
                logger.debug(f"Authorization Endpoint: {config.authorization_endpoint}")

                if config.grant_types_supported:
                    logger.debug(f"Supported grant types: {config.grant_types_supported}")
                if config.code_challenge_methods_supported:
                    logger.debug(f"Supported PKCE methods: {config.code_challenge_methods_supported}")

                return config

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching OIDC discovery document: {e.response.status_code}")
            logger.error(f"Response: {e.response.text}")
            raise ValueError(
                f"Failed to fetch OIDC discovery document: {e.response.status_code} {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Network error fetching OIDC discovery document: {e}")
            raise ValueError(f"Network error connecting to OIDC provider: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching OIDC discovery document")
            raise ValueError(f"Failed to fetch OIDC discovery document: {e}")

    def _parse_discovery_document(self, doc: Dict[str, Any]) -> OIDCConfiguration:
        """
        Parse and validate OIDC discovery document.

        Args:
            doc: Raw discovery document JSON

        Returns:
            Parsed OIDCConfiguration object

        Raises:
            ValueError: If required fields are missing
        """
        # Validate required fields per OIDC Discovery spec
        required_fields = ['issuer', 'authorization_endpoint', 'token_endpoint', 'jwks_uri']
        missing_fields = [field for field in required_fields if field not in doc]

        if missing_fields:
            raise ValueError(
                f"Invalid OIDC discovery document: missing required fields: {missing_fields}"
            )

        return OIDCConfiguration(
            issuer=doc['issuer'],
            authorization_endpoint=doc['authorization_endpoint'],
            token_endpoint=doc['token_endpoint'],
            jwks_uri=doc['jwks_uri'],
            userinfo_endpoint=doc.get('userinfo_endpoint'),
            end_session_endpoint=doc.get('end_session_endpoint'),
            scopes_supported=doc.get('scopes_supported'),
            grant_types_supported=doc.get('grant_types_supported'),
            code_challenge_methods_supported=doc.get('code_challenge_methods_supported')
        )

    def clear_cache(self) -> None:
        """Clear cached OIDC configuration."""
        self._cached_config = None
        self._cached_at = None
        logger.debug("OIDC discovery cache cleared")

    def get_cache_age(self) -> Optional[float]:
        """
        Get age of cached configuration in seconds.

        Returns:
            Age in seconds, or None if no cached configuration
        """
        if self._cached_at is None:
            return None
        return time.time() - self._cached_at


def construct_well_known_url(server_url: str, realm: str) -> str:
    """
    Construct OIDC well-known URL from Keycloak server URL and realm.

    Args:
        server_url: Keycloak server base URL (e.g., "https://keycloak.example.com")
        realm: Keycloak realm name (e.g., "mcp-realm")

    Returns:
        Full well-known URL

    Example:
        url = construct_well_known_url("https://keycloak.example.com", "mcp-realm")
        # Returns: "https://keycloak.example.com/realms/mcp-realm/.well-known/openid-configuration"
    """
    base_url = server_url.rstrip('/')
    return f"{base_url}/realms/{realm}/.well-known/openid-configuration"
