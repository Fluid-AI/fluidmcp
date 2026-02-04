"""
Tests for retry decorator with exponential backoff.
"""

import pytest
import asyncio
import time
from fluidmcp.cli.utils.retry_decorator import retry_with_backoff


@pytest.mark.asyncio
class TestRetryDecorator:
    """Test suite for retry_with_backoff decorator."""

    async def test_success_no_retry(self):
        """Test that successful function doesn't retry."""
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=1.0)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()
        assert result == "success"
        assert call_count == 1  # Should only call once

    async def test_retry_on_transient_error(self):
        """Test retry on transient errors."""
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.1)
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        start = time.monotonic()
        result = await flaky_func()
        elapsed = time.monotonic() - start

        assert result == "success"
        assert call_count == 3  # Failed twice, succeeded on 3rd
        assert elapsed >= 0.1  # Should have waited at least once

    async def test_max_retries_exceeded(self):
        """Test that function raises after max retries."""
        call_count = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.05)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            await always_fails()

        assert call_count == 3  # Initial + 2 retries

    async def test_exponential_backoff_timing(self):
        """Test that backoff delays follow exponential pattern."""
        call_count = 0
        delays = []
        last_time = None

        @retry_with_backoff(max_retries=3, initial_delay=0.1, backoff_factor=2.0)
        async def measure_delays():
            nonlocal call_count, last_time
            current_time = time.monotonic()
            if last_time is not None:
                delays.append(current_time - last_time)
            last_time = current_time

            call_count += 1
            if call_count < 4:
                raise RuntimeError("Fail")
            return "success"

        result = await measure_delays()

        assert result == "success"
        assert len(delays) == 3  # 3 delays between 4 calls

        # Check exponential pattern
        # First retry is immediate (attempt=0, condition `attempt > 0` is false)
        # Second retry waits initial_delay * 2^0 = 0.1s (attempt=1)
        # Third retry waits initial_delay * 2^1 = 0.2s (attempt=2)
        assert delays[0] < 0.05  # Immediate retry (should be ~0ms)
        assert delays[1] >= 0.09  # ~0.1s
        assert delays[2] >= 0.18  # ~0.2s

    async def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        call_count = 0

        @retry_with_backoff(max_retries=5, initial_delay=1.0, backoff_factor=10.0, max_delay=2.0)
        async def capped_delays():
            nonlocal call_count
            call_count += 1
            if call_count < 6:
                raise RuntimeError("Fail")
            return "success"

        start = time.monotonic()
        result = await capped_delays()
        elapsed = time.monotonic() - start

        assert result == "success"
        # Total delay should be capped: 1s + 2s + 2s + 2s + 2s = 9s (not 1+10+100+1000+...)
        assert elapsed < 12.0  # Should be around 9s, definitely less than 12s

    async def test_retryable_exceptions_filter(self):
        """Test that only specified exceptions are retried."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            initial_delay=0.05,
            retryable_exceptions=(ConnectionError, TimeoutError)
        )
        async def selective_retry():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Retryable")
            elif call_count == 2:
                raise ValueError("Not retryable")
            return "success"

        with pytest.raises(ValueError, match="Not retryable"):
            await selective_retry()

        assert call_count == 2  # Should stop at ValueError

    async def test_immediate_retry_on_first_attempt(self):
        """Test that first retry is immediate if initial_delay=0."""
        call_count = 0
        delays = []
        last_time = None

        @retry_with_backoff(max_retries=2, initial_delay=0, backoff_factor=2.0)
        async def immediate_first_retry():
            nonlocal call_count, last_time
            current_time = time.monotonic()
            if last_time is not None:
                delays.append(current_time - last_time)
            last_time = current_time

            call_count += 1
            if call_count < 3:
                raise RuntimeError("Fail")
            return "success"

        result = await immediate_first_retry()

        assert result == "success"
        assert len(delays) == 2
        # First retry should be nearly immediate
        assert delays[0] < 0.05

    async def test_function_with_arguments(self):
        """Test that decorator preserves function arguments."""
        call_count = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.05)
        async def func_with_args(x: int, y: str, z: bool = False):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("Fail")
            return f"{x}-{y}-{z}"

        result = await func_with_args(42, "test", z=True)

        assert result == "42-test-True"
        assert call_count == 2

    async def test_concurrent_retries(self):
        """Test that multiple concurrent calls work correctly."""
        call_counts = {1: 0, 2: 0, 3: 0}

        @retry_with_backoff(max_retries=2, initial_delay=0.05)
        async def concurrent_func(task_id: int):
            call_counts[task_id] += 1
            if call_counts[task_id] < 2:
                raise RuntimeError(f"Task {task_id} fails")
            return f"Task {task_id} success"

        results = await asyncio.gather(
            concurrent_func(1),
            concurrent_func(2),
            concurrent_func(3)
        )

        assert results == ["Task 1 success", "Task 2 success", "Task 3 success"]
        assert all(count == 2 for count in call_counts.values())
