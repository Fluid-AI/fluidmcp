"""
Tests for response caching layer.
"""

import pytest
import asyncio
from fluidmcp.cli.services.response_cache import ResponseCache, get_response_cache, clear_response_cache


@pytest.mark.asyncio
class TestResponseCache:
    """Test suite for ResponseCache."""

    async def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = ResponseCache(ttl=60, max_size=100)
        result = await cache.get("nonexistent_key")
        assert result is None

    async def test_cache_hit(self):
        """Test cache hit returns stored value."""
        cache = ResponseCache(ttl=60, max_size=100)

        await cache.set("key1", {"data": "value1"})
        result = await cache.get("key1")

        assert result == {"data": "value1"}

    async def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = ResponseCache(ttl=1, max_size=100)  # 1 second TTL

        await cache.set("expiring_key", "value")
        assert await cache.get("expiring_key") == "value"

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get("expiring_key")
        assert result is None

    async def test_max_size_eviction(self):
        """Test LRU eviction when max size reached."""
        cache = ResponseCache(ttl=60, max_size=3)

        # Fill cache
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        # Add 4th item - should evict key1 (oldest)
        await cache.set("key4", "value4")

        assert await cache.get("key1") is None  # Evicted
        assert await cache.get("key2") == "value2"
        assert await cache.get("key3") == "value3"
        assert await cache.get("key4") == "value4"

    async def test_lru_ordering(self):
        """Test that accessing items updates LRU order."""
        cache = ResponseCache(ttl=60, max_size=3)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        # Access key1 to make it most recent
        await cache.get("key1")

        # Add key4 - should evict key2 (now oldest)
        await cache.set("key4", "value4")

        assert await cache.get("key1") == "value1"  # Still present
        assert await cache.get("key2") is None  # Evicted
        assert await cache.get("key3") == "value3"
        assert await cache.get("key4") == "value4"

    async def test_get_or_fetch_cache_hit(self):
        """Test get_or_fetch with cache hit doesn't call fetch."""
        cache = ResponseCache(ttl=60, max_size=100)
        fetch_called = False

        async def fetch_fn():
            nonlocal fetch_called
            fetch_called = True
            return "fetched_value"

        # Prime cache
        await cache.set(cache._generate_key({"test": "data"}), "cached_value")

        result = await cache.get_or_fetch({"test": "data"}, fetch_fn)

        assert result == "cached_value"
        assert not fetch_called  # Fetch should not be called

    async def test_get_or_fetch_cache_miss(self):
        """Test get_or_fetch with cache miss calls fetch."""
        cache = ResponseCache(ttl=60, max_size=100)
        fetch_called = False

        async def fetch_fn():
            nonlocal fetch_called
            fetch_called = True
            return "fetched_value"

        result = await cache.get_or_fetch({"test": "data"}, fetch_fn)

        assert result == "fetched_value"
        assert fetch_called  # Fetch should be called

        # Second call should hit cache
        fetch_called = False
        result2 = await cache.get_or_fetch({"test": "data"}, fetch_fn)
        assert result2 == "fetched_value"
        assert not fetch_called  # Fetch should NOT be called again

    async def test_invalidate(self):
        """Test cache invalidation."""
        cache = ResponseCache(ttl=60, max_size=100)

        data = {"test": "data"}
        await cache.set(cache._generate_key(data), "value")

        # Invalidate
        removed = await cache.invalidate(data)
        assert removed is True

        # Should no longer be in cache
        result = await cache.get(cache._generate_key(data))
        assert result is None

    async def test_clear(self):
        """Test clearing entire cache."""
        cache = ResponseCache(ttl=60, max_size=100)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        count = await cache.clear()

        assert count == 3
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is None

    async def test_statistics(self):
        """Test cache statistics tracking."""
        cache = ResponseCache(ttl=60, max_size=100)

        await cache.set("key1", "value1")

        # Hit
        await cache.get("key1")

        # Miss
        await cache.get("key2")

        stats = await cache.get_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["max_size"] == 100
        assert stats["hit_rate"] == 50.0  # 1 hit out of 2 total

    async def test_concurrent_access(self):
        """Test cache with concurrent access."""
        cache = ResponseCache(ttl=60, max_size=100)

        async def writer(key: str, value: str):
            await cache.set(key, value)

        async def reader(key: str):
            return await cache.get(key)

        # Concurrent writes
        await asyncio.gather(
            writer("key1", "value1"),
            writer("key2", "value2"),
            writer("key3", "value3")
        )

        # Concurrent reads
        results = await asyncio.gather(
            reader("key1"),
            reader("key2"),
            reader("key3")
        )

        assert results == ["value1", "value2", "value3"]

    async def test_hash_generation_consistency(self):
        """Test that same data generates same key."""
        cache = ResponseCache(ttl=60, max_size=100)

        data1 = {"model": "llama", "prompt": "Hello", "temp": 0.7}
        data2 = {"temp": 0.7, "prompt": "Hello", "model": "llama"}  # Different order

        key1 = cache._generate_key(data1)
        key2 = cache._generate_key(data2)

        # Should be same key (order-independent)
        assert key1 == key2

    async def test_global_cache_instance(self):
        """Test global cache getter."""
        await clear_response_cache()

        cache1 = await get_response_cache(ttl=300, max_size=1000)
        cache2 = await get_response_cache(ttl=300, max_size=1000)

        # Should return same instance
        assert cache1 is cache2

    async def test_caching_disabled(self):
        """Test that caching can be disabled."""
        cache = await get_response_cache(enabled=False)
        assert cache is None
