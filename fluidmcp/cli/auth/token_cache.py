"""
Token validation result caching for FluidMCP OAuth.

This module provides in-memory caching of validated JWT token claims to improve
performance by avoiding repeated signature verification and claims validation.
"""

import hashlib
import threading
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger


@dataclass
class CachedToken:
    """Cached token validation result."""
    claims: Dict[str, Any]
    cached_at: float
    ttl_seconds: int

    def is_expired(self) -> bool:
        """Check if cache entry has exceeded its TTL."""
        return (time.time() - self.cached_at) > self.ttl_seconds


class TokenCache:
    """
    Thread-safe in-memory cache for validated JWT token claims.

    Uses SHA-256 hash of the JWT string as cache key to avoid storing
    full tokens in memory. Each cache entry has a TTL (default 5 minutes).

    Performance characteristics:
    - Cache hit: ~0.1ms (immediate return)
    - Cache miss: Falls back to full JWT validation (~1-2ms)

    Example:
        cache = TokenCache(ttl_seconds=300)

        # Cache a validated token
        cache.set(jwt_token, decoded_claims)

        # Retrieve cached claims
        claims = cache.get(jwt_token)
        if claims:
            # Use cached claims (fast path)
            pass
        else:
            # Perform full validation (slow path)
            pass
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        """
        Initialize token cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds (default: 300 = 5 minutes)
            max_size: Maximum number of tokens to cache (default: 1000)
        """
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, CachedToken] = {}
        self._lock = threading.Lock()
        self._enabled = True

        logger.debug(f"TokenCache initialized: TTL={ttl_seconds}s, max_size={max_size}")

    def _compute_cache_key(self, token: str) -> str:
        """
        Compute cache key from JWT token.

        Uses SHA-256 hash to avoid storing full tokens in cache keys.

        Args:
            token: JWT token string

        Returns:
            SHA-256 hex digest of the token
        """
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def get(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached token claims if available and not expired.

        Args:
            token: JWT token string

        Returns:
            Decoded token claims if cached and valid, None otherwise
        """
        if not self._enabled:
            return None

        cache_key = self._compute_cache_key(token)

        with self._lock:
            cached = self._cache.get(cache_key)

            if cached is None:
                logger.trace(f"Token cache miss: {cache_key[:16]}...")
                return None

            if cached.is_expired():
                logger.trace(f"Token cache expired: {cache_key[:16]}...")
                # Remove expired entry
                del self._cache[cache_key]
                return None

            logger.trace(f"Token cache hit: {cache_key[:16]}...")
            return cached.claims.copy()  # Return copy to prevent mutation

    def set(self, token: str, claims: Dict[str, Any]) -> None:
        """
        Cache validated token claims.

        Args:
            token: JWT token string
            claims: Decoded token claims to cache
        """
        if not self._enabled:
            return

        cache_key = self._compute_cache_key(token)

        with self._lock:
            # Enforce max size by removing oldest entries
            if len(self._cache) >= self.max_size:
                self._evict_oldest()

            self._cache[cache_key] = CachedToken(
                claims=claims.copy(),  # Store copy to prevent mutation
                cached_at=time.time(),
                ttl_seconds=self.ttl_seconds
            )

            logger.trace(f"Token cached: {cache_key[:16]}... (TTL={self.ttl_seconds}s)")

    def invalidate(self, token: str) -> bool:
        """
        Manually invalidate a cached token.

        Useful for logout scenarios or when a token needs to be revoked.

        Args:
            token: JWT token string to invalidate

        Returns:
            True if token was in cache and removed, False otherwise
        """
        cache_key = self._compute_cache_key(token)

        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.debug(f"Token invalidated: {cache_key[:16]}...")
                return True
            return False

    def clear(self) -> None:
        """Clear all cached tokens."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.debug(f"Token cache cleared: {count} entries removed")

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from cache.

        This is automatically called during get() operations, but can also
        be called manually for periodic cleanup.

        Returns:
            Number of expired entries removed
        """
        with self._lock:
            expired_keys = [
                key for key, cached in self._cache.items()
                if cached.is_expired()
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired token cache entries")

            return len(expired_keys)

    def _evict_oldest(self) -> None:
        """
        Evict oldest cache entry (by insertion order).

        Called when cache reaches max_size. Uses FIFO eviction policy.
        """
        if not self._cache:
            return

        # Find oldest entry by cached_at timestamp
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].cached_at)
        del self._cache[oldest_key]
        logger.trace(f"Evicted oldest cache entry: {oldest_key[:16]}...")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics (size, ttl, enabled)
        """
        with self._lock:
            return {
                "enabled": self._enabled,
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds
            }

    def disable(self) -> None:
        """Disable the cache (all get() calls return None)."""
        self._enabled = False
        logger.debug("Token cache disabled")

    def enable(self) -> None:
        """Enable the cache."""
        self._enabled = True
        logger.debug("Token cache enabled")
