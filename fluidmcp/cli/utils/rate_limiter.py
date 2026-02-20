"""
Rate limiting utilities for FluidMCP API.

Provides both in-memory (process-local) and Redis-based (distributed) rate limiting.
"""
import os
import threading
import asyncio
from time import time as current_time
from collections import defaultdict
from typing import Dict, List, Optional
from loguru import logger


# In-memory rate limiter state
_rate_limit_store: Dict[str, List[float]] = defaultdict(list)
_rate_limit_last_cleanup: float = current_time()
_rate_limit_lock = threading.Lock()
_RATE_LIMIT_MAX_KEYS = 10000
_RATE_LIMIT_CLEANUP_INTERVAL = 60

# NEW COPILOT COMMENT 3 FIX: Global Redis connection pool for efficient reuse
_redis_client: Optional[object] = None  # redis.asyncio.Redis instance
_redis_lock = threading.Lock()

# HIGH PRIORITY FIX #5: Track active cleanup tasks to prevent accumulation
_active_cleanup_task: Optional[object] = None  # asyncio.Task instance
_cleanup_task_lock = threading.Lock()


async def _cleanup_rate_limiter_background(window_start: float):
    """
    Background task to clean up expired rate limiter entries.
    
    Args:
        window_start: Timestamp threshold for cleaning old entries
    """
    with _rate_limit_lock:
        keys_to_remove = []
        for k, timestamps in _rate_limit_store.items():
            # Remove entries older than window
            _rate_limit_store[k] = [t for t in timestamps if t > window_start]
            # Remove keys with no recent activity
            if not _rate_limit_store[k]:
                keys_to_remove.append(k)
        
        for k in keys_to_remove:
            del _rate_limit_store[k]
        
        logger.debug(f"Rate limiter cleanup: {len(keys_to_remove)} inactive keys removed, {len(_rate_limit_store)} active")


def safe_log_task_error(task):
    """Safely log errors from async tasks."""
    try:
        if exc := task.exception():
            logger.error(f"Rate limiter cleanup failed: {exc}")
    except Exception as e:
        logger.error(f"Error in task callback: {e}")


def check_rate_limit(key: str, max_requests: int, window_seconds: int):
    """
    In-memory, process-local rate limiter using sliding window algorithm.
    
    Args:
        key: Unique identifier for rate limit (e.g., "api:user123" or "register_model:192.168.1.1")
        max_requests: Maximum requests allowed in the window
        window_seconds: Time window in seconds
        
    Raises:
        HTTPException: If rate limit exceeded (429 Too Many Requests)
    """
    from fastapi import HTTPException
    
    global _rate_limit_last_cleanup, _active_cleanup_task
    now = current_time()
    window_start = now - window_seconds

    # COPILOT FIX: Check cleanup outside the main lock to avoid holding it during task spawn
    should_spawn_cleanup = False
    with _rate_limit_lock:
        if now - _rate_limit_last_cleanup > _RATE_LIMIT_CLEANUP_INTERVAL:
            _rate_limit_last_cleanup = now
            should_spawn_cleanup = True

        # Get entries without defaultdict auto-creation
        entries = _rate_limit_store.get(key)
        if entries is not None:
            # Clean old entries for this key
            entries = [t for t in entries if t > window_start]
            _rate_limit_store[key] = entries
        else:
            # Check capacity before adding new key
            if len(_rate_limit_store) >= _RATE_LIMIT_MAX_KEYS:
                logger.warning(f"Rate limiter at capacity ({_RATE_LIMIT_MAX_KEYS} keys), removing oldest")
                # Remove oldest 100 keys
                sorted_keys = sorted(
                    _rate_limit_store.items(),
                    key=lambda x: max(x[1]) if x[1] else 0
                )
                for old_key, _ in sorted_keys[:100]:
                    del _rate_limit_store[old_key]
            entries = []
            _rate_limit_store[key] = entries
        
        if len(entries) >= max_requests:
            raise HTTPException(
                429,
                f"Rate limit exceeded: {max_requests} requests per {window_seconds}s"
            )
        
        entries.append(now)
        _rate_limit_store[key] = entries

    # COPILOT FIX: Spawn cleanup task AFTER releasing the lock
    if should_spawn_cleanup:
        try:
            loop = asyncio.get_running_loop()

            # Check if previous cleanup task completed
            with _cleanup_task_lock:
                if _active_cleanup_task is None or _active_cleanup_task.done():
                    task = loop.create_task(_cleanup_rate_limiter_background(window_start))
                    task.add_done_callback(safe_log_task_error)
                    _active_cleanup_task = task
                # else: cleanup already running, skip spawning new one

        except RuntimeError:
            # No event loop running - skip async cleanup (will be cleaned up inline for each key)
            pass


