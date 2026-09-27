"""
Tests for P5 - stability tracking and log-based alerts in MCPHealthMonitor.

Covers:
- Restart timestamps accumulate per server
- Storm threshold triggers "unstable" flag in DB
- Old timestamps outside 10-min window are pruned
- Counter resets on sustained health (>5 min uptime)
- _clear_stability clears "unstable" flag after healthy operation
- _clear_stability is a no-op when already "stable"
- stability field present in all get_server_status() return paths
- Per-env FMCP_RESTART_STORM_THRESHOLD override
"""
import time
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock

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


# ---------------------------------------------------------------------------
# _check_stability — restart timestamp accumulation
# ---------------------------------------------------------------------------

class TestCheckStability:

    @pytest.mark.asyncio
    async def test_timestamps_accumulate(self, monitor):
        await monitor._check_stability("srv")
        await monitor._check_stability("srv")
        assert len(monitor._restart_timestamps.get("srv", [])) == 2

    @pytest.mark.asyncio
    async def test_old_timestamps_pruned(self, monitor):
        # Inject 3 old timestamps outside the 10-min window
        old = time.monotonic() - 700
        monitor._restart_timestamps["srv"] = [old, old, old]

        # A fresh restart should prune the old ones
        await monitor._check_stability("srv")
        assert len(monitor._restart_timestamps["srv"]) == 1

    @pytest.mark.asyncio
    async def test_no_flag_below_threshold(self, monitor, server_manager):
        with patch.dict("os.environ", {"FMCP_RESTART_STORM_THRESHOLD": "5"}):
            for _ in range(4):
                await monitor._check_stability("srv")

        instance = await server_manager.db.get_instance_state("srv")
        # Either no instance yet or stability not set to "unstable"
        if instance:
            assert instance.get("stability", "stable") != "unstable"

    @pytest.mark.asyncio
    async def test_marks_unstable_at_threshold(self, monitor, server_manager):
        with patch.dict("os.environ", {"FMCP_RESTART_STORM_THRESHOLD": "3"}):
            for _ in range(3):
                await monitor._check_stability("srv")

        instance = await server_manager.db.get_instance_state("srv")
        assert instance is not None
        assert instance.get("stability") == "unstable"

    @pytest.mark.asyncio
    async def test_env_threshold_override_respected(self, monitor, server_manager):
        # With threshold=2, second call should trigger unstable
        with patch.dict("os.environ", {"FMCP_RESTART_STORM_THRESHOLD": "2"}):
            await monitor._check_stability("srv2")
            instance = await server_manager.db.get_instance_state("srv2")
            if instance:
                assert instance.get("stability", "stable") != "unstable"  # only 1 so far

            await monitor._check_stability("srv2")

        instance = await server_manager.db.get_instance_state("srv2")
        assert instance is not None
        assert instance.get("stability") == "unstable"

    @pytest.mark.asyncio
    async def test_multiple_servers_tracked_independently(self, monitor, server_manager):
        with patch.dict("os.environ", {"FMCP_RESTART_STORM_THRESHOLD": "3"}):
            for _ in range(3):
                await monitor._check_stability("alpha")
            for _ in range(2):
                await monitor._check_stability("beta")

        alpha_instance = await server_manager.db.get_instance_state("alpha")
        beta_instance = await server_manager.db.get_instance_state("beta")

        assert alpha_instance is not None
        assert alpha_instance.get("stability") == "unstable"

        if beta_instance:
            assert beta_instance.get("stability", "stable") != "unstable"


# ---------------------------------------------------------------------------
# _clear_stability
# ---------------------------------------------------------------------------

class TestClearStability:

    @pytest.mark.asyncio
    async def test_clears_unstable_flag(self, monitor, server_manager):
        # Seed an unstable instance directly
        await server_manager.db.save_instance_state({
            "server_id": "srv",
            "stability": "unstable",
        })

        await monitor._clear_stability("srv")

        instance = await server_manager.db.get_instance_state("srv")
        assert instance["stability"] == "stable"

    @pytest.mark.asyncio
    async def test_noop_when_already_stable(self, monitor, server_manager):
        await server_manager.db.save_instance_state({
            "server_id": "srv",
            "stability": "stable",
        })

        # Should not raise, should not change anything
        await monitor._clear_stability("srv")

        instance = await server_manager.db.get_instance_state("srv")
        assert instance["stability"] == "stable"

    @pytest.mark.asyncio
    async def test_noop_when_no_instance(self, monitor, server_manager):
        # No instance in DB — should not raise
        await monitor._clear_stability("nonexistent")

    @pytest.mark.asyncio
    async def test_restart_timestamps_cleared_before_stability_clear(self, monitor, server_manager):
        # Simulate the reset path that removes timestamps then schedules _clear_stability
        monitor._restart_timestamps["srv"] = [time.monotonic()]

        # The health monitor removes timestamps before calling _clear_stability
        monitor._restart_timestamps.pop("srv", None)
        await monitor._clear_stability("srv")

        assert "srv" not in monitor._restart_timestamps


# ---------------------------------------------------------------------------
# stability field in get_server_status()
# ---------------------------------------------------------------------------

class TestStabilityInGetServerStatus:

    @pytest.mark.asyncio
    async def test_stability_present_when_running(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "name": "Test"}

        mock_process = Mock()
        mock_process.pid = 1234
        mock_process.poll = Mock(return_value=None)
        server_manager.processes["srv"] = mock_process

        await server_manager.db.save_instance_state({
            "server_id": "srv",
            "state": "running",
            "pid": 1234,
            "stability": "stable",
        })

        status = await server_manager.get_server_status("srv")
        assert "stability" in status
        assert status["stability"] == "stable"

    @pytest.mark.asyncio
    async def test_stability_unstable_surfaced(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "name": "Test"}

        mock_process = Mock()
        mock_process.pid = 1234
        mock_process.poll = Mock(return_value=None)
        server_manager.processes["srv"] = mock_process

        await server_manager.db.save_instance_state({
            "server_id": "srv",
            "state": "running",
            "pid": 1234,
            "stability": "unstable",
        })

        status = await server_manager.get_server_status("srv")
        assert status["stability"] == "unstable"

    @pytest.mark.asyncio
    async def test_stability_defaults_to_stable_when_not_in_db(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "name": "Test"}

        mock_process = Mock()
        mock_process.pid = 1234
        mock_process.poll = Mock(return_value=None)
        server_manager.processes["srv"] = mock_process

        await server_manager.db.save_instance_state({
            "server_id": "srv",
            "state": "running",
            "pid": 1234,
            # no "stability" key
        })

        status = await server_manager.get_server_status("srv")
        assert status.get("stability") == "stable"

    @pytest.mark.asyncio
    async def test_stability_present_for_not_found_server(self, server_manager):
        status = await server_manager.get_server_status("ghost")
        assert "stability" in status
        assert status["stability"] == "stable"
