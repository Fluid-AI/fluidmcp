"""
Tests for EventLoopWatchdog — start/stop lifecycle and lag threshold behavior.
"""
import asyncio
import pytest
from unittest.mock import patch
from fluidmcp.cli.services.watchdog import EventLoopWatchdog, _get_env_float


class TestGetEnvFloat:
    """Tests for the safe env var parser."""

    def test_returns_default_when_unset(self):
        with patch.dict("os.environ", {}, clear=False):
            assert _get_env_float("FMCP_NONEXISTENT_VAR", 1.5) == 1.5

    def test_returns_default_on_invalid_value(self):
        with patch.dict("os.environ", {"FMCP_TEST_FLOAT": "not-a-float"}):
            assert _get_env_float("FMCP_TEST_FLOAT", 2.0) == 2.0

    def test_returns_default_on_empty_string(self):
        with patch.dict("os.environ", {"FMCP_TEST_FLOAT": ""}):
            assert _get_env_float("FMCP_TEST_FLOAT", 3.0) == 3.0

    def test_parses_valid_float(self):
        with patch.dict("os.environ", {"FMCP_TEST_FLOAT": "0.75"}):
            assert _get_env_float("FMCP_TEST_FLOAT", 1.0) == 0.75

    def test_returns_default_below_min_value(self):
        with patch.dict("os.environ", {"FMCP_TEST_FLOAT": "0.0"}):
            assert _get_env_float("FMCP_TEST_FLOAT", 1.0, min_value=0.001) == 1.0

    def test_accepts_value_at_min_value(self):
        with patch.dict("os.environ", {"FMCP_TEST_FLOAT": "0.001"}):
            assert _get_env_float("FMCP_TEST_FLOAT", 1.0, min_value=0.001) == 0.001


class TestEventLoopWatchdogLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        watchdog = EventLoopWatchdog()
        assert watchdog._task is None
        watchdog.start()
        assert watchdog._task is not None
        assert not watchdog._task.done()
        await watchdog.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        watchdog = EventLoopWatchdog()
        watchdog.start()
        task = watchdog._task
        await watchdog.stop()
        assert task.cancelled() or task.done()
        assert watchdog._task is None

    @pytest.mark.asyncio
    async def test_duplicate_start_ignored(self):
        watchdog = EventLoopWatchdog()
        watchdog.start()
        first_task = watchdog._task
        watchdog.start()  # second call — should be ignored
        assert watchdog._task is first_task  # same task, not replaced
        await watchdog.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self):
        """Calling stop() on a non-started watchdog should not raise."""
        watchdog = EventLoopWatchdog()
        await watchdog.stop()  # no-op, should not raise

    @pytest.mark.asyncio
    async def test_start_after_stop_creates_new_task(self):
        watchdog = EventLoopWatchdog()
        watchdog.start()
        first_task = watchdog._task
        await watchdog.stop()
        watchdog.start()
        assert watchdog._task is not first_task
        assert not watchdog._task.done()
        await watchdog.stop()


class TestEventLoopWatchdogThresholds:
    """Tests for lag threshold logging behavior."""

    @pytest.mark.asyncio
    async def test_no_log_below_warn_threshold(self):
        """No warning logged when lag is below threshold."""
        watchdog = EventLoopWatchdog()
        with patch("fluidmcp.cli.services.watchdog._WARN_THRESHOLD", 1.0), \
             patch("fluidmcp.cli.services.watchdog._ERROR_THRESHOLD", 2.0), \
             patch("fluidmcp.cli.services.watchdog._CHECK_INTERVAL", 0.01), \
             patch("fluidmcp.cli.services.watchdog.logger") as mock_logger:
            watchdog.start()
            await asyncio.sleep(0.05)
            await watchdog.stop()
            mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_warning_logged_above_warn_threshold(self):
        """Warning logged when lag exceeds warn threshold."""
        watchdog = EventLoopWatchdog()
        with patch("fluidmcp.cli.services.watchdog._WARN_THRESHOLD", 0.0), \
             patch("fluidmcp.cli.services.watchdog._ERROR_THRESHOLD", 999.0), \
             patch("fluidmcp.cli.services.watchdog._CHECK_INTERVAL", 0.01), \
             patch("fluidmcp.cli.services.watchdog.logger") as mock_logger:
            watchdog.start()
            await asyncio.sleep(0.05)
            await watchdog.stop()
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_error_logged_above_error_threshold(self):
        """Error logged when lag exceeds error threshold."""
        watchdog = EventLoopWatchdog()
        with patch("fluidmcp.cli.services.watchdog._WARN_THRESHOLD", 0.0), \
             patch("fluidmcp.cli.services.watchdog._ERROR_THRESHOLD", 0.0), \
             patch("fluidmcp.cli.services.watchdog._CHECK_INTERVAL", 0.01), \
             patch("fluidmcp.cli.services.watchdog.logger") as mock_logger:
            watchdog.start()
            await asyncio.sleep(0.05)
            await watchdog.stop()
            mock_logger.error.assert_called()