async def _get_redis_client():
    """
    Get or create a Redis client instance with connection pooling.

    NEW COPILOT COMMENT 3 FIX: Use connection pool instead of creating per-request connections.
    This significantly improves performance and prevents connection exhaustion under load.

    Returns:
        Redis client instance (reused across requests)
    """
    global _redis_client

    # COPILOT FIX: Remove outer check to ensure thread-safe initialization
    # Always acquire lock for initialization check
    with _redis_lock:
        if _redis_client is None:
            import redis.asyncio as redis

            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                raise ValueError("REDIS_URL not configured")

            # Create Redis client with connection pooling (default pool size: 50)
            # Connection pool is managed by redis-py and reused across calls
            _redis_client = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50  # Explicit pool size
            )
            logger.info("Initialized Redis connection pool for rate limiting")

    return _redis_client


async def check_rate_limit_redis(key: str, max_requests: int, window_seconds: int) -> bool:
    """
    Redis-based distributed rate limiter using sliding window.

    Args:
        key: Unique identifier for rate limit
        max_requests: Maximum requests allowed in the window
        window_seconds: Time window in seconds

    Returns:
        True if request is allowed, False if rate limit exceeded

    Raises:
        HTTPException: If rate limit exceeded
    """
    from fastapi import HTTPException

    try:
        # NEW COPILOT COMMENT 3 FIX: Reuse Redis connection from pool instead of creating new one
        r = await _get_redis_client()

        now = current_time()
        window_start = now - window_seconds

        # Remove old entries
        await r.zremrangebyscore(key, 0, window_start)

        # Count current requests
        count = await r.zcard(key)

        if count >= max_requests:
            raise HTTPException(
                429,
                f"Rate limit exceeded: {max_requests} requests per {window_seconds}s"
            )

        # Add current request
        await r.zadd(key, {str(now): now})
        await r.expire(key, window_seconds)

        return True

    except ImportError:
        logger.warning("Redis not available, falling back to in-memory rate limiting")
        check_rate_limit(key, max_requests, window_seconds)
        return True


def get_rate_limiter_stats() -> dict:
    """
    Get statistics about current rate limiter state.
    
    Returns:
        Dictionary with stats: total_keys, total_entries, etc.
    """
    with _rate_limit_lock:
        total_entries = sum(len(entries) for entries in _rate_limit_store.values())
        return {
            "total_keys": len(_rate_limit_store),
            "total_entries": total_entries,
            "max_keys": _RATE_LIMIT_MAX_KEYS,
            "cleanup_interval_seconds": _RATE_LIMIT_CLEANUP_INTERVAL
        }


def clear_rate_limiter():
    """Clear all rate limiter entries."""
    with _rate_limit_lock:
        _rate_limit_store.clear()
        logger.info("Rate limiter cleared")


async def close_redis_client():
    """
    Close the Redis connection pool gracefully.

    NEW COPILOT COMMENT 3 FIX: Cleanup function for graceful shutdown.
    Should be called during application shutdown to close Redis connections properly.
    """
    global _redis_client

    if _redis_client is not None:
        with _redis_lock:
            if _redis_client is not None:
                try:
                    await _redis_client.close()
                    logger.info("Closed Redis connection pool")
                except Exception as e:
                    logger.warning(f"Error closing Redis connection pool: {e}")
                finally:
                    _redis_client = None
