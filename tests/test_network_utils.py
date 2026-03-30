"""Unit tests for network_utils.py

Test Organization:
    - Port availability detection: is_port_in_use() with occupied and free ports
    - Port finding: find_free_port() with various ranges and constraints
    - Port range validation: Valid port numbers (1-65535) and invalid ranges
    - PID detection: get_pid_on_port() for processes listening on ports
    - Process management: kill_process_on_port() for terminating port-using processes
    - Edge cases: Port exhaustion, boundary ports, taken_ports parameter
    - Socket operations: Actual socket binding to verify behavior

Note on Testing Strategy:
    These tests use real socket operations to verify network utility functions.
    Tests create actual listening sockets to test port detection, which means:

    1. Tests are integration-level (not pure unit tests)
    2. Tests may be affected by system state (ports in use)
    3. Tests use ephemeral ports and cleanup to avoid conflicts
    4. Helper servers are spawned in subprocesses for realistic testing

    Port Ranges:
    - Valid ports: 1-65535 (0 is reserved)
    - Privileged ports: 1-1023 (may require root on Unix)
    - Registered ports: 1024-49151
    - Dynamic/ephemeral: 49152-65535

    Tests use high port numbers (50000+) to avoid conflicts with system services.

Subprocess Management:
    Tests that spawn servers use subprocesses with proper cleanup in finally blocks
    to ensure server processes are terminated even if tests fail.
"""

import socket
import pytest
import time
import subprocess
import sys
import os
import select
from fluidmcp.cli.services.network_utils import (
    is_port_in_use,
    find_free_port,
    get_pid_on_port,
    kill_process_on_port,
)


# Test configuration constants
BASE_TEST_PORT = 50000  # Base port for all test operations
TEST_TIMEOUT = 2.0      # Default timeout for wait conditions (adjustable for slow CI)


def wait_for_condition(condition_func, timeout=TEST_TIMEOUT, interval=0.1):
    """Helper function to poll until a condition is met.

    Args:
        condition_func: Callable that returns True when condition is met
        timeout: Maximum time to wait in seconds (default: TEST_TIMEOUT)
        interval: Time to wait between checks in seconds (default: 0.1)

    Returns:
        bool: True if condition was met, False if timeout occurred

    Example:
        # Wait for port to be in use
        success = wait_for_condition(lambda: is_port_in_use(port))

        # Wait for PID to be available
        success = wait_for_condition(lambda: get_pid_on_port(port) is not None)
    """
    start_time = time.perf_counter()
    while True:
        if condition_func():
            return True
        if time.perf_counter() - start_time >= timeout:
            return False
        time.sleep(interval)


