"""
Response caching layer for API calls.

Caches responses to reduce redundant API calls and costs.
"""

import asyncio
import time
import hashlib
import json
from typing import Dict, Any, Optional, Callable, Awaitable
from collections import OrderedDict
from loguru import logger


class ResponseCache:
    """
    LRU cache with TTL for API responses.

    Features:
    - Time-to-live (TTL) expiration
    - LRU eviction when max size reached
    - Thread-safe for async operations

    Args:
        ttl: Time-to-live in seconds (default: 300 = 5 minutes)
        max_size: Maximum number of cached items (default: 1000)

    Example:
        cache = ResponseCache(ttl=300, max_size=100)
        result = await cache.get_or_fetch("key", async_fetch_function)
    """

    def __init__(self, ttl: int = 300, max_size: int = 1000):
        """
        Initialize response cache.

        Args:
            ttl: Seconds until cached entries expire
            max_size: Maximum cache size (LRU eviction)
        """
        self.ttl = ttl
        self.max_size = max_size
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

        logger.debug(f"Created response cache: TTL={ttl}s, max_size={max_size}")

    def _generate_key(self, data: Any) -> str:
        """Generate cache key from data."""
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is expired."""
        age = time.monotonic() - entry["timestamp"]
        return age > self.ttl

    async def get(self, key: str) -> Optional[Any]:
        """
        Get item from cache if present and not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]

                if self._is_expired(entry):
                    # Expired - remove from cache
                    del self._cache[key]
                    self._misses += 1
                    logger.debug(f"Cache MISS (expired): {key[:16]}...")
                    return None

                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                logger.debug(f"Cache HIT: {key[:16]}...")
                return entry["value"]

            self._misses += 1
            logger.debug(f"Cache MISS: {key[:16]}...")
            return None

    async def set(self, key: str, value: Any) -> None:
        """
        Store item in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        async with self._lock:
            # Add/update entry
            self._cache[key] = {
                "value": value,
                "timestamp": time.monotonic()
            }

            # Move to end (most recently used)
            self._cache.move_to_end(key)

            # Evict oldest if over capacity
            while len(self._cache) > self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.debug(f"Cache evicted (LRU): {oldest_key[:16]}...")

            logger.debug(f"Cache SET: {key[:16]}... (size: {len(self._cache)})")

    async def get_or_fetch(
        self,
        data: Any,
        fetch_fn: Callable[[], Awaitable[Any]]
    ) -> Any:
        """
        Get from cache or fetch if not present.

        Args:
            data: Data to use as cache key (will be hashed)
            fetch_fn: Async function to fetch data on cache miss

        Returns:
            Cached or freshly fetched value

        Example:
            result = await cache.get_or_fetch(
                {"model": "llama", "prompt": "Hello"},
                lambda: client.predict(...)
            )
        """
        key = self._generate_key(data)

        # Try cache first
        cached = await self.get(key)
        if cached is not None:
            return cached

        # Cache miss - fetch and store
        value = await fetch_fn()
        await self.set(key, value)
        return value

    async def invalidate(self, data: Any) -> bool:
        """
        Invalidate cache entry.

        Args:
            data: Data to hash into cache key

        Returns:
            True if entry was removed, False if not found
        """
        key = self._generate_key(data)

        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache invalidated: {key[:16]}...")
                return True
            return False

    async def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info(f"Cache cleared: {count} entries removed")
            return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, size, hit_rate
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate": round(hit_rate, 2),
            "ttl": self.ttl
        }


# Global cache instance
_response_cache: Optional[ResponseCache] = None
_cache_lock = asyncio.Lock()


async def get_response_cache(
    ttl: int = 300,
    max_size: int = 1000,
    enabled: bool = True
) -> Optional[ResponseCache]:
    """
    Get or create global response cache.

    Args:
        ttl: Time-to-live in seconds
        max_size: Maximum cache size
        enabled: Whether caching is enabled

    Returns:
        ResponseCache instance or None if disabled

    Example:
        cache = await get_response_cache(ttl=600, max_size=500)
        if cache:
            result = await cache.get_or_fetch(data, fetch_fn)
    """
    if not enabled:
        return None

    global _response_cache

    async with _cache_lock:
        if _response_cache is None:
            _response_cache = ResponseCache(ttl=ttl, max_size=max_size)
            logger.info(f"Initialized response cache: TTL={ttl}s, max_size={max_size}")

        return _response_cache


async def clear_response_cache() -> int:
    """Clear global response cache."""
    global _response_cache

    if _response_cache:
        return await _response_cache.clear()
    return 0
