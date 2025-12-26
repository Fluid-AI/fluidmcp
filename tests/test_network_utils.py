"""Unit tests for network_utils.py"""

import pytest
from unittest.mock import Mock, patch
import signal
from fluidai_mcp.services.network_utils import (
    is_port_in_use,
    get_pid_on_port,
    kill_process,
    kill_process_on_port,
    find_free_port
)


class TestIsPortInUse:
    """Unit tests for is_port_in_use function"""

    @patch('fluidai_mcp.services.network_utils.socket.socket')
    def test_returns_true_when_port_is_in_use(self, mock_socket):
        """Test returns True when port is occupied"""
        mock_sock = Mock()
        mock_sock.connect_ex.return_value = 0
        mock_socket.return_value.__enter__.return_value = mock_sock

        result = is_port_in_use(8080)

        assert result is True
        mock_sock.connect_ex.assert_called_once_with(('localhost', 8080))

    @patch('fluidai_mcp.services.network_utils.socket.socket')
    def test_returns_false_when_port_is_free(self, mock_socket):
        """Test returns False when port is free"""
        mock_sock = Mock()
        mock_sock.connect_ex.return_value = 1
        mock_socket.return_value.__enter__.return_value = mock_sock

        result = is_port_in_use(9999)

        assert result is False
        mock_sock.connect_ex.assert_called_once_with(('localhost', 9999))


class TestGetPidOnPort:
    """Unit tests for get_pid_on_port function"""

    @patch('fluidai_mcp.services.network_utils.psutil.net_connections')
    def test_returns_pid_when_process_found(self, mock_net_connections):
        """Test returns PID when process is found on port"""
        mock_conn = Mock()
        mock_conn.status = 'LISTEN'
        mock_conn.laddr.port = 8080
        mock_conn.pid = 12345
        mock_net_connections.return_value = [mock_conn]

        result = get_pid_on_port(8080)

        assert result == 12345

    @patch('fluidai_mcp.services.network_utils.psutil.net_connections')
    def test_returns_none_when_no_process_on_port(self, mock_net_connections):
        """Test returns None when no process found"""
        mock_net_connections.return_value = []

        result = get_pid_on_port(9999)

        assert result is None

    @patch('fluidai_mcp.services.network_utils.psutil.net_connections')
    def test_only_matches_listen_status(self, mock_net_connections):
        """Test ignores connections not in LISTEN status"""
        mock_conn = Mock()
        mock_conn.status = 'ESTABLISHED'
        mock_conn.laddr.port = 8080
        mock_conn.pid = 12345
        mock_net_connections.return_value = [mock_conn]

        result = get_pid_on_port(8080)

        assert result is None

    @patch('fluidai_mcp.services.network_utils.psutil.net_connections')
    def test_matches_correct_port_number(self, mock_net_connections):
        """Test returns PID only for matching port"""
        mock_conn1 = Mock()
        mock_conn1.status = 'LISTEN'
        mock_conn1.laddr.port = 8080
        mock_conn1.pid = 11111

        mock_conn2 = Mock()
        mock_conn2.status = 'LISTEN'
        mock_conn2.laddr.port = 8081
        mock_conn2.pid = 22222

        mock_net_connections.return_value = [mock_conn1, mock_conn2]

        result = get_pid_on_port(8081)

        assert result == 22222


class TestKillProcess:
    """Unit tests for kill_process function"""

    @patch('fluidai_mcp.services.network_utils.os.kill')
    def test_calls_os_kill_with_sigterm(self, mock_kill):
        """Test calls os.kill with SIGTERM signal"""
        kill_process(12345)

        mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    @patch('fluidai_mcp.services.network_utils.os.kill')
    def test_handles_exception_when_process_not_found(self, mock_kill):
        """Test handles ProcessLookupError gracefully"""
        mock_kill.side_effect = ProcessLookupError("Process not found")

        kill_process(99999)

        mock_kill.assert_called_once_with(99999, signal.SIGTERM)

    @patch('fluidai_mcp.services.network_utils.os.kill')
    def test_handles_permission_error(self, mock_kill):
        """Test handles PermissionError gracefully"""
        mock_kill.side_effect = PermissionError("Permission denied")

        kill_process(1)

        mock_kill.assert_called_once_with(1, signal.SIGTERM)


class TestKillProcessOnPort:
    """Unit tests for kill_process_on_port function"""

    @patch('fluidai_mcp.services.network_utils.kill_process')
    @patch('fluidai_mcp.services.network_utils.get_pid_on_port')
    def test_kills_process_and_returns_true_when_found(self, mock_get_pid, mock_kill):
        """Test kills process and returns True when found"""
        mock_get_pid.return_value = 12345

        result = kill_process_on_port(8080)

        assert result is True
        mock_get_pid.assert_called_once_with(8080)
        mock_kill.assert_called_once_with(12345)

    @patch('fluidai_mcp.services.network_utils.kill_process')
    @patch('fluidai_mcp.services.network_utils.get_pid_on_port')
    def test_returns_false_when_no_process_on_port(self, mock_get_pid, mock_kill):
        """Test returns False when no process found"""
        mock_get_pid.return_value = None

        result = kill_process_on_port(9999)

        assert result is False
        mock_get_pid.assert_called_once_with(9999)
        mock_kill.assert_not_called()


class TestFindFreePort:
    """Unit tests for find_free_port function"""

    @patch('fluidai_mcp.services.network_utils.socket.socket')
    def test_finds_first_available_port_in_range(self, mock_socket):
        """Test finds first available port"""
        mock_sock = Mock()
        mock_socket.return_value.__enter__.return_value = mock_sock
        mock_sock.bind.side_effect = [OSError, OSError, None]

        result = find_free_port(8100, 8105)

        assert result == 8102

    @patch('fluidai_mcp.services.network_utils.socket.socket')
    def test_uses_default_range_when_not_specified(self, mock_socket):
        """Test uses default range 8100-9000"""
        mock_sock = Mock()
        mock_socket.return_value.__enter__.return_value = mock_sock
        mock_sock.bind.return_value = None

        result = find_free_port()

        assert 8100 <= result < 9000

    @patch('fluidai_mcp.services.network_utils.socket.socket')
    def test_skips_taken_ports(self, mock_socket):
        """Test skips ports in taken_ports set"""
        mock_sock = Mock()
        mock_socket.return_value.__enter__.return_value = mock_sock
        mock_sock.bind.return_value = None

        result = find_free_port(8100, 8105, taken_ports={8100, 8101, 8102})

        assert result == 8103

    @patch('fluidai_mcp.services.network_utils.socket.socket')
    def test_raises_runtime_error_when_no_ports_available(self, mock_socket):
        """Test raises RuntimeError when all ports occupied"""
        mock_sock = Mock()
        mock_socket.return_value.__enter__.return_value = mock_sock
        mock_sock.bind.side_effect = OSError

        with pytest.raises(RuntimeError, match="No free ports available"):
            find_free_port(8100, 8102)

    @patch('fluidai_mcp.services.network_utils.socket.socket')
    def test_continues_on_oserror_until_free_port(self, mock_socket):
        """Test continues trying ports after OSError"""
        mock_sock = Mock()
        mock_socket.return_value.__enter__.return_value = mock_sock
        mock_sock.bind.side_effect = [OSError, OSError, OSError, None]

        result = find_free_port(8100, 8110)

        assert result == 8103

    def test_find_free_port_returns_valid_tcp_port(self):
        """Returned port should be within valid TCP port range"""
        port = find_free_port(1024, 65535)
        assert isinstance(port, int)
        assert 1 <= port <= 65535

