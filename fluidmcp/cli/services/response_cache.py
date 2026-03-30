"""
Response caching layer for API calls.

Provides LRU cache with TTL for Replicate API responses to reduce costs and improve performance.

Features:
- Time-to-live (TTL) expiration
- LRU eviction when max size reached
- Thread-safe for async operations
- Prevents duplicate concurrent fetches (request coalescing)

Integration:
- Integrated with Replicate client when cache.enabled=true in config
- Automatically skipped for streaming and webhook requests
- Cache key based on model ID, input parameters, and version

Usage:
Enable caching in your config:
```json
{
  "llmModels": {
    "model-id": {
      "type": "replicate",
      "cache": {
        "enabled": true,
        "ttl": 300,
        "max_size": 1000
      }
    }
  }
}
```
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

    def __init__(self, ttl: float = 300.0, max_size: int = 1000):
        """
        Initialize response cache.

        Args:
            ttl: Seconds until cached entries expire (must be positive)
            max_size: Maximum cache size for LRU eviction (must be positive)

        Raises:
            ValueError: If ttl or max_size are not positive
        """
        if ttl <= 0:
            raise ValueError(f"ttl must be positive, got {ttl}")
        if max_size <= 0:
            raise ValueError(f"max_size must be positive, got {max_size}")

        self.ttl = ttl
        self.max_size = max_size
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._in_flight: Dict[str, asyncio.Future] = {}  # Track in-flight fetches
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

        Prevents duplicate fetches for the same key - if multiple concurrent
        calls request the same data, only one fetch executes while others wait.

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

        # Single critical section to check cache and register in-flight fetch
        created_future = False
        future = None
        async with self._lock:
            # Check cache first (with lock held to prevent races)
            if key in self._cache:
                entry = self._cache[key]
                if not self._is_expired(entry):
                    # Cache hit - move to end (LRU) and return
                    self._cache.move_to_end(key)
                    self._hits += 1
                    logger.debug(f"Cache HIT: {key[:16]}...")
                    return entry["value"]
                else:
                    # Expired - remove from cache
                    del self._cache[key]
                    logger.debug(f"Cache MISS (expired): {key[:16]}...")
            else:
                logger.debug(f"Cache MISS: {key[:16]}...")

            # Check if another task is already fetching
            future = self._in_flight.get(key)
            if future is None:
                # First task to start fetching for this key: create and register future
                # Only this task counts as a true miss (triggers actual fetch)
                self._misses += 1
                future = asyncio.get_running_loop().create_future()
                self._in_flight[key] = future
                created_future = True
                logger.debug(f"Starting new fetch for key: {key[:16]}... (counted as miss)")
            else:
                # Another task is already fetching - coalesce without counting as miss
                logger.debug(f"Waiting for in-flight fetch: {key[:16]}... (coalesced, not counted as miss)")

        if not created_future:
            # Another task is already fetching; just await its result
            return await future

        # This task is responsible for performing the fetch
        try:
            value = await fetch_fn()
            await self.set(key, value)

            # Mark future as done - set result BEFORE removing from registry
            # to avoid race condition where another task awaits removed future
            async with self._lock:
                in_flight_future = self._in_flight.get(key)
                if in_flight_future is not None and not in_flight_future.done():
                    in_flight_future.set_result(value)
                self._in_flight.pop(key, None)

            return value
        except BaseException as e:
            # Mark future as failed - set exception BEFORE removing from registry
            # BaseException catches Exception, CancelledError, and other async exceptions
            async with self._lock:
                in_flight_future = self._in_flight.get(key)
                if in_flight_future is not None and not in_flight_future.done():
                    # For CancelledError, cancel the future instead of set_exception
                    if isinstance(e, asyncio.CancelledError):
                        in_flight_future.cancel()
                    else:
                        in_flight_future.set_exception(e)
                        # Retrieve the exception to avoid "Future exception was never retrieved"
                        # warnings when no other task is awaiting this future
                        try:
                            _ = in_flight_future.exception()
                        except Exception:
                            pass  # Exception already set, ignore
                self._in_flight.pop(key, None)
            raise

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

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, size, hit_rate
        """
        async with self._lock:
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
_cache_lock: Optional[asyncio.Lock] = None


def _get_cache_lock() -> asyncio.Lock:
    """Get or create the global lock (lazy initialization to avoid event loop issues)."""
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


async def get_response_cache(
    ttl: float = 300.0,
    max_size: int = 1000,
    enabled: bool = True
) -> Optional[ResponseCache]:
    """
    Get or create global response cache.

    Note:
        This returns a single global cache instance. Per-model cache configuration
        (different TTL/max_size per model) is not currently supported - the cache
        settings from the first model to initialize the cache will be used for all
        models. For per-model caching with different settings, a future enhancement
        could maintain a dict of caches keyed by (ttl, max_size) or model_id.

    Args:
        ttl: Time-to-live in seconds (only used on first initialization)
        max_size: Maximum cache size (only used on first initialization)
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

    async with _get_cache_lock():
        if _response_cache is None:
            _response_cache = ResponseCache(ttl=ttl, max_size=max_size)
            logger.info(f"Initialized response cache: TTL={ttl}s, max_size={max_size}")
        else:
            # Cache already exists - warn if different settings requested
            existing_ttl = _response_cache.ttl
            existing_max_size = _response_cache.max_size
            if ttl != existing_ttl or max_size != existing_max_size:
                logger.warning(
                    f"Response cache already initialized with TTL={existing_ttl}s, max_size={existing_max_size}. "
                    f"Ignoring requested settings: TTL={ttl}s, max_size={max_size}. "
                    f"Global cache settings are shared across all models."
                )

        return _response_cache


async def peek_response_cache() -> Optional[ResponseCache]:
    """
    Peek at existing cache without creating it.

    Returns None if cache hasn't been initialized yet.
    Used by metrics endpoints to avoid side effects.

    Returns:
        Existing ResponseCache instance or None
    """
    return _response_cache


async def clear_response_cache() -> int:
    """Clear global response cache."""
    global _response_cache

    async with _get_cache_lock():
        if _response_cache:
            return await _response_cache.clear()
        return 0
