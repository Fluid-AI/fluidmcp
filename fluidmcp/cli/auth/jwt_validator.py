"""
JWT validation with JWKS caching for Auth0.

This module handles JWT token validation using Auth0's JWKS endpoint
with caching to minimize external API calls.
"""

import os
import threading
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
from jose import jwt, jwk
from jose.exceptions import JWTError, ExpiredSignatureError, JWTClaimsError


class JWKSCache:
    """Cache for JWKS keys with TTL to avoid repeated fetches"""

    def __init__(self, jwks_url: str, ttl_seconds: int = 3600):
        """
        Initialize JWKS cache.

        Args:
            jwks_url: URL to Auth0 JWKS endpoint
            ttl_seconds: Time-to-live for cached keys (default: 3600 = 1 hour)
        """
        self.jwks_url = jwks_url
        self.ttl = timedelta(seconds=ttl_seconds)
        self._keys: Optional[Dict] = None
        self._expires_at: Optional[datetime] = None
        self._lock = threading.Lock()  # Thread safety for cache access

    def get_signing_key(self, kid: str):
        """
        Get signing key by Key ID (kid).

        Args:
            kid: Key ID from JWT header

        Returns:
            Signing key for JWT validation

        Raises:
            ValueError: If key ID not found in JWKS
        """
        with self._lock:
            # Refresh keys if cache is empty or expired
            if self._keys is None or self._expires_at is None or datetime.utcnow() >= self._expires_at:
                self._refresh_keys()

            # Find key with matching kid
            for key_data in self._keys.get("keys", []):
                if key_data.get("kid") == kid:
                    return jwk.construct(key_data)

        raise ValueError(f"Key ID {kid} not found in JWKS")

    def _refresh_keys(self):
        """Fetch fresh keys from JWKS endpoint"""
        try:
            response = requests.get(self.jwks_url, timeout=10)
            response.raise_for_status()
            self._keys = response.json()
            self._expires_at = datetime.utcnow() + self.ttl
        except requests.RequestException as e:
            raise ValueError(f"Failed to fetch JWKS from {self.jwks_url}: {e}")


# Global JWKS cache instance with thread safety
_jwks_cache: Optional[JWKSCache] = None
_cache_lock = threading.Lock()


def _get_jwks_cache() -> JWKSCache:
    """Get or create global JWKS cache instance (thread-safe)"""
    global _jwks_cache

    domain = os.getenv("FMCP_AUTH0_DOMAIN")
    if not domain:
        raise ValueError("FMCP_AUTH0_DOMAIN environment variable not set")

    jwks_url = f"https://{domain}/.well-known/jwks.json"

    with _cache_lock:
        # Check if cache needs refresh (None, different URL, or expired)
        needs_refresh = (
            _jwks_cache is None or
            _jwks_cache.jwks_url != jwks_url
        )

        if needs_refresh:
            _jwks_cache = JWKSCache(jwks_url)

        return _jwks_cache


async def validate_oauth_jwt(token: str, retry_on_key_error: bool = True) -> Dict[str, str]:
    """
    Validate Auth0 JWT token using JWKS endpoint.

    If validation fails due to missing key, will refresh JWKS cache
    and retry once to handle Auth0 key rotation.

    Args:
        token: JWT access token from Auth0
        retry_on_key_error: If True, retry once on key not found errors (default: True)

    Returns:
        User context dictionary with:
        - user_id: User's Auth0 sub (subject)
        - email: User's email address
        - name: User's display name
        - auth_method: Always 'oauth' for OAuth tokens

    Raises:
        ValueError: If token validation fails
    """
    try:
        # Get unverified header to extract kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            raise ValueError("Token missing 'kid' in header")

        # Get signing key from JWKS cache
        cache = _get_jwks_cache()
        signing_key = cache.get_signing_key(kid)

        # Get Auth0 configuration
        domain = os.getenv("FMCP_AUTH0_DOMAIN")
        audience = os.getenv("FMCP_AUTH0_AUDIENCE")

        # Decode and validate JWT
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=audience if audience else None,
            issuer=f"https://{domain}/"
        )

        # Extract user information
        user_id = payload.get("sub", "")
        email = payload.get("email", payload.get("name", ""))  # Fallback to name if no email
        name = payload.get("name", payload.get("email", "Unknown"))  # Fallback to email if no name

        return {
            "user_id": user_id,
            "email": email,
            "name": name,
            "auth_method": "oauth"
        }

    except ValueError as e:
        # Handle stale JWKS cache - Auth0 may have rotated keys
        if "Key ID" in str(e) and "not found" in str(e) and retry_on_key_error:
            from loguru import logger
            logger.warning(f"Key not found in JWKS cache, refreshing and retrying: {e}")

            # Force cache refresh by invalidating cached keys
            cache = _get_jwks_cache()
            with cache._lock:
                cache._keys = None
                cache._expires_at = None

            # Retry validation once with fresh keys
            return await validate_oauth_jwt(token, retry_on_key_error=False)

        # Re-raise for other ValueError cases or after retry
        raise
    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except JWTClaimsError as e:
        raise ValueError(f"Token claims validation failed: {e}")
    except JWTError as e:
        raise ValueError(f"Token validation failed: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error during token validation: {e}")
