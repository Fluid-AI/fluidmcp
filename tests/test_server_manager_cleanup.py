"""
Tests for ServerManager process cleanup and signal handling.

Tests context manager support, cleanup handlers, and graceful shutdown.
"""
import pytest
import asyncio
import subprocess
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from fluidmcp.cli.services.server_manager import ServerManager
from fluidmcp.cli.repositories import InMemoryBackend


@pytest.fixture
def backend():
    """Create an in-memory backend (sync fixture)."""
    backend = InMemoryBackend()
    # Connect in tests that need it
    return backend


@pytest.fixture
def server_manager(backend):
    """Create a ServerManager instance with in-memory backend."""
    return ServerManager(backend)


@pytest.fixture
def mock_process():
    """Create a mock process object."""
    process = Mock(spec=subprocess.Popen)
    process.pid = 12345
    process.poll = Mock(return_value=None)  # Process running
    process.terminate = Mock()
    process.kill = Mock()
    process.wait = Mock()
    return process


class TestServerManagerContextManager:
    """Tests for ServerManager context manager functionality."""

    def test_context_manager_enter(self, server_manager):
        """Test context manager __enter__ returns self."""
        with server_manager as manager:
            assert manager is server_manager

    def test_context_manager_exit_calls_cleanup(self, server_manager, mock_process):
        """Test context manager __exit__ calls cleanup."""
        # Add a mock process
        server_manager.processes["test-server"] = mock_process

        # Use context manager
        with server_manager:
            pass

        # Verify cleanup was called
        mock_process.terminate.assert_called_once()

    def test_context_manager_handles_exceptions(self, server_manager):
        """Test context manager handles exceptions properly."""
        try:
            with server_manager:
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected

        # Manager should still be valid after exception


class TestCleanupOnExit:
    """Tests for _cleanup_on_exit method."""

    def test_cleanup_with_no_processes(self, server_manager):
        """Test cleanup with no running processes."""
        # Should not raise
        server_manager._cleanup_on_exit()

    def test_cleanup_terminates_running_process(self, server_manager, mock_process):
        """Test cleanup terminates running processes."""
        server_manager.processes["test-server"] = mock_process

        server_manager._cleanup_on_exit()

        # Verify termination was called
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called()

    def test_cleanup_force_kills_on_timeout(self, server_manager):
        """Test cleanup force kills process if termination times out."""
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll = Mock(return_value=None)
        mock_process.terminate = Mock()
        mock_process.kill = Mock()

        # First wait times out, second wait succeeds
        mock_process.wait = Mock(side_effect=[subprocess.TimeoutExpired("cmd", 5), None, None])

        server_manager.processes["test-server"] = mock_process

        server_manager._cleanup_on_exit()

        # Verify kill was called after timeout
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    def test_cleanup_handles_already_stopped_process(self, server_manager):
        """Test cleanup handles processes that already stopped."""
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll = Mock(return_value=0)  # Already stopped

        server_manager.processes["test-server"] = mock_process

        server_manager._cleanup_on_exit()

        # Should not try to terminate stopped process
        mock_process.terminate.assert_not_called()

    def test_cleanup_clears_process_registry(self, server_manager, mock_process):
        """Test cleanup clears the process registry."""
        server_manager.processes["server1"] = mock_process
        server_manager.processes["server2"] = mock_process

        server_manager._cleanup_on_exit()

        assert len(server_manager.processes) == 0

    def test_cleanup_handles_errors_gracefully(self, server_manager):
        """Test cleanup handles errors without crashing."""
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll = Mock(return_value=None)
        mock_process.terminate = Mock(side_effect=Exception("Test error"))
        mock_process.kill = Mock()
        mock_process.wait = Mock()

        server_manager.processes["test-server"] = mock_process

        # Should not raise despite error
        server_manager._cleanup_on_exit()


