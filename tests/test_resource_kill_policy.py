"""
Tests for P4 - soft resource throttling and kill policy in MCPHealthMonitor.

Covers:
- Memory kill at >= memory_kill_pct
- Memory warn at >= memory_warn_pct (no kill)
- CPU stuck kill after N consecutive high cycles
- CPU counter resets on healthy cycle
- Kill loop cooldown (60s guard)
- No action when memory limit not configured
- Config-level threshold overrides
"""
import time
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

from fluidmcp.cli.services.server_manager import ServerManager, MCPHealthMonitor
from fluidmcp.cli.repositories import InMemoryBackend


@pytest.fixture
def backend():
    return InMemoryBackend()


@pytest.fixture
def server_manager(backend):
    return ServerManager(backend)


@pytest.fixture
def monitor(server_manager):
    return MCPHealthMonitor(server_manager, check_interval=30)


def _make_process(pid=1234, alive=True):
    p = Mock()
    p.pid = pid
    p.poll = Mock(return_value=None if alive else 1)
    return p


def _set_snapshot(monitor, server_id, memory_rss_bytes=None, cpu_percent=0.0):
    monitor._last_resource_snapshot[server_id] = {
        "memory_rss_bytes": memory_rss_bytes,
        "cpu_percent": cpu_percent,
        "active_requests": 0,
    }


# ---------------------------------------------------------------------------
# Memory kill policy
# ---------------------------------------------------------------------------

