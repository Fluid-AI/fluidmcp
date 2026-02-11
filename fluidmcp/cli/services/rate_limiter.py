"""
Token bucket rate limiter for API calls.

Prevents exceeding API rate limits by controlling the rate of outgoing requests
on a per-model basis.
"""

import asyncio
import time
from typing import Dict, Optional, Any
from loguru import logger


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter for async operations.

    Allows bursts up to capacity, then enforces steady rate.

    Args:
        rate: Tokens per second (e.g., 10 = 10 requests/second)
        capacity: Maximum tokens in bucket (burst capacity)

    Example:
        limiter = TokenBucketRateLimiter(rate=10, capacity=20)
        await limiter.acquire()  # Blocks if rate limit exceeded
    """

    def __init__(self, rate: float, capacity: int):
        """
        Initialize rate limiter.

        Args:
            rate: Tokens added per second (must be positive)
            capacity: Maximum bucket size (must be positive)

        Raises:
            ValueError: If rate or capacity are not positive
        """
        if not isinstance(rate, (int, float)) or rate <= 0:
            raise ValueError(f"rate must be a positive number, got {rate!r}")
        if not isinstance(capacity, int) or capacity <= 0:
            raise ValueError(f"capacity must be a positive integer, got {capacity!r}")

        self.rate = float(rate)
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

        logger.debug(f"Created rate limiter: {rate} req/s, capacity {capacity}")

    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, blocking if necessary.

        Args:
            tokens: Number of tokens to acquire (default 1)

        Raises:
            ValueError: If tokens > capacity (impossible to acquire)

        Note:
            Current implementation holds the lock during sleep, which can cause
            head-of-line blocking under high contention (1000+ req/sec). This is
            intentional for simplicity and works fine for typical use cases.
            For high-throughput scenarios, consider releasing the lock before sleep
            and re-checking tokens after waking (see GitHub issue for optimization PR).
        """
        if tokens > self.capacity:
            raise ValueError(f"Cannot acquire {tokens} tokens (capacity: {self.capacity})")

        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update

                # Add tokens based on elapsed time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= tokens:
                    # Sufficient tokens available
                    self.tokens -= tokens
                    logger.debug(f"Acquired {tokens} token(s), {self.tokens:.2f} remaining")
                    return

                # Not enough tokens - calculate wait time
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.rate

                logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s for {tokens} token(s)")
                await asyncio.sleep(wait_time)

    async def get_available_tokens(self) -> float:
        """Get current number of available tokens without acquiring."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            return min(self.capacity, self.tokens + elapsed * self.rate)


# Global registry of rate limiters per model
# Note: This registry grows monotonically and limiters are NEVER automatically evicted.
# In long-running processes with many distinct model_id values, this can cause
# unbounded memory growth.
#
# Manual cleanup options:
# 1. API endpoint: POST /metrics/rate-limiters/clear (see management.py)
# 2. Direct call: await clear_rate_limiters() (below)
# 3. Future enhancement: Add remove_rate_limiter(model_id) for selective cleanup
#    or implement periodic pruning of inactive limiters
_rate_limiters: Dict[str, TokenBucketRateLimiter] = {}
_limiter_lock: Optional[asyncio.Lock] = None


def _get_limiter_lock() -> asyncio.Lock:
    """Get or create the global lock (lazy initialization to avoid event loop issues)."""
    global _limiter_lock
    if _limiter_lock is None:
        _limiter_lock = asyncio.Lock()
    return _limiter_lock


async def get_rate_limiter(
    model_id: str,
    rate: Optional[float] = None,
    capacity: Optional[int] = None
) -> TokenBucketRateLimiter:
    """
    Get or create rate limiter for a model.

    Args:
        model_id: Model identifier
        rate: Requests per second (default: 10)
        capacity: Burst capacity (default: 20)

    Returns:
        Rate limiter instance for the model

    Example:
        limiter = await get_rate_limiter("llama-2-70b", rate=5, capacity=10)
        await limiter.acquire()
    """
    # Default rate limits (conservative to avoid API errors)
    if rate is None:
        rate = 10.0  # 10 requests/second
    if capacity is None:
        capacity = 20  # Allow bursts up to 20

    async with _get_limiter_lock():
        if model_id not in _rate_limiters:
            _rate_limiters[model_id] = TokenBucketRateLimiter(rate, capacity)
            logger.info(f"Created rate limiter for '{model_id}': {rate} req/s, capacity {capacity}")

        return _rate_limiters[model_id]


async def configure_rate_limiter(
    model_id: str,
    rate: float,
    capacity: int
) -> None:
    """
    Configure or reconfigure rate limiter for a model.

    Args:
        model_id: Model identifier
        rate: Requests per second
        capacity: Burst capacity

    Example:
        await configure_rate_limiter("llama-2-70b", rate=5, capacity=10)
    """
    async with _get_limiter_lock():
        _rate_limiters[model_id] = TokenBucketRateLimiter(rate, capacity)
        logger.info(f"Configured rate limiter for '{model_id}': {rate} req/s, capacity {capacity}")


async def clear_rate_limiters() -> None:
    """Clear all rate limiters (useful for testing)."""
    global _rate_limiters
    async with _get_limiter_lock():
        _rate_limiters.clear()
    logger.debug("Cleared all rate limiters")


async def get_all_rate_limiter_stats() -> Dict[str, Dict[str, Any]]:
    """
    Get statistics for all rate limiters (thread-safe snapshot).

    Returns a snapshot of all rate limiters with their current stats.
    This avoids race conditions when iterating the global registry.

    Returns:
        Dict mapping model_id to stats (available_tokens, capacity, rate, utilization_pct)
    """
    async with _get_limiter_lock():
        # Take a snapshot of all limiters under lock
        limiters_snapshot = dict(_rate_limiters)

    # Now query each limiter's stats outside the global lock
    stats = {}
    for model_id, limiter in limiters_snapshot.items():
        available = await limiter.get_available_tokens()
        stats[model_id] = {
            "available_tokens": round(available, 2),
            "capacity": limiter.capacity,
            "rate": limiter.rate,
            "utilization_pct": round((1 - available / limiter.capacity) * 100, 2)
        }

    return stats