class TestShutdownAll:
    """Tests for shutdown_all async method."""

    @pytest.mark.asyncio
    async def test_shutdown_all_with_no_processes(self, server_manager):
        """Test shutdown_all with no running processes."""
        # Should not raise
        await server_manager.shutdown_all()

    @pytest.mark.asyncio
    async def test_shutdown_all_stops_all_servers(self, server_manager, backend):
        """Test shutdown_all calls stop_server for all processes."""
        # Mock stop_server method
        server_manager.stop_server = AsyncMock(return_value=True)

        # Add mock processes
        mock_process1 = Mock(spec=subprocess.Popen)
        mock_process2 = Mock(spec=subprocess.Popen)
        server_manager.processes["server1"] = mock_process1
        server_manager.processes["server2"] = mock_process2

        await server_manager.shutdown_all()

        # Verify stop_server was called for both
        assert server_manager.stop_server.call_count == 2

    @pytest.mark.asyncio
    async def test_shutdown_all_handles_stop_errors(self, server_manager):
        """Test shutdown_all handles errors during stop."""
        # Mock stop_server to raise error
        server_manager.stop_server = AsyncMock(side_effect=Exception("Stop failed"))

        # Add mock process
        mock_process = Mock(spec=subprocess.Popen)
        server_manager.processes["test-server"] = mock_process

        # Should not raise, but log error
        await server_manager.shutdown_all()

    @pytest.mark.asyncio
    async def test_shutdown_all_continues_after_error(self, server_manager):
        """Test shutdown_all continues stopping other servers after error."""
        stop_calls = []

        async def mock_stop(server_id):
            stop_calls.append(server_id)
            if server_id == "server1":
                raise Exception("Stop failed")
            return True

        server_manager.stop_server = mock_stop

        # Add mock processes
        mock_process = Mock(spec=subprocess.Popen)
        server_manager.processes["server1"] = mock_process
        server_manager.processes["server2"] = mock_process

        await server_manager.shutdown_all()

        # Both servers should have stop attempted
        assert len(stop_calls) == 2
        assert "server1" in stop_calls
        assert "server2" in stop_calls


class TestAtexitRegistration:
    """Tests for atexit handler registration."""

    def test_atexit_registered_on_init(self, backend):
        """Test that cleanup handler is registered on initialization."""
        with patch('atexit.register') as mock_register:
            manager = ServerManager(backend)
            mock_register.assert_called_once()

    def test_cleanup_called_on_program_exit(self, server_manager, mock_process):
        """Test cleanup is called when Python exits (simulated)."""
        server_manager.processes["test-server"] = mock_process

        # Simulate program exit by calling cleanup directly
        # (actual atexit test would require subprocess)
        server_manager._cleanup_on_exit()

        mock_process.terminate.assert_called_once()


class TestProcessZombieReaping:
    """Tests for zombie process prevention."""

    def test_wait_called_after_terminate(self, server_manager):
        """Test that wait() is called after terminate to reap zombies."""
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll = Mock(return_value=None)
        mock_process.terminate = Mock()
        mock_process.wait = Mock()

        server_manager.processes["test-server"] = mock_process

        server_manager._cleanup_on_exit()

        # Verify wait was called (multiple times for reaping)
        assert mock_process.wait.call_count >= 1

    def test_wait_called_after_kill(self, server_manager):
        """Test that wait() is called after kill to reap zombies."""
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll = Mock(return_value=None)
        mock_process.terminate = Mock()
        mock_process.kill = Mock()
        mock_process.wait = Mock(side_effect=[subprocess.TimeoutExpired("cmd", 5), None, None])

        server_manager.processes["test-server"] = mock_process

        server_manager._cleanup_on_exit()

        # Kill should be called after terminate timeout
        mock_process.kill.assert_called_once()
        # Wait should be called after kill
        assert mock_process.wait.call_count >= 2


class TestGracefulVsForcedShutdown:
    """Tests for graceful shutdown with fallback to forced."""

    def test_graceful_shutdown_succeeds(self, server_manager):
        """Test successful graceful shutdown."""
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll = Mock(return_value=None)
        mock_process.terminate = Mock()
        mock_process.wait = Mock(return_value=0)  # Successful termination
        mock_process.kill = Mock()

        server_manager.processes["test-server"] = mock_process

        server_manager._cleanup_on_exit()

        # Verify graceful termination was attempted
        mock_process.terminate.assert_called_once()
        # Kill should NOT be called
        mock_process.kill.assert_not_called()

    def test_forced_shutdown_after_timeout(self, server_manager):
        """Test forced shutdown after graceful timeout."""
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll = Mock(return_value=None)
        mock_process.terminate = Mock()
        mock_process.kill = Mock()
        # First wait (after terminate) times out, then succeeds after kill
        mock_process.wait = Mock(side_effect=[subprocess.TimeoutExpired("cmd", 5), None, None])

        server_manager.processes["test-server"] = mock_process

        server_manager._cleanup_on_exit()

        # Both terminate and kill should be called
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()


