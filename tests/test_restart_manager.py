"""Unit tests for RestartManager class."""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import patch, Mock
from fluidai_mcp.services.restart_manager import RestartManager, RestartStats
from fluidai_mcp.models.server_status import RestartPolicy


class TestRestartManager:
    """Test suite for RestartManager class."""

    @pytest.fixture
    def restart_manager(self):
        """Create a RestartManager instance for testing."""
        return RestartManager()

    @pytest.fixture
    def default_policy(self):
        """Create a default RestartPolicy for testing."""
        return RestartPolicy(
            max_restarts=5,
            initial_delay_seconds=2,
            backoff_multiplier=2.0,
            max_delay_seconds=60,
            restart_window_seconds=300
        )

    # Initialization Tests

    def test_init(self, restart_manager):
        """Test RestartManager initialization."""
        assert restart_manager._restart_history == {}

    # can_restart Tests

    def test_can_restart_no_history(self, restart_manager, default_policy):
        """Test can_restart with no restart history."""
        can_restart, reason = restart_manager.can_restart("test-server", default_policy, 0)

        assert can_restart is True
        assert reason is None

    def test_can_restart_below_max(self, restart_manager, default_policy):
        """Test can_restart when below max restarts."""
        can_restart, reason = restart_manager.can_restart("test-server", default_policy, 3)

        assert can_restart is True
        assert reason is None

    def test_can_restart_at_max(self, restart_manager, default_policy):
        """Test can_restart when at max restarts."""
        can_restart, reason = restart_manager.can_restart("test-server", default_policy, 5)

        assert can_restart is False
        assert "Max restarts (5) reached" in reason

    def test_can_restart_above_max(self, restart_manager, default_policy):
        """Test can_restart when above max restarts."""
        can_restart, reason = restart_manager.can_restart("test-server", default_policy, 10)

        assert can_restart is False
        assert "Max restarts (5) reached" in reason

    def test_can_restart_window_check_pass(self, restart_manager, default_policy):
        """Test can_restart with window check (pass)."""
        # Record 3 restarts within window
        now = datetime.now()
        restart_manager._restart_history["test-server"] = [
            now - timedelta(seconds=100),
            now - timedelta(seconds=200),
            now - timedelta(seconds=250)
        ]

        can_restart, reason = restart_manager.can_restart("test-server", default_policy, 3)

        assert can_restart is True
        assert reason is None

    def test_can_restart_window_check_fail(self, restart_manager, default_policy):
        """Test can_restart with window check (fail)."""
        # Record 5 restarts within window (at limit)
        now = datetime.now()
        restart_manager._restart_history["test-server"] = [
            now - timedelta(seconds=10),
            now - timedelta(seconds=50),
            now - timedelta(seconds=100),
            now - timedelta(seconds=150),
            now - timedelta(seconds=200)
        ]

        # Use restart_count=4 so that max_restarts check passes, and window check triggers
        can_restart, reason = restart_manager.can_restart("test-server", default_policy, 4)

        assert can_restart is False
        assert "Too many restarts" in reason
        assert "in 300s window" in reason

    def test_can_restart_old_restarts_ignored(self, restart_manager, default_policy):
        """Test can_restart ignores old restarts outside window."""
        # Record restarts: 2 old (outside window) + 3 new (within window)
        now = datetime.now()
        restart_manager._restart_history["test-server"] = [
            now - timedelta(seconds=50),   # Within window
            now - timedelta(seconds=100),  # Within window
            now - timedelta(seconds=200),  # Within window
            now - timedelta(seconds=400),  # Outside window
            now - timedelta(seconds=500)   # Outside window
        ]

        can_restart, reason = restart_manager.can_restart("test-server", default_policy, 3)

        assert can_restart is True  # Only 3 recent restarts count
        assert reason is None

    # calculate_backoff_delay Tests

    def test_calculate_backoff_delay_first_restart(self, restart_manager, default_policy):
        """Test backoff delay calculation for first restart."""
        delay = restart_manager.calculate_backoff_delay("test-server", default_policy, 0)

        assert delay == 2  # initial_delay_seconds * (2^0) = 2 * 1 = 2

    def test_calculate_backoff_delay_exponential_growth(self, restart_manager, default_policy):
        """Test exponential growth of backoff delay."""
        delays = [
            restart_manager.calculate_backoff_delay("test-server", default_policy, i)
            for i in range(6)
        ]

        expected = [2, 4, 8, 16, 32, 60]  # Last one capped at max_delay_seconds
        assert delays == expected

    def test_calculate_backoff_delay_capped_at_max(self, restart_manager, default_policy):
        """Test backoff delay is capped at max_delay_seconds."""
        delay = restart_manager.calculate_backoff_delay("test-server", default_policy, 10)

        assert delay == 60  # Capped at max_delay_seconds

    def test_calculate_backoff_delay_exponent_capped(self, restart_manager, default_policy):
        """Test exponent is capped at 10."""
        delay_10 = restart_manager.calculate_backoff_delay("test-server", default_policy, 10)
        delay_20 = restart_manager.calculate_backoff_delay("test-server", default_policy, 20)

        assert delay_10 == delay_20  # Both should be capped

    def test_calculate_backoff_delay_large_multiplier_warning(self, restart_manager):
        """Test warning is logged for large backoff_multiplier."""
        large_policy = RestartPolicy(
            max_restarts=5,
            initial_delay_seconds=2,
            backoff_multiplier=15.0,  # Too large
            max_delay_seconds=60,
            restart_window_seconds=300
        )

        with patch('fluidai_mcp.services.restart_manager.logger') as mock_logger:
            delay = restart_manager.calculate_backoff_delay("test-server", large_policy, 1)

            mock_logger.warning.assert_called_once()
            assert "too large" in mock_logger.warning.call_args[0][0]

    def test_calculate_backoff_delay_multiplier_capped(self, restart_manager):
        """Test backoff_multiplier is capped at 10.0."""
        large_policy = RestartPolicy(
            max_restarts=5,
            initial_delay_seconds=2,
            backoff_multiplier=15.0,  # Should be capped to 10.0
            max_delay_seconds=200,
            restart_window_seconds=300
        )

        delay = restart_manager.calculate_backoff_delay("test-server", large_policy, 2)

        # Should use 10.0 instead of 15.0
        expected = min(2 * (10.0 ** 2), 200)  # 2 * 100 = 200 (at max)
        assert delay == expected

    # record_restart Tests

    def test_record_restart_new_server(self, restart_manager):
        """Test recording restart for a new server."""
        restart_manager.record_restart("test-server")

        assert "test-server" in restart_manager._restart_history
        assert len(restart_manager._restart_history["test-server"]) == 1

    def test_record_restart_existing_server(self, restart_manager):
        """Test recording restart for an existing server."""
        restart_manager.record_restart("test-server")
        restart_manager.record_restart("test-server")

        assert len(restart_manager._restart_history["test-server"]) == 2

    def test_record_restart_timestamps_ordered(self, restart_manager):
        """Test restart timestamps are in chronological order."""
        restart_manager.record_restart("test-server")
        time.sleep(0.01)
        restart_manager.record_restart("test-server")

        history = restart_manager._restart_history["test-server"]
        assert history[0] < history[1]

    # reset_restart_history Tests

    def test_reset_restart_history_existing_server(self, restart_manager):
        """Test resetting restart history for existing server."""
        restart_manager.record_restart("test-server")
        restart_manager.reset_restart_history("test-server")

        assert "test-server" not in restart_manager._restart_history

    def test_reset_restart_history_nonexistent_server(self, restart_manager):
        """Test resetting restart history for nonexistent server (should not error)."""
        restart_manager.reset_restart_history("nonexistent")

        # Should not raise an exception
        assert "nonexistent" not in restart_manager._restart_history

    # cleanup_old_history Tests

    def test_cleanup_old_history_removes_old_entries(self, restart_manager):
        """Test cleanup removes old entries."""
        now = datetime.now()
        restart_manager._restart_history["test-server"] = [
            now - timedelta(seconds=7200),  # Older than 3600s
            now - timedelta(seconds=5400),  # Older than 3600s
            now - timedelta(seconds=100),   # Recent
            now - timedelta(seconds=50)     # Recent
        ]

        restart_manager.cleanup_old_history(max_age_seconds=3600)

        assert len(restart_manager._restart_history["test-server"]) == 2

    def test_cleanup_old_history_removes_server_if_no_recent(self, restart_manager):
        """Test cleanup removes server if no recent history."""
        now = datetime.now()
        restart_manager._restart_history["test-server"] = [
            now - timedelta(seconds=3700),  # Old
            now - timedelta(seconds=3800)   # Old
        ]

        restart_manager.cleanup_old_history(max_age_seconds=3600)

        assert "test-server" not in restart_manager._restart_history

    def test_cleanup_old_history_preserves_recent(self, restart_manager):
        """Test cleanup preserves recent entries."""
        now = datetime.now()
        restart_manager._restart_history["test-server"] = [
            now - timedelta(seconds=100),
            now - timedelta(seconds=200)
        ]

        restart_manager.cleanup_old_history(max_age_seconds=3600)

        assert "test-server" in restart_manager._restart_history
        assert len(restart_manager._restart_history["test-server"]) == 2

    # get_restart_stats Tests

    def test_get_restart_stats_no_history(self, restart_manager):
        """Test get_restart_stats with no history."""
        stats = restart_manager.get_restart_stats("test-server")

        assert stats["total_restarts"] == 0
        assert stats["last_restart"] is None
        assert stats["recent_restarts_1h"] == 0
        assert stats["recent_restarts_24h"] == 0

    def test_get_restart_stats_with_history(self, restart_manager):
        """Test get_restart_stats with restart history."""
        now = datetime.now()
        restart_manager._restart_history["test-server"] = [
            now - timedelta(minutes=10),   # Within 1h and 24h
            now - timedelta(minutes=30),   # Within 1h and 24h
            now - timedelta(hours=2),      # Within 24h only
            now - timedelta(hours=20),     # Within 24h only
            now - timedelta(days=2)        # Outside both windows
        ]

        stats = restart_manager.get_restart_stats("test-server")

        assert stats["total_restarts"] == 5
        assert stats["last_restart"] is not None
        assert stats["recent_restarts_1h"] == 2
        assert stats["recent_restarts_24h"] == 4

    def test_get_restart_stats_return_type(self, restart_manager):
        """Test get_restart_stats returns RestartStats TypedDict."""
        restart_manager.record_restart("test-server")
        stats = restart_manager.get_restart_stats("test-server")

        # Check all required keys are present
        assert "total_restarts" in stats
        assert "last_restart" in stats
        assert "recent_restarts_1h" in stats
        assert "recent_restarts_24h" in stats

    # wait_with_backoff Tests

    @patch('time.sleep')
    def test_wait_with_backoff_positive_delay(self, mock_sleep, restart_manager, default_policy):
        """Test wait_with_backoff with positive delay."""
        restart_manager.wait_with_backoff("test-server", default_policy, 2)

        expected_delay = 8  # initial_delay (2) * (2^2) = 8
        mock_sleep.assert_called_once_with(expected_delay)

    @patch('time.sleep')
    def test_wait_with_backoff_zero_delay(self, mock_sleep, restart_manager):
        """Test wait_with_backoff with zero delay."""
        zero_policy = RestartPolicy(
            max_restarts=5,
            initial_delay_seconds=0,
            backoff_multiplier=2.0,
            max_delay_seconds=60,
            restart_window_seconds=300
        )

        restart_manager.wait_with_backoff("test-server", zero_policy, 0)

        mock_sleep.assert_not_called()

    # Integration Tests

    def test_typical_restart_workflow(self, restart_manager, default_policy):
        """Test typical restart workflow."""
        server_name = "test-server"

        # First restart
        can_restart, _ = restart_manager.can_restart(server_name, default_policy, 0)
        assert can_restart is True
        restart_manager.record_restart(server_name)

        # Second restart
        can_restart, _ = restart_manager.can_restart(server_name, default_policy, 1)
        assert can_restart is True
        restart_manager.record_restart(server_name)

        # Check stats
        stats = restart_manager.get_restart_stats(server_name)
        assert stats["total_restarts"] == 2

        # Reset and verify
        restart_manager.reset_restart_history(server_name)
        stats = restart_manager.get_restart_stats(server_name)
        assert stats["total_restarts"] == 0