def start_test_server(port, duration=3):
    """Helper function to start a test TCP server subprocess.

    Args:
        port: Port number to bind the server to
        duration: How long the server should stay alive (default: 3 seconds - reduced for CI)

    Returns:
        subprocess.Popen: The subprocess running the server

    Example:
        proc = start_test_server(52003, duration=2)
        try:
            line = proc.stdout.readline()
            assert 'READY' in line
            # ... test code ...
        finally:
            proc.terminate()
            proc.wait(timeout=2)
    """
    server_code = f"""
import socket
import time
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('', {port}))
s.listen(1)
print('READY', flush=True)
time.sleep({duration})
s.close()
"""
    return subprocess.Popen(
        [sys.executable, '-c', server_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


def can_bind_to_port(port):
    """Helper function to check if a port can be bound to.

    Args:
        port: Port number to test

    Returns:
        bool: True if port can be bound, False otherwise

    Example:
        # Wait until port becomes available
        assert wait_for_condition(lambda: can_bind_to_port(port))
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_socket:
            test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_socket.bind(('', port))
        return True
    except OSError:
        return False


def wait_for_server_ready(proc, timeout=TEST_TIMEOUT):
    """Wait for test server subprocess to be ready.

    Args:
        proc: subprocess.Popen instance
        timeout: Maximum time to wait in seconds

    Returns:
        bool: True if server is ready

    Raises:
        AssertionError: If server process terminates early or does not become
            ready within the specified timeout
    """
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < timeout:
        # Check if process is still running
        if proc.poll() is not None:
            stderr_output = proc.stderr.read() if proc.stderr else ""
            pytest.fail(f"Test server process terminated unexpectedly: {stderr_output}")

        # Try to read a line with a short timeout
        if select.select([proc.stdout], [], [], 0.1)[0]:
            line = proc.stdout.readline()
            if 'READY' in line:
                return True

    pytest.fail(f"Test server did not become ready within {timeout} seconds")


class TestIsPortInUse:
    """Integration tests for is_port_in_use function"""

    def test_free_port_returns_false(self):
        """Test that is_port_in_use returns False for an unused port"""
        # Use a high port number to avoid conflicts (ephemeral range)
        port = 54321

        # Verify the port is actually free before testing
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
            except OSError:
                pytest.skip(f"Port {port} is already in use on this system")

        # Now test that is_port_in_use returns False
        assert is_port_in_use(port) is False

    def test_occupied_port_returns_true(self):
        """Test that is_port_in_use returns True for a port with a listening socket"""
        # Use a high port number to avoid conflicts
        port = 54322

        # Create a listening socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('', port))
            server_socket.listen(1)

            # Port should now be in use
            assert is_port_in_use(port) is True

    def test_port_becomes_free_after_socket_close(self):
        """Test that a port becomes free after closing the socket"""
        port = 54323

        # Create and close a socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('', port))
            server_socket.listen(1)

            # Port is in use
            assert is_port_in_use(port) is True

        # Wait for OS to release the port
        success = wait_for_condition(lambda: not is_port_in_use(port))
        assert success, "Port was not released within timeout"

    def test_multiple_checks_on_same_port(self):
        """Test that is_port_in_use can be called multiple times on the same port"""
        port = 54327  # Use a port close to the working test

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Bind to all interfaces ('') so is_port_in_use can connect via localhost
            server_socket.bind(('', port))
            # Use higher backlog to allow multiple connection attempts
            server_socket.listen(10)

            # Wait for socket to be ready
            success = wait_for_condition(lambda: is_port_in_use(port))
            assert success, "Port was not detected as in use within timeout"

            # Multiple checks should all return True
            assert is_port_in_use(port) is True
            assert is_port_in_use(port) is True
            assert is_port_in_use(port) is True

    def test_different_ports(self):
        """Test checking multiple different ports"""
        port1 = 54335
        port2 = 54336

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Bind to all interfaces ('') so is_port_in_use can connect via localhost
            server_socket.bind(('', port1))
            server_socket.listen(1)

            # port1 is in use, port2 is free
            assert is_port_in_use(port1) is True
            assert is_port_in_use(port2) is False


class TestFindFreePort:
    """Integration tests for find_free_port function"""

    def test_finds_available_port_in_range(self):
        """Test that find_free_port returns a port within the specified range"""
        start = 50000
        end = 50100

        port = find_free_port(start, end)

        assert isinstance(port, int)
        assert start <= port < end

    def test_returned_port_is_actually_free(self):
        """Test that the returned port can actually be bound to"""
        port = find_free_port(50100, 50200)

        # Try to bind to the returned port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', port))  # Should not raise an exception

    def test_skips_taken_ports_in_taken_ports_set(self):
        """Test that find_free_port skips ports in the taken_ports set"""
        start = 50200
        end = 50210

        # Mark ports 50200-50205 as taken
        taken_ports = {50200, 50201, 50202, 50203, 50204, 50205}

        port = find_free_port(start, end, taken_ports)

        # Should return a port NOT in taken_ports
        assert port not in taken_ports
        assert start <= port < end

    def test_skips_actually_occupied_ports(self):
        """Test that find_free_port skips ports that are actually in use"""
        start = 50210
        end = 50220

        # Occupy port 50210
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('', start))
            server_socket.listen(1)

            # find_free_port should skip 50210 and return a different port
            port = find_free_port(start, end)

            assert port != start  # Should not return the occupied port
            assert start < port < end

    def test_default_range(self):
        """Test find_free_port with default range (8100-9000)"""
        port = find_free_port()

        assert isinstance(port, int)
        assert 8100 <= port < 9000

    def test_small_range(self):
        """Test find_free_port with a small range"""
        start = 50300
        end = 50305  # Only 5 ports

        port = find_free_port(start, end)

        assert start <= port < end

    def test_single_port_range(self):
        """Test find_free_port with a range containing only one port"""
        start = 50400
        end = 50401  # Only port 50400

        port = find_free_port(start, end)

        assert port == start

    def test_raises_error_when_all_ports_taken(self):
        """Test that RuntimeError is raised when no ports are available"""
        start = 50500
        end = 50502  # Ports 50500, 50501

        # Mark all ports as taken
        taken_ports = {50500, 50501}

        with pytest.raises(RuntimeError, match="No free ports available in the range"):
            find_free_port(start, end, taken_ports)

    def test_raises_error_when_range_exhausted(self):
        """Test RuntimeError when all ports in range are actually occupied"""
        start = 50600
        end = 50602  # Only 2 ports: 50600, 50601

        # Occupy both ports
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket1, \
             socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket2:
            socket1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            socket2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            socket1.bind(('', 50600))
            socket1.listen(1)
            socket2.bind(('', 50601))
            socket2.listen(1)

            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="No free ports available in the range"):
                find_free_port(start, end)

    def test_empty_taken_ports_set(self):
        """Test find_free_port with an empty taken_ports set"""
        port = find_free_port(50700, 50710, set())

        assert 50700 <= port < 50710

    def test_none_taken_ports(self):
        """Test find_free_port with None for taken_ports (default behavior)"""
        port = find_free_port(50710, 50720, None)

        assert 50710 <= port < 50720

    def test_large_range(self):
        """Test find_free_port with a large range"""
        start = 50800
        end = 51800  # 1000 ports

        port = find_free_port(start, end)

        assert start <= port < end

    def test_high_port_numbers(self):
        """Test find_free_port with high port numbers (ephemeral range)"""
        start = 60000
        end = 60100

        port = find_free_port(start, end)

        assert 60000 <= port < 60100

    def test_sequential_calls_return_different_ports(self):
        """Test that sequential calls return different available ports"""
        start = 51000
        end = 51100

        taken_ports = set()

        # Find 5 ports sequentially
        port1 = find_free_port(start, end, taken_ports)
        taken_ports.add(port1)

        port2 = find_free_port(start, end, taken_ports)
        taken_ports.add(port2)

        port3 = find_free_port(start, end, taken_ports)
        taken_ports.add(port3)

        # All ports should be different
        assert len({port1, port2, port3}) == 3


class TestPortRangeValidation:
    """Test valid and invalid port numbers"""

    @pytest.mark.parametrize("port,expected", [
        (1, True),      # Minimum valid port
        (65535, True),  # Maximum valid port
        (0, False),     # Special port (OS-assigned)
        (-1, False),    # Negative port
        (65536, False), # Above maximum
    ])
    def test_port_validity(self, port, expected):
        """Test port number validity (1-65535 range)"""
        assert (1 <= port <= 65535) == expected

    @pytest.mark.parametrize("port", [1, 22, 80, 443, 1023])
    def test_privileged_port_range(self, port):
        """Test identification of privileged ports (1-1023)"""
        # These ports typically require root/admin privileges
        assert 1 <= port <= 1023

    @pytest.mark.parametrize("port", [1024, 3000, 8080, 49151])
    def test_registered_port_range(self, port):
        """Test identification of registered ports (1024-49151)"""
        assert 1024 <= port <= 49151

    @pytest.mark.parametrize("port", [49152, 50000, 60000, 65535])
    def test_ephemeral_port_range(self, port):
        """Test identification of ephemeral/dynamic ports (49152-65535)"""
        assert 49152 <= port <= 65535


class TestGetPidOnPort:
    """Integration tests for get_pid_on_port function"""

    def test_returns_none_for_unused_port(self):
        """Test that get_pid_on_port returns None for a free port"""
        port = 52000

        # Ensure port is free
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
            except OSError:
                pytest.skip(f"Port {port} is already in use")

        pid = get_pid_on_port(port)
        assert pid is None

    def test_returns_integer_pid_for_occupied_port(self):
        """Test that get_pid_on_port returns an integer PID for an occupied port"""
        port = 52001

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('', port))
            server_socket.listen(1)

            try:
                pid = get_pid_on_port(port)
            except PermissionError:
                pytest.skip("Insufficient privileges to access network connections (psutil requires elevated permissions)")

            # Should return an integer PID (our own process in this case)
            assert isinstance(pid, int)
            assert pid > 0

    def test_returns_current_process_pid(self):
        """Test that get_pid_on_port returns the current process PID when we bind a port"""
        port = 52002
        current_pid = os.getpid()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('', port))
            server_socket.listen(1)

            # Wait for socket to be registered (with permission handling)
            try:
                success = wait_for_condition(lambda: get_pid_on_port(port) == current_pid)
            except PermissionError:
                pytest.skip("Insufficient privileges to access network connections (psutil requires elevated permissions)")

            assert success, "PID was not registered within timeout"

            pid = get_pid_on_port(port)
            # Should return our current process PID
            assert pid == current_pid

    def test_with_subprocess_server(self):
        """Test get_pid_on_port with an actual subprocess listening on a port"""
        port = BASE_TEST_PORT + 2003

        # Start subprocess server
        proc = start_test_server(port, duration=2)

        try:
            # Wait for server to be ready
            wait_for_server_ready(proc)

            # Poll until port is registered (with permission handling)
            try:
                success = wait_for_condition(lambda: get_pid_on_port(port) is not None)
            except PermissionError:
                pytest.skip("Insufficient privileges to access network connections (psutil requires elevated permissions)")

            assert success, "Port was not registered within timeout"

            pid = get_pid_on_port(port)
            # Should return the subprocess PID
            assert pid == proc.pid
        finally:
            # Clean up subprocess
            proc.terminate()
            proc.wait(timeout=2)


class TestKillProcessOnPort:
    """Integration tests for kill_process_on_port function"""

    def test_returns_false_for_unused_port(self):
        """Test that kill_process_on_port returns False for a free port"""
        port = 53000

        # Ensure port is free
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
            except OSError:
                pytest.skip(f"Port {port} is already in use")

        result = kill_process_on_port(port)
        assert result is False

    def test_returns_boolean(self):
        """Test that kill_process_on_port returns a boolean value"""
        port = 53001

        result = kill_process_on_port(port)
        assert isinstance(result, bool)

    def test_kills_subprocess_on_port(self):
        """Test that kill_process_on_port actually terminates a process listening on a port

        Note: This test uses SIGTERM which has platform-specific behavior.
        On Windows, signal handling is limited and may behave differently.
        """
        port = BASE_TEST_PORT + 3002

        # Start subprocess server
        proc = start_test_server(port)

        try:
            # Wait for server to be ready
            wait_for_server_ready(proc)

            # Poll until port is in use
            assert wait_for_condition(lambda: is_port_in_use(port))

            # Kill the process on the port (with permission/platform handling)
            try:
                result = kill_process_on_port(port)
            except PermissionError:
                pytest.skip("Insufficient privileges to kill processes (requires elevated permissions)")
            except OSError as e:
                # Windows may raise OSError for unsupported signals
                pytest.skip(f"Platform does not support process termination: {e}")

            # Should return True (a process was killed)
            assert result is True

            # Poll until process terminates
            assert wait_for_condition(lambda: proc.poll() is not None)

            # Poll until port is free
            assert wait_for_condition(lambda: not is_port_in_use(port))
        finally:
            # Ensure cleanup if test fails
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=2)

    def test_port_becomes_available_after_kill(self):
        """Test that a port becomes available after killing the process using it

        Note: This test uses SIGTERM which has platform-specific behavior.
        On Windows, signal handling is limited and may behave differently.
        """
        port = BASE_TEST_PORT + 3003

        # Start subprocess server
        proc = start_test_server(port)

        try:
            # Wait for server to be ready
            wait_for_server_ready(proc)

            # Poll until port is in use
            assert wait_for_condition(lambda: is_port_in_use(port))

            # Kill process and verify return value (with permission/platform handling)
            try:
                result = kill_process_on_port(port)
            except PermissionError:
                pytest.skip("Insufficient privileges to kill processes (requires elevated permissions)")
            except OSError as e:
                # Windows may raise OSError for unsupported signals
                pytest.skip(f"Platform does not support process termination: {e}")

            assert result is True

            # Poll until port is available for binding
            assert wait_for_condition(lambda: can_bind_to_port(port))

            # Port should now be available for binding
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('', port))  # Should succeed without error
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=2)


class TestEdgeCases:
    """Edge case tests for network utilities"""

    def test_concurrent_port_checks(self):
        """Test that is_port_in_use works correctly with concurrent checks"""
        port = 56100

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('', port))
            # Use higher backlog to allow multiple connection attempts
            server_socket.listen(10)

            # Wait for socket to be ready
            success = wait_for_condition(lambda: is_port_in_use(port))
            assert success, "Port was not detected as in use within timeout"

            # Simulate concurrent checks
            results = []
            for _ in range(5):  # Reduced from 10 to 5 for faster tests
                results.append(is_port_in_use(port))

            # All checks should return True
            assert all(results)
            assert len(results) == 5

    def test_find_free_port_with_mostly_taken_ports(self):
        """Test find_free_port when most ports in range are taken"""
        start = 54100
        end = 54110  # 10 ports total

        # Mark 9 out of 10 ports as taken
        taken_ports = {54100, 54101, 54102, 54103, 54104, 54105, 54106, 54107, 54108}
        # Port 54109 is free

        port = find_free_port(start, end, taken_ports)

        # Should find the one free port
        assert port == 54109

    def test_port_reuse_after_close(self):
        """Test that a port can be reused after closing the socket"""
        port = 54200

        # First usage
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as first_socket:
            first_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            first_socket.bind(('', port))
            first_socket.listen(1)
            assert is_port_in_use(port) is True

        # Wait for OS to release the port
        success = wait_for_condition(lambda: not is_port_in_use(port))
        assert success, "Port was not released within timeout"

        # Second usage on the same port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as second_socket:
            second_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            second_socket.bind(('', port))
            second_socket.listen(1)
            assert is_port_in_use(port) is True

    def test_find_free_port_boundary_cases(self):
        """Test find_free_port at range boundaries"""
        # Test start of range
        port = find_free_port(55000, 55100)
        assert 55000 <= port < 55100

        # Test with start = end - 1 (single port range)
        port = find_free_port(55200, 55201)
        assert port == 55200

    def test_is_port_in_use_with_multiple_sockets(self):
        """Test is_port_in_use when multiple sockets exist but only one binds to port"""
        port = 55300

        # Create multiple sockets but only bind one to the port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unused_socket1, \
             socket.socket(socket.AF_INET, socket.SOCK_STREAM) as bound_socket, \
             socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unused_socket2:
            bound_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            bound_socket.bind(('', port))
            bound_socket.listen(1)

            # Port should be detected as in use
            assert is_port_in_use(port) is True