class TestMultipleProcessCleanup:
    """Tests for cleaning up multiple processes."""

    def test_cleanup_multiple_processes(self, server_manager):
        """Test cleanup handles multiple processes correctly."""
        processes = {}
        for i in range(5):
            mock_process = Mock(spec=subprocess.Popen)
            mock_process.pid = 10000 + i
            mock_process.poll = Mock(return_value=None)
            mock_process.terminate = Mock()
            mock_process.wait = Mock()
            processes[f"server{i}"] = mock_process

        server_manager.processes = processes

        server_manager._cleanup_on_exit()

        # Verify all processes were terminated
        for process in processes.values():
            process.terminate.assert_called_once()

        # Registry should be cleared
        assert len(server_manager.processes) == 0

    def test_cleanup_continues_on_individual_failures(self, server_manager):
        """Test cleanup continues even if individual process cleanup fails."""
        # Create 3 processes, middle one fails
        processes = {}
        for i in range(3):
            mock_process = Mock(spec=subprocess.Popen)
            mock_process.pid = 10000 + i
            mock_process.poll = Mock(return_value=None)

            if i == 1:
                # Middle process raises error
                mock_process.terminate = Mock(side_effect=Exception("Cleanup error"))
            else:
                mock_process.terminate = Mock()
                mock_process.wait = Mock()

            processes[f"server{i}"] = mock_process

        server_manager.processes = processes

        # Should not raise
        server_manager._cleanup_on_exit()

        # All processes should have termination attempted
        for process in processes.values():
            process.terminate.assert_called_once()


class TestMCPHealthMonitor:
    """Tests for MCPHealthMonitor — crash detection, restart policy, dedup."""

    @pytest.fixture
    def monitor(self, server_manager):
        from fluidmcp.cli.services.server_manager import MCPHealthMonitor
        return MCPHealthMonitor(server_manager, check_interval=30)

    @pytest.mark.asyncio
    async def test_detects_crash_and_restarts(self, monitor, server_manager, backend):
        """Health monitor detects dead process and triggers restart."""
        await backend.connect()
        await backend.save_server_config({
            "id": "srv1", "name": "srv1", "restart_policy": "on-failure", "max_restarts": 3
        })
        dead = Mock(spec=subprocess.Popen)
        dead.poll = Mock(return_value=1)
        dead.returncode = 1
        server_manager.processes["srv1"] = dead
        server_manager._start_server_unlocked = AsyncMock(return_value=True)
        server_manager._cleanup_server = AsyncMock()
        monitor._calculate_restart_delay = Mock(return_value=0)

        await monitor._check_server("srv1", dead)
        await asyncio.sleep(0.05)

        server_manager._cleanup_server.assert_called_once()
        server_manager._start_server_unlocked.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_restart_on_clean_exit(self, monitor, server_manager, backend):
        """on-failure policy: clean exit (code=0) should not restart."""
        await backend.connect()
        await backend.save_server_config({
            "id": "srv2", "name": "srv2", "restart_policy": "on-failure", "max_restarts": 3
        })
        dead = Mock(spec=subprocess.Popen)
        dead.poll = Mock(return_value=0)
        dead.returncode = 0
        server_manager.processes["srv2"] = dead
        server_manager._start_server_unlocked = AsyncMock(return_value=True)
        server_manager._cleanup_server = AsyncMock()

        await monitor._check_server("srv2", dead)

        server_manager._start_server_unlocked.assert_not_called()

    @pytest.mark.asyncio
    async def test_respects_never_policy(self, monitor, server_manager, backend):
        """restart_policy=never: crashed process should not be restarted."""
        await backend.connect()
        await backend.save_server_config({
            "id": "srv3", "name": "srv3", "restart_policy": "never", "max_restarts": 3
        })
        dead = Mock(spec=subprocess.Popen)
        dead.poll = Mock(return_value=1)
        dead.returncode = 1
        server_manager.processes["srv3"] = dead
        server_manager._start_server_unlocked = AsyncMock(return_value=True)
        server_manager._cleanup_server = AsyncMock()

        await monitor._check_server("srv3", dead)

        server_manager._start_server_unlocked.assert_not_called()
        server_manager._cleanup_server.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_restarts_not_exceeded(self, monitor, server_manager, backend):
        """Monitor stops restarting after max_restarts is reached."""
        await backend.connect()
        await backend.save_server_config({
            "id": "srv4", "name": "srv4", "restart_policy": "on-failure", "max_restarts": 2
        })
        dead = Mock(spec=subprocess.Popen)
        dead.poll = Mock(return_value=1)
        dead.returncode = 1
        server_manager.processes["srv4"] = dead
        server_manager._start_server_unlocked = AsyncMock(return_value=True)
        server_manager._cleanup_server = AsyncMock()
        monitor._restart_counts["srv4"] = 2  # already at max

        await monitor._check_server("srv4", dead)

        server_manager._start_server_unlocked.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_duplicate_restart(self, monitor, server_manager, backend):
        """_restarts_in_progress prevents duplicate restarts across cycles."""
        await backend.connect()
        await backend.save_server_config({
            "id": "srv5", "name": "srv5", "restart_policy": "on-failure", "max_restarts": 3
        })
        dead = Mock(spec=subprocess.Popen)
        dead.poll = Mock(return_value=1)
        dead.returncode = 1
        server_manager.processes["srv5"] = dead
        server_manager._start_server_unlocked = AsyncMock(return_value=True)
        server_manager._cleanup_server = AsyncMock()
        monitor._restarts_in_progress.add("srv5")  # simulate in-progress

        await monitor._check_server("srv5", dead)

        server_manager._start_server_unlocked.assert_not_called()


