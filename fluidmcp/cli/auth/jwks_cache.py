"""
JWKS (JSON Web Key Set) caching for FluidMCP OAuth.

This module handles fetching and caching public keys from Keycloak's JWKS endpoint.
These keys are used to verify JWT signatures.
"""

import time
import threading
from typing import Optional, Dict, Any
from jose import jwk
from jose.backends.cryptography_backend import CryptographyRSAKey, CryptographyECKey
import httpx
from loguru import logger


class JWKSCache:
    """
    Thread-safe cache for JWKS (JSON Web Key Set).

    Fetches public keys from Keycloak's JWKS endpoint and caches them
    for signature verification. Keys are indexed by 'kid' (key ID) for
    fast lookup during JWT validation.

    Supports key rotation: multiple keys can be active simultaneously,
    allowing zero-downtime key rotation.

    Example:
        cache = JWKSCache(
            jwks_uri="https://keycloak.example.com/realms/mcp/protocol/openid-connect/certs",
            cache_ttl_seconds=3600
        )

        # Get a public key by kid
        key = await cache.get_key("key-id-123")

        # Use key to verify JWT signature
        # (handled by jwt_validator.py)
    """

    def __init__(
        self,
        jwks_uri: str,
        cache_ttl_seconds: int = 3600,
        timeout_seconds: int = 10
    ):
        """
        Initialize JWKS cache.

        Args:
            jwks_uri: URL to JWKS endpoint (from OIDC discovery)
            cache_ttl_seconds: How long to cache keys (default: 3600 = 1 hour)
            timeout_seconds: HTTP request timeout (default: 10 seconds)
        """
        self.jwks_uri = jwks_uri
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds

        self._keys: Dict[str, Any] = {}  # kid -> parsed key
        self._cached_at: Optional[float] = None
        self._lock = threading.Lock()

        logger.debug(f"JWKSCache initialized: {jwks_uri} (TTL={cache_ttl_seconds}s)")

    def _is_cache_valid(self) -> bool:
        """Check if cached JWKS is still valid."""
        if not self._keys or self._cached_at is None:
            return False

        age = time.time() - self._cached_at
        return age < self.cache_ttl_seconds

    async def get_key(self, kid: str, force_refresh: bool = False) -> Optional[Any]:
        """
        Get a public key by key ID (kid).

        Args:
            kid: Key ID from JWT header
            force_refresh: If True, fetch fresh JWKS even if cached

        Returns:
            Parsed public key object, or None if not found

        Raises:
            ValueError: If JWKS fetch fails
        """
        with self._lock:
            # Return cached key if valid and key exists
            if not force_refresh and self._is_cache_valid():
                key = self._keys.get(kid)
                if key:
                    logger.trace(f"JWKS cache hit for kid: {kid}")
                    return key
                else:
                    logger.trace(f"JWKS cache miss for kid: {kid} (key not in cache)")

        # Cache miss or expired - fetch fresh JWKS
        await self._fetch_jwks()

        with self._lock:
            key = self._keys.get(kid)
            if key:
                logger.trace(f"Found key after JWKS refresh: {kid}")
                return key
            else:
                logger.warning(f"Key not found in JWKS after refresh: {kid}")
                logger.debug(f"Available keys: {list(self._keys.keys())}")
                return None

    async def _fetch_jwks(self) -> None:
        """
        Fetch JWKS from Keycloak and parse keys.

        Raises:
            ValueError: If JWKS fetch or parsing fails
        """
        logger.debug(f"Fetching JWKS from {self.jwks_uri}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.jwks_uri)
                response.raise_for_status()

                jwks_data = response.json()

                # Parse JWKS document
                keys = self._parse_jwks(jwks_data)

                with self._lock:
                    self._keys = keys
                    self._cached_at = time.time()

                logger.info(f"JWKS fetched successfully: {len(keys)} keys loaded")
                logger.debug(f"Key IDs: {list(keys.keys())}")

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching JWKS: {e.response.status_code}")
            logger.error(f"Response: {e.response.text}")
            raise ValueError(
                f"Failed to fetch JWKS: {e.response.status_code} {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Network error fetching JWKS: {e}")
            raise ValueError(f"Network error connecting to JWKS endpoint: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching JWKS")
            raise ValueError(f"Failed to fetch JWKS: {e}")

    def _parse_jwks(self, jwks_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse JWKS document and extract keys.

        Args:
            jwks_data: Raw JWKS JSON

        Returns:
            Dictionary mapping kid -> parsed key object

        Raises:
            ValueError: If JWKS format is invalid
        """
        if 'keys' not in jwks_data:
            raise ValueError("Invalid JWKS: missing 'keys' field")

        keys = {}
        for key_data in jwks_data['keys']:
            try:
                kid = key_data.get('kid')
                if not kid:
                    logger.warning("Skipping JWK without 'kid' field")
                    continue

                # Parse key using python-jose
                parsed_key = self._parse_jwk(key_data)
                if parsed_key:
                    keys[kid] = parsed_key
                    logger.trace(f"Parsed JWK: kid={kid}, kty={key_data.get('kty')}, alg={key_data.get('alg')}")

            except Exception as e:
                logger.warning(f"Failed to parse JWK with kid={key_data.get('kid')}: {e}")
                continue

        if not keys:
            raise ValueError("No valid keys found in JWKS")

        return keys

    def _parse_jwk(self, key_data: Dict[str, Any]) -> Optional[Any]:
        """
        Parse a single JWK into a key object.

        Args:
            key_data: Single JWK JSON object

        Returns:
            Parsed key object (RSA or EC), or None if parsing fails
        """
        try:
            # Use python-jose to parse JWK
            # This handles RSA, EC, and other key types
            key_obj = jwk.construct(key_data)

            # Verify it's a supported key type
            if not isinstance(key_obj, (CryptographyRSAKey, CryptographyECKey)):
                logger.warning(f"Unsupported key type: {type(key_obj)}")
                return None

            return key_obj

        except Exception as e:
            logger.error(f"Failed to construct JWK: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear cached JWKS."""
        with self._lock:
            count = len(self._keys)
            self._keys.clear()
            self._cached_at = None
            logger.debug(f"JWKS cache cleared: {count} keys removed")

    def get_cache_age(self) -> Optional[float]:
        """
        Get age of cached JWKS in seconds.

        Returns:
            Age in seconds, or None if no cached JWKS
        """
        if self._cached_at is None:
            return None
        return time.time() - self._cached_at

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            return {
                "jwks_uri": self.jwks_uri,
                "keys_count": len(self._keys),
                "cache_ttl_seconds": self.cache_ttl_seconds,
                "cache_age_seconds": self.get_cache_age(),
                "is_valid": self._is_cache_valid(),
                "key_ids": list(self._keys.keys())
            }

    async def prefetch(self) -> None:
        """
        Prefetch JWKS to warm up the cache.

        Useful during application startup to avoid cold start penalty.
        """
        logger.debug("Prefetching JWKS to warm up cache")
        try:
            await self._fetch_jwks()
        except Exception as e:
            logger.warning(f"JWKS prefetch failed (non-fatal): {e}")
