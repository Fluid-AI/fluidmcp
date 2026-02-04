"""
Tests for token bucket rate limiter.

Tests rate limiting functionality to prevent API abuse.
"""

import pytest
import asyncio
import time
from fluidmcp.cli.services.rate_limiter import (
    TokenBucketRateLimiter,
    get_rate_limiter,
    configure_rate_limiter,
    clear_rate_limiters
)


@pytest.mark.asyncio
class TestTokenBucketRateLimiter:
    """Test suite for TokenBucketRateLimiter."""

    async def test_acquire_within_limit(self):
        """Test acquiring tokens within rate limit."""
        limiter = TokenBucketRateLimiter(rate=10, capacity=10)

        # Should acquire immediately (within capacity)
        start = time.monotonic()
        await limiter.acquire(tokens=5)
        elapsed = time.monotonic() - start

        assert elapsed < 0.1  # Should be nearly instant
        assert limiter.get_available_tokens() == pytest.approx(5.0, abs=1.0)

    async def test_acquire_blocks_when_full(self):
        """Test that acquire blocks when tokens exhausted."""
        limiter = TokenBucketRateLimiter(rate=10, capacity=10)

        # Exhaust all tokens
        await limiter.acquire(tokens=10)
        assert limiter.get_available_tokens() == pytest.approx(0.0, abs=0.5)

        # Next acquire should block
        start = time.monotonic()
        await limiter.acquire(tokens=5)
        elapsed = time.monotonic() - start

        # Should wait ~0.5 seconds (5 tokens at 10/sec)
        assert elapsed >= 0.4  # At least 400ms
        assert elapsed < 0.7   # But not too long

    async def test_rate_enforcement(self):
        """Test that rate limit is enforced over time."""
        limiter = TokenBucketRateLimiter(rate=10, capacity=5)

        # Make 15 requests (should take ~1 second at 10 req/s after burst)
        start = time.monotonic()
        for _ in range(15):
            await limiter.acquire()

        elapsed = time.monotonic() - start

        # First 5 are instant (capacity), next 10 take 1 second
        assert elapsed >= 0.9  # At least 900ms
        assert elapsed < 1.5   # But reasonable

    async def test_multiple_models(self):
        """Test rate limiters for multiple models are independent."""
        clear_rate_limiters()

        limiter1 = await get_rate_limiter("model-1", rate=10, capacity=10)
        limiter2 = await get_rate_limiter("model-2", rate=5, capacity=5)

        # Exhaust model-1
        await limiter1.acquire(tokens=10)
        assert limiter1.get_available_tokens() == pytest.approx(0.0, abs=0.5)

        # Model-2 should still have tokens
        start = time.monotonic()
        await limiter2.acquire(tokens=5)
        elapsed = time.monotonic() - start

        assert elapsed < 0.1  # Should be instant
        assert limiter1 is not limiter2  # Different instances

    async def test_rate_limit_reset(self):
        """Test that tokens replenish over time."""
        limiter = TokenBucketRateLimiter(rate=10, capacity=10)

        # Exhaust tokens
        await limiter.acquire(tokens=10)
        assert limiter.get_available_tokens() == pytest.approx(0.0, abs=0.5)

        # Wait for replenishment
        await asyncio.sleep(0.5)  # 0.5s * 10 tokens/s = 5 tokens

        available = limiter.get_available_tokens()
        assert available >= 4.0  # At least 4 tokens
        assert available <= 6.0  # Not more than 6

    async def test_concurrent_requests(self):
        """Test rate limiter with concurrent requests."""
        limiter = TokenBucketRateLimiter(rate=10, capacity=10)

        async def make_request(delay: float):
            await asyncio.sleep(delay)
            await limiter.acquire()

        # Launch 20 concurrent requests with staggered starts
        start = time.monotonic()
        tasks = [make_request(i * 0.01) for i in range(20)]
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        # First 10 instant (capacity), next 10 rate-limited
        # Should take ~1 second total (10 tokens at 10/sec)
        assert elapsed >= 0.9
        assert elapsed < 1.5

    async def test_burst_capacity(self):
        """Test that burst capacity allows temporary spikes."""
        limiter = TokenBucketRateLimiter(rate=5, capacity=20)

        # Burst of 20 requests should all go through instantly
        start = time.monotonic()
        for _ in range(20):
            await limiter.acquire()
        elapsed = time.monotonic() - start

        assert elapsed < 0.2  # All 20 should be instant

        # Next 10 should be rate-limited
        start = time.monotonic()
        for _ in range(10):
            await limiter.acquire()
        elapsed = time.monotonic() - start

        # 10 tokens at 5/sec = 2 seconds
        assert elapsed >= 1.8
        assert elapsed < 2.5

    async def test_configure_rate_limiter(self):
        """Test runtime configuration of rate limiters."""
        clear_rate_limiters()

        # Create with default rate
        limiter1 = await get_rate_limiter("test-model", rate=10, capacity=10)

        # Reconfigure
        await configure_rate_limiter("test-model", rate=20, capacity=20)

        # Should get new instance with new rate
        limiter2 = await get_rate_limiter("test-model")

        assert limiter1 is not limiter2
        assert limiter2.rate == 20
        assert limiter2.capacity == 20

    async def test_acquire_more_than_capacity_raises(self):
        """Test that requesting more tokens than capacity raises error."""
        limiter = TokenBucketRateLimiter(rate=10, capacity=10)

        with pytest.raises(ValueError, match="Cannot acquire 15 tokens"):
            await limiter.acquire(tokens=15)

    async def test_get_available_tokens_accuracy(self):
        """Test that get_available_tokens returns accurate count."""
        limiter = TokenBucketRateLimiter(rate=10, capacity=10)

        # Initially full
        assert limiter.get_available_tokens() == pytest.approx(10.0, abs=0.1)

        # After acquiring
        await limiter.acquire(tokens=3)
        assert limiter.get_available_tokens() == pytest.approx(7.0, abs=0.5)

        # After waiting
        await asyncio.sleep(0.3)  # 3 tokens should replenish
        assert limiter.get_available_tokens() == pytest.approx(10.0, abs=1.0)


@pytest.mark.asyncio
class TestRateLimiterIntegration:
    """Integration tests with Replicate client."""

    async def test_rate_limiter_prevents_burst(self):
        """Test that rate limiter prevents rapid burst requests."""
        clear_rate_limiters()

        # Configure very restrictive rate limit
        limiter = await get_rate_limiter("test-model", rate=2, capacity=2)

        # Try to make 5 requests rapidly
        start = time.monotonic()
        for _ in range(5):
            await limiter.acquire()
        elapsed = time.monotonic() - start

        # First 2 instant, next 3 take 1.5 seconds (at 2 req/s)
        assert elapsed >= 1.4  # Should enforce rate limit
        assert elapsed < 2.0

    async def test_rate_limiter_shared_across_calls(self):
        """Test that same model uses same rate limiter instance."""
        clear_rate_limiters()

        limiter1 = await get_rate_limiter("shared-model", rate=10, capacity=10)
        limiter2 = await get_rate_limiter("shared-model", rate=10, capacity=10)

        assert limiter1 is limiter2  # Same instance

        # Exhaust via limiter1
        await limiter1.acquire(tokens=10)

        # limiter2 should also be exhausted
        assert limiter2.get_available_tokens() == pytest.approx(0.0, abs=0.5)
