"""Tests for OpenTelemetry shutdown logic."""
import os
import threading
import pytest
from unittest.mock import Mock, patch

from fluidmcp.cli.otel import init_otel, shutdown_otel


@pytest.fixture(autouse=True)
def reset_otel_state():
    """Reset OTEL global state before each test."""
    import fluidmcp.cli.otel as otel_module
    otel_module._otel_initialized = False
    otel_module._otel_shutdown_done = False
    otel_module._otel_provider = None
    yield
    # Cleanup after test
    otel_module._otel_initialized = False
    otel_module._otel_shutdown_done = False
    otel_module._otel_provider = None


def test_shutdown_when_not_initialized():
    """Shutdown should skip gracefully if OTEL not initialized."""
    result = shutdown_otel()
    assert result is True


def test_shutdown_when_disabled():
    """Shutdown should skip if OTEL was disabled."""
    with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
        init_otel()  # Returns False, doesn't initialize
        result = shutdown_otel()
        assert result is True


def test_shutdown_when_no_provider_reference():
    """Shutdown should skip if provider reference is None."""
    import fluidmcp.cli.otel as otel_module
    otel_module._otel_initialized = True
    otel_module._otel_provider = None

    result = shutdown_otel()
    assert result is True


def test_shutdown_idempotency():
    """Multiple shutdown calls should be safe."""
    with patch.dict(os.environ, {"OTEL_ENABLED": "true", "OTEL_EXPORTER": "console"}):
        init_otel()

        # First call
        assert shutdown_otel() is True

        # Subsequent calls (should skip)
        assert shutdown_otel() is True
        assert shutdown_otel() is True


def test_shutdown_thread_safety():
    """Concurrent shutdown calls should be thread-safe."""
    with patch.dict(os.environ, {"OTEL_ENABLED": "true", "OTEL_EXPORTER": "console"}):
        init_otel()

        results = []

        def shutdown_worker():
            results.append(shutdown_otel())

        threads = [threading.Thread(target=shutdown_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert all(results)
        assert len(results) == 10


def test_shutdown_with_custom_timeout():
    """Test timeout configuration via environment variable."""
    with patch.dict(os.environ, {
        "OTEL_ENABLED": "true",
        "OTEL_EXPORTER": "console",
        "OTEL_SHUTDOWN_TIMEOUT": "3.0"
    }):
        init_otel()

        # Mock provider to verify timeout value
        import fluidmcp.cli.otel as otel_module
        mock_provider = Mock()
        mock_provider.force_flush.return_value = True
        otel_module._otel_provider = mock_provider

        shutdown_otel()

        # Verify force_flush called with 3000ms
        mock_provider.force_flush.assert_called_once_with(timeout_millis=3000)


def test_shutdown_with_invalid_timeout():
    """Test invalid timeout value is handled gracefully."""
    with patch.dict(os.environ, {
        "OTEL_ENABLED": "true",
        "OTEL_EXPORTER": "console",
        "OTEL_SHUTDOWN_TIMEOUT": "invalid"
    }):
        init_otel()

        # Mock provider to verify default timeout is used
        import fluidmcp.cli.otel as otel_module
        mock_provider = Mock()
        mock_provider.force_flush.return_value = True
        otel_module._otel_provider = mock_provider

        shutdown_otel()

        # Should use default 5000ms
        mock_provider.force_flush.assert_called_once_with(timeout_millis=5000)


def test_shutdown_with_negative_timeout():
    """Test negative timeout is handled gracefully."""
    with patch.dict(os.environ, {
        "OTEL_ENABLED": "true",
        "OTEL_EXPORTER": "console",
        "OTEL_SHUTDOWN_TIMEOUT": "-1"
    }):
        init_otel()

        # Mock provider to verify default timeout is used
        import fluidmcp.cli.otel as otel_module
        mock_provider = Mock()
        mock_provider.force_flush.return_value = True
        otel_module._otel_provider = mock_provider

        shutdown_otel()

        # Should use default 5000ms
        mock_provider.force_flush.assert_called_once_with(timeout_millis=5000)


def test_shutdown_handles_flush_timeout():
    """Test that flush timeout is handled gracefully."""
    with patch.dict(os.environ, {"OTEL_ENABLED": "true", "OTEL_EXPORTER": "console"}):
        init_otel()

        import fluidmcp.cli.otel as otel_module
        mock_provider = Mock()
        mock_provider.force_flush.return_value = False  # Simulates timeout
        otel_module._otel_provider = mock_provider

        result = shutdown_otel()

        # Should return False (flush failed)
        assert result is False
        mock_provider.force_flush.assert_called_once()
        # Shutdown should still be called
        mock_provider.shutdown.assert_called_once()


def test_shutdown_handles_exceptions():
    """Shutdown should handle exceptions gracefully."""
    with patch.dict(os.environ, {"OTEL_ENABLED": "true", "OTEL_EXPORTER": "console"}):
        init_otel()

        import fluidmcp.cli.otel as otel_module
        mock_provider = Mock()
        mock_provider.force_flush.side_effect = RuntimeError("Network error")
        otel_module._otel_provider = mock_provider

        # Should not crash
        result = shutdown_otel()
        assert result is False  # Returns False on error


def test_shutdown_calls_force_flush_and_shutdown():
    """Test that both force_flush and shutdown are called."""
    with patch.dict(os.environ, {"OTEL_ENABLED": "true", "OTEL_EXPORTER": "console"}):
        init_otel()

        import fluidmcp.cli.otel as otel_module
        mock_provider = Mock()
        mock_provider.force_flush.return_value = True
        otel_module._otel_provider = mock_provider

        result = shutdown_otel()

        # Both methods should be called
        assert result is True
        mock_provider.force_flush.assert_called_once()
        mock_provider.shutdown.assert_called_once()


def test_shutdown_marks_complete_on_success():
    """Test that _otel_shutdown_done is set to True on successful shutdown."""
    with patch.dict(os.environ, {"OTEL_ENABLED": "true", "OTEL_EXPORTER": "console"}):
        init_otel()

        import fluidmcp.cli.otel as otel_module
        assert otel_module._otel_shutdown_done is False

        shutdown_otel()

        assert otel_module._otel_shutdown_done is True


def test_shutdown_marks_complete_on_error():
    """Test that _otel_shutdown_done is set to True even on error."""
    with patch.dict(os.environ, {"OTEL_ENABLED": "true", "OTEL_EXPORTER": "console"}):
        init_otel()

        import fluidmcp.cli.otel as otel_module
        mock_provider = Mock()
        mock_provider.force_flush.side_effect = RuntimeError("Error")
        otel_module._otel_provider = mock_provider

        assert otel_module._otel_shutdown_done is False

        shutdown_otel()

        # Should still mark as complete
        assert otel_module._otel_shutdown_done is True
