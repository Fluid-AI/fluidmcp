"""
Reusable retry decorator with exponential backoff.

Provides a clean way to add retry logic to async functions.
"""

import asyncio
import functools
from typing import Callable, TypeVar, Optional, Tuple, Type
from loguru import logger

T = TypeVar('T')


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None
):
    """
    Decorator that retries async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay before first retry in seconds (default: 0)
        backoff_factor: Multiplier for delay between retries (default: 2.0)
        max_delay: Maximum delay between retries in seconds (default: 60.0)
        retryable_exceptions: Tuple of exception types to retry on (default: all)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_backoff(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
        async def fetch_data():
            response = await client.get("/api/data")
            return response.json()

    Backoff sequence (initial_delay=2, backoff_factor=2):
        Attempt 0: immediate
        Attempt 1: wait 2s  (2 * 2^0)
        Attempt 2: wait 4s  (2 * 2^1)
        Attempt 3: wait 8s  (2 * 2^2)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"{func.__name__} succeeded on attempt {attempt + 1}/{max_retries + 1}")
                    return result

                except Exception as e:
                    last_exception = e

                    # Check if exception is retryable
                    if retryable_exceptions and not isinstance(e, retryable_exceptions):
                        logger.debug(f"{func.__name__} raised non-retryable exception: {type(e).__name__}")
                        raise

                    # Last attempt - don't wait, just raise
                    if attempt >= max_retries:
                        logger.error(f"{func.__name__} failed after {max_retries + 1} attempts: {e}")
                        raise

                    # Calculate delay with exponential backoff
                    if initial_delay > 0 and attempt > 0:
                        # First retry (attempt=1) uses initial_delay
                        # Subsequent retries use exponential backoff
                        delay = min(initial_delay * (backoff_factor ** (attempt - 1)), max_delay)
                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                            f"Retrying immediately..."
                        )

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"{func.__name__} failed with no exception captured")

        return wrapper
    return decorator
