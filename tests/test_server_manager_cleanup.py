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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