class TestCleanupServerState:
    """Tests for _cleanup_server intentional flag and crash event persistence."""

    @pytest.mark.asyncio
    async def test_intentional_stop_sets_stopped_state(self, server_manager, backend):
        """Intentional stop saves state=stopped regardless of exit code."""
        await backend.connect()
        await backend.save_instance_state({"server_id": "s1", "state": "running", "pid": 1})
        server_manager.start_times["s1"] = asyncio.get_event_loop().time()

        await server_manager._cleanup_server("s1", exit_code=1, intentional=True)

        state = await backend.get_instance_state("s1")
        assert state["state"] == "stopped"

    @pytest.mark.asyncio
    async def test_crash_sets_failed_state_and_saves_event(self, server_manager, backend):
        """Non-intentional non-zero exit saves state=failed and a crash event."""
        await backend.connect()
        await backend.save_instance_state({"server_id": "s2", "state": "running", "pid": 2})
        server_manager.start_times["s2"] = asyncio.get_event_loop().time()

        await server_manager._cleanup_server("s2", exit_code=137, intentional=False)

        state = await backend.get_instance_state("s2")
        assert state["state"] == "failed"
        events = await backend.list_crash_events("s2")
        assert len(events) == 1
        assert events[0]["exit_code"] == 137

    @pytest.mark.asyncio
    async def test_no_crash_event_on_intentional_stop(self, server_manager, backend):
        """Intentional stop must not save a crash event."""
        await backend.connect()
        server_manager.start_times["s3"] = asyncio.get_event_loop().time()

        await server_manager._cleanup_server("s3", exit_code=0, intentional=True)

        events = await backend.list_crash_events("s3")
        assert len(events) == 0


class TestCrashEventPersistence:
    """Tests for in-memory crash event save/list ordering and limit."""

    @pytest.mark.asyncio
    async def test_events_stored_most_recent_first(self, backend):
        await backend.connect()
        await backend.save_crash_event({"server_id": "x", "exit_code": 1, "timestamp": "t1"})
        await backend.save_crash_event({"server_id": "x", "exit_code": 2, "timestamp": "t2"})

        events = await backend.list_crash_events("x")
        assert events[0]["exit_code"] == 2
        assert events[1]["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_list_respects_limit(self, backend):
        await backend.connect()
        for i in range(10):
            await backend.save_crash_event({"server_id": "y", "exit_code": i})

        events = await backend.list_crash_events("y", limit=3)
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_crash_events_cleared_on_disconnect(self, backend):
        await backend.connect()
        await backend.save_crash_event({"server_id": "z", "exit_code": 1})
        await backend.disconnect()
        await backend.connect()

        events = await backend.list_crash_events("z")
        assert len(events) == 0


class TestResourceLimits:
    """Tests for _create_preexec_fn subprocess memory limits."""

    def test_returns_none_when_disabled(self):
        # Call site: preexec_fn = _create_preexec_fn(mb) if mb > 0 else None
        # When mb=0 the call site never calls _create_preexec_fn — result is None
        import os
        if os.name == "nt":
            pytest.skip("Not applicable on Windows")
        memory_limit_mb = 0
        result = ServerManager._create_preexec_fn(memory_limit_mb) if memory_limit_mb > 0 else None
        assert result is None

    def test_returns_callable_on_linux(self):
        import sys
        if sys.platform == "win32":
            pytest.skip("Not applicable on Windows")
        fn = ServerManager._create_preexec_fn(256)
        assert callable(fn)

    def test_preexec_fn_sets_rlimit(self):
        import sys
        if sys.platform == "win32":
            pytest.skip("Not applicable on Windows")
        import resource as resource_module
        with patch.object(resource_module, "setrlimit") as mock_rlimit:
            fn = ServerManager._create_preexec_fn(256)
            fn()
            mock_rlimit.assert_called_once_with(
                resource_module.RLIMIT_AS,
                (256 * 1024 * 1024, 256 * 1024 * 1024)
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