class TestMemoryKillPolicy:

    @pytest.mark.asyncio
    async def test_kills_when_memory_exceeds_kill_pct(self, monitor, server_manager):
        server_manager.configs["srv"] = {
            "memory_limit_mb": 100,
            "memory_kill_pct": 98,
            "memory_warn_pct": 90,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        # 99MB / 100MB = 99% > 98% kill threshold
        _set_snapshot(monitor, "srv", memory_rss_bytes=99 * 1024 * 1024)

        restart_called = []
        async def mock_restart_under_policy(server_id, proc, exit_code, config):
            restart_called.append((server_id, exit_code))
        monitor._restart_under_policy = mock_restart_under_policy

        await monitor._check_resource_thresholds("srv", process)

        assert len(restart_called) == 1
        assert restart_called[0] == ("srv", -1)

    @pytest.mark.asyncio
    async def test_warns_but_no_kill_at_warn_threshold(self, monitor, server_manager):
        server_manager.configs["srv"] = {
            "memory_limit_mb": 100,
            "memory_kill_pct": 98,
            "memory_warn_pct": 90,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        # 92MB / 100MB = 92% — above warn (90%) but below kill (98%)
        _set_snapshot(monitor, "srv", memory_rss_bytes=92 * 1024 * 1024)

        cleanup_called = []
        async def mock_cleanup(id, exit_code, intentional=False):
            cleanup_called.append((id, exit_code))
        server_manager._cleanup_server = mock_cleanup

        await monitor._check_resource_thresholds("srv", process)

        assert len(cleanup_called) == 0

    @pytest.mark.asyncio
    async def test_no_kill_when_memory_limit_not_configured(self, monitor, server_manager):
        server_manager.configs["srv"] = {"memory_limit_mb": 0}
        process = _make_process()
        server_manager.processes["srv"] = process
        # Even with enormous RSS, no kill without a limit to compare against
        _set_snapshot(monitor, "srv", memory_rss_bytes=999 * 1024 * 1024)

        cleanup_called = []
        async def mock_cleanup(id, exit_code, intentional=False):
            cleanup_called.append(id)
        server_manager._cleanup_server = mock_cleanup

        await monitor._check_resource_thresholds("srv", process)

        assert len(cleanup_called) == 0

    @pytest.mark.asyncio
    async def test_no_kill_when_no_snapshot(self, monitor, server_manager):
        server_manager.configs["srv"] = {"memory_limit_mb": 100}
        process = _make_process()
        server_manager.processes["srv"] = process
        # No snapshot yet

        cleanup_called = []
        async def mock_cleanup(id, exit_code, intentional=False):
            cleanup_called.append(id)
        server_manager._cleanup_server = mock_cleanup

        await monitor._check_resource_thresholds("srv", process)

        assert len(cleanup_called) == 0


# ---------------------------------------------------------------------------
# CPU stuck policy
# ---------------------------------------------------------------------------

class TestCpuStuckPolicy:

    @pytest.mark.asyncio
    async def test_kills_after_n_consecutive_high_cpu_cycles(self, monitor, server_manager):
        server_manager.configs["srv"] = {
            "cpu_warn_pct": 90,
            "cpu_kill_cycles": 3,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        _set_snapshot(monitor, "srv", cpu_percent=95.0)

        restart_called = []
        async def mock_restart_under_policy(server_id, proc, exit_code, config):
            restart_called.append((server_id, exit_code))
        monitor._restart_under_policy = mock_restart_under_policy

        # First two cycles: warning only
        await monitor._check_resource_thresholds("srv", process)
        assert len(restart_called) == 0
        assert monitor._high_cpu_cycles["srv"] == 1

        await monitor._check_resource_thresholds("srv", process)
        assert len(restart_called) == 0
        assert monitor._high_cpu_cycles["srv"] == 2

        # Third cycle: kill fires
        await monitor._check_resource_thresholds("srv", process)
        assert len(restart_called) == 1
        assert restart_called[0] == ("srv", -1)

    @pytest.mark.asyncio
    async def test_cpu_counter_resets_on_healthy_cycle(self, monitor, server_manager):
        server_manager.configs["srv"] = {"cpu_warn_pct": 90, "cpu_kill_cycles": 3}
        process = _make_process()
        server_manager.processes["srv"] = process

        # Two high-CPU cycles
        _set_snapshot(monitor, "srv", cpu_percent=95.0)
        await monitor._check_resource_thresholds("srv", process)
        await monitor._check_resource_thresholds("srv", process)
        assert monitor._high_cpu_cycles.get("srv") == 2

        # One healthy cycle resets the counter
        _set_snapshot(monitor, "srv", cpu_percent=10.0)
        await monitor._check_resource_thresholds("srv", process)
        assert "srv" not in monitor._high_cpu_cycles

    @pytest.mark.asyncio
    async def test_no_kill_below_cpu_warn_threshold(self, monitor, server_manager):
        server_manager.configs["srv"] = {"cpu_warn_pct": 90, "cpu_kill_cycles": 3}
        process = _make_process()
        server_manager.processes["srv"] = process
        _set_snapshot(monitor, "srv", cpu_percent=50.0)

        cleanup_called = []
        async def mock_cleanup(id, exit_code, intentional=False):
            cleanup_called.append(id)
        server_manager._cleanup_server = mock_cleanup

        for _ in range(5):
            await monitor._check_resource_thresholds("srv", process)

        assert len(cleanup_called) == 0


# ---------------------------------------------------------------------------
# Kill cooldown guard
# ---------------------------------------------------------------------------

class TestKillCooldown:

    @pytest.mark.asyncio
    async def test_second_kill_skipped_within_cooldown(self, monitor, server_manager):
        server_manager.configs["srv"] = {
            "memory_limit_mb": 100,
            "memory_kill_pct": 98,
            "memory_warn_pct": 90,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        _set_snapshot(monitor, "srv", memory_rss_bytes=99 * 1024 * 1024)

        restart_called = []
        async def mock_restart_under_policy(server_id, proc, exit_code, config):
            restart_called.append(server_id)
        monitor._restart_under_policy = mock_restart_under_policy

        # First kill fires
        await monitor._check_resource_thresholds("srv", process)
        assert len(restart_called) == 1

        # Immediately try again — should be blocked by 60s cooldown
        await monitor._check_resource_thresholds("srv", process)
        assert len(restart_called) == 1  # still 1, not 2

    @pytest.mark.asyncio
    async def test_kill_allowed_after_cooldown_expires(self, monitor, server_manager):
        server_manager.configs["srv"] = {
            "memory_limit_mb": 100,
            "memory_kill_pct": 98,
            "memory_warn_pct": 90,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        _set_snapshot(monitor, "srv", memory_rss_bytes=99 * 1024 * 1024)

        restart_called = []
        async def mock_restart_under_policy(server_id, proc, exit_code, config):
            restart_called.append(server_id)
        monitor._restart_under_policy = mock_restart_under_policy

        # First kill
        await monitor._check_resource_thresholds("srv", process)
        assert len(restart_called) == 1

        # Simulate cooldown expiry by backdating the last kill time
        monitor._last_kill_time["srv"] = time.monotonic() - 61

        # Second kill allowed
        await monitor._check_resource_thresholds("srv", process)
        assert len(restart_called) == 2


# ---------------------------------------------------------------------------
# Config overrides via server config
# ---------------------------------------------------------------------------

class TestConfigOverrides:

    @pytest.mark.asyncio
    async def test_per_server_memory_thresholds_respected(self, monitor, server_manager):
        # Lower kill threshold (80%) via per-server config
        server_manager.configs["srv"] = {
            "memory_limit_mb": 100,
            "memory_kill_pct": 80,
            "memory_warn_pct": 70,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        # 85MB / 100MB = 85% > 80% kill threshold
        _set_snapshot(monitor, "srv", memory_rss_bytes=85 * 1024 * 1024)

        restart_called = []
        async def mock_restart_under_policy(server_id, proc, exit_code, config):
            restart_called.append(server_id)
        monitor._restart_under_policy = mock_restart_under_policy

        await monitor._check_resource_thresholds("srv", process)
        assert len(restart_called) == 1

    @pytest.mark.asyncio
    async def test_per_server_cpu_kill_cycles_respected(self, monitor, server_manager):
        # Kill after just 1 cycle via per-server config
        server_manager.configs["srv"] = {
            "cpu_warn_pct": 80,
            "cpu_kill_cycles": 1,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        _set_snapshot(monitor, "srv", cpu_percent=85.0)

        restart_called = []
        async def mock_restart_under_policy(server_id, proc, exit_code, config):
            restart_called.append(server_id)
        monitor._restart_under_policy = mock_restart_under_policy

        await monitor._check_resource_thresholds("srv", process)
        assert len(restart_called) == 1


# ---------------------------------------------------------------------------
# Restart policy after resource kill
# ---------------------------------------------------------------------------

class TestRestartPolicyAfterKill:

    @pytest.mark.asyncio
    async def test_restart_invoked_after_memory_kill(self, monitor, server_manager):
        """_restart_under_policy must be called after a memory-triggered kill."""
        server_manager.configs["srv"] = {
            "memory_limit_mb": 100,
            "memory_kill_pct": 98,
            "memory_warn_pct": 90,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        _set_snapshot(monitor, "srv", memory_rss_bytes=99 * 1024 * 1024)

        restart_checked = []

        async def mock_cleanup(id, exit_code, intentional=False):
            pass

        async def mock_restart_under_policy(server_id, proc, exit_code, config):
            restart_checked.append(server_id)

        server_manager._cleanup_server = mock_cleanup
        monitor._restart_under_policy = mock_restart_under_policy

        await monitor._check_resource_thresholds("srv", process)

        assert restart_checked == ["srv"], "restart policy was not invoked after memory kill"

    @pytest.mark.asyncio
    async def test_restart_invoked_after_cpu_kill(self, monitor, server_manager):
        """_restart_under_policy must be called after a CPU-stuck kill."""
        server_manager.configs["srv"] = {
            "cpu_warn_pct": 80,
            "cpu_kill_cycles": 1,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        _set_snapshot(monitor, "srv", cpu_percent=85.0)

        restart_checked = []

        async def mock_cleanup(id, exit_code, intentional=False):
            pass

        async def mock_restart_under_policy(server_id, proc, exit_code, config):
            restart_checked.append(server_id)

        server_manager._cleanup_server = mock_cleanup
        monitor._restart_under_policy = mock_restart_under_policy

        await monitor._check_resource_thresholds("srv", process)

        assert restart_checked == ["srv"], "restart policy was not invoked after CPU kill"

    @pytest.mark.asyncio
    async def test_restart_not_invoked_when_cooldown_active(self, monitor, server_manager):
        """When cooldown guard skips the kill, restart must not be called either."""
        server_manager.configs["srv"] = {
            "memory_limit_mb": 100,
            "memory_kill_pct": 98,
        }
        process = _make_process()
        server_manager.processes["srv"] = process
        _set_snapshot(monitor, "srv", memory_rss_bytes=99 * 1024 * 1024)

        # Set a recent kill so cooldown is active
        monitor._last_kill_time["srv"] = time.monotonic()

        restart_checked = []

        async def mock_restart_under_policy(server_id, proc, exit_code, config):
            restart_checked.append(server_id)

        monitor._restart_under_policy = mock_restart_under_policy

        await monitor._check_resource_thresholds("srv", process)

        assert restart_checked == [], "restart should not be called when cooldown skipped the kill"
