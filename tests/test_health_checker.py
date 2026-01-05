"""Unit tests for HealthChecker class."""

import pytest
import psutil
from unittest.mock import Mock, patch, MagicMock
from fluidai_mcp.services.health_checker import HealthChecker


class TestHealthChecker:
    """Test suite for HealthChecker class."""

    @pytest.fixture
    def health_checker(self):
        """Create a HealthChecker instance for testing."""
        return HealthChecker(http_timeout=5)

    def test_init(self, health_checker):
        """Test HealthChecker initialization."""
        assert health_checker.http_timeout == 5

    # Process Health Check Tests

    @patch('psutil.Process')
    def test_check_process_alive_success(self, mock_process_class, health_checker):
        """Test successful process health check."""
        mock_process = Mock()
        mock_process.is_running.return_value = True
        mock_process.status.return_value = psutil.STATUS_RUNNING
        mock_process_class.return_value = mock_process

        is_alive, error = health_checker.check_process_alive(1234)

        assert is_alive is True
        assert error is None
        mock_process_class.assert_called_once_with(1234)

    @patch('psutil.Process')
    def test_check_process_alive_not_running(self, mock_process_class, health_checker):
        """Test process health check when process is not running."""
        mock_process = Mock()
        mock_process.is_running.return_value = False
        mock_process_class.return_value = mock_process

        is_alive, error = health_checker.check_process_alive(1234)

        assert is_alive is False
        assert "Process 1234 is not running" in error

    @patch('psutil.Process')
    def test_check_process_alive_zombie(self, mock_process_class, health_checker):
        """Test process health check when process is a zombie."""
        mock_process = Mock()
        mock_process.is_running.return_value = True
        mock_process.status.return_value = psutil.STATUS_ZOMBIE
        mock_process_class.return_value = mock_process

        is_alive, error = health_checker.check_process_alive(1234)

        assert is_alive is False
        assert "zombie" in error.lower()

    @patch('psutil.Process')
    def test_check_process_alive_dead(self, mock_process_class, health_checker):
        """Test process health check when process is dead."""
        mock_process = Mock()
        mock_process.is_running.return_value = True
        mock_process.status.return_value = psutil.STATUS_DEAD
        mock_process_class.return_value = mock_process

        is_alive, error = health_checker.check_process_alive(1234)

        assert is_alive is False
        assert "dead" in error.lower()

    @patch('psutil.Process')
    def test_check_process_alive_no_such_process(self, mock_process_class, health_checker):
        """Test process health check when process doesn't exist."""
        mock_process_class.side_effect = psutil.NoSuchProcess(1234)

        is_alive, error = health_checker.check_process_alive(1234)

        assert is_alive is False
        assert "does not exist" in error

    @patch('psutil.Process')
    def test_check_process_alive_access_denied(self, mock_process_class, health_checker):
        """Test process health check when access is denied."""
        mock_process_class.side_effect = psutil.AccessDenied(1234)

        is_alive, error = health_checker.check_process_alive(1234)

        # Should assume alive when access denied
        assert is_alive is True
        assert error is None

    @patch('psutil.Process')
    def test_check_process_alive_exception(self, mock_process_class, health_checker):
        """Test process health check with unexpected exception."""
        mock_process_class.side_effect = Exception("Unexpected error")

        is_alive, error = health_checker.check_process_alive(1234)

        assert is_alive is False
        assert "Error checking process 1234" in error

    # HTTP Health Check Tests

    @patch('requests.get')
    def test_check_http_health_success_get(self, mock_get, health_checker):
        """Test successful HTTP health check with GET."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        is_healthy, error = health_checker.check_http_health("localhost", 8080, "/health", "GET")

        assert is_healthy is True
        assert error is None
        mock_get.assert_called_once_with("http://localhost:8080/health", timeout=5)

    @patch('requests.post')
    def test_check_http_health_success_post(self, mock_post, health_checker):
        """Test successful HTTP health check with POST."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        is_healthy, error = health_checker.check_http_health("localhost", 8080, "/health", "POST")

        assert is_healthy is True
        assert error is None
        mock_post.assert_called_once_with("http://localhost:8080/health", timeout=5)

    @patch('requests.get')
    def test_check_http_health_3xx_redirect(self, mock_get, health_checker):
        """Test HTTP health check with 3xx redirect (should be healthy)."""
        mock_response = Mock()
        mock_response.status_code = 301
        mock_get.return_value = mock_response

        is_healthy, error = health_checker.check_http_health("localhost", 8080)

        assert is_healthy is True
        assert error is None

    @patch('requests.get')
    def test_check_http_health_4xx_error(self, mock_get, health_checker):
        """Test HTTP health check with 4xx error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        is_healthy, error = health_checker.check_http_health("localhost", 8080)

        assert is_healthy is False
        assert "HTTP 404" in error

    @patch('requests.get')
    def test_check_http_health_5xx_error(self, mock_get, health_checker):
        """Test HTTP health check with 5xx error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        is_healthy, error = health_checker.check_http_health("localhost", 8080)

        assert is_healthy is False
        assert "HTTP 500" in error

    @patch('requests.get')
    def test_check_http_health_connection_error(self, mock_get, health_checker):
        """Test HTTP health check with connection error."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        is_healthy, error = health_checker.check_http_health("localhost", 8080)

        assert is_healthy is False
        assert "Connection refused" in error

    @patch('requests.get')
    def test_check_http_health_timeout(self, mock_get, health_checker):
        """Test HTTP health check with timeout."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        is_healthy, error = health_checker.check_http_health("localhost", 8080)

        assert is_healthy is False
        assert "Timeout" in error

    @patch('requests.get')
    def test_check_http_health_generic_exception(self, mock_get, health_checker):
        """Test HTTP health check with generic exception."""
        mock_get.side_effect = Exception("Network error")

        is_healthy, error = health_checker.check_http_health("localhost", 8080)

        assert is_healthy is False
        assert "Error checking" in error

    # MCP JSON-RPC Health Check Tests

    @patch('requests.post')
    def test_check_mcp_jsonrpc_health_success(self, mock_post, health_checker):
        """Test successful MCP JSON-RPC health check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "health_check_123",
            "result": {"tools": []}
        }
        mock_post.return_value = mock_response

        is_healthy, error = health_checker.check_mcp_jsonrpc_health("localhost", 8099, "test-server")

        assert is_healthy is True
        assert error is None

    @patch('requests.post')
    def test_check_mcp_jsonrpc_health_json_rpc_error(self, mock_post, health_checker):
        """Test MCP JSON-RPC health check with JSON-RPC error."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "health_check_123",
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        }
        mock_post.return_value = mock_response

        is_healthy, error = health_checker.check_mcp_jsonrpc_health("localhost", 8099, "test-server")

        assert is_healthy is False
        assert "JSON-RPC error" in error
        assert "Method not found" in error

    @patch('requests.post')
    def test_check_mcp_jsonrpc_health_json_rpc_error_no_message(self, mock_post, health_checker):
        """Test MCP JSON-RPC health check with JSON-RPC error without message key."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "health_check_123",
            "error": {
                "code": -32601
            }
        }
        mock_post.return_value = mock_response

        is_healthy, error = health_checker.check_mcp_jsonrpc_health("localhost", 8099, "test-server")

        assert is_healthy is False
        assert "JSON-RPC error" in error

    @patch('requests.post')
    def test_check_mcp_jsonrpc_health_http_error(self, mock_post, health_checker):
        """Test MCP JSON-RPC health check with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        is_healthy, error = health_checker.check_mcp_jsonrpc_health("localhost", 8099, "test-server")

        assert is_healthy is False
        assert "HTTP 500" in error

    @patch('requests.post')
    def test_check_mcp_jsonrpc_health_connection_error(self, mock_post, health_checker):
        """Test MCP JSON-RPC health check with connection error."""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        is_healthy, error = health_checker.check_mcp_jsonrpc_health("localhost", 8099, "test-server")

        assert is_healthy is False
        assert "Connection refused" in error

    @patch('requests.post')
    def test_check_mcp_jsonrpc_health_timeout(self, mock_post, health_checker):
        """Test MCP JSON-RPC health check with timeout."""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        is_healthy, error = health_checker.check_mcp_jsonrpc_health("localhost", 8099, "test-server")

        assert is_healthy is False
        assert "Timeout" in error

    @patch('requests.post')
    def test_check_mcp_jsonrpc_health_invalid_json(self, mock_post, health_checker):
        """Test MCP JSON-RPC health check with invalid JSON response."""
        import json as json_module
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json_module.JSONDecodeError("error", "doc", 0)
        mock_post.return_value = mock_response

        is_healthy, error = health_checker.check_mcp_jsonrpc_health("localhost", 8099, "test-server")

        assert is_healthy is False
        assert "Invalid JSON response" in error

    # Comprehensive Server Health Check Tests

    @patch.object(HealthChecker, 'check_mcp_jsonrpc_health')
    @patch.object(HealthChecker, 'check_process_alive')
    def test_check_server_health_success_with_http(
        self, mock_process_check, mock_http_check, health_checker
    ):
        """Test successful comprehensive server health check with HTTP."""
        mock_process_check.return_value = (True, None)
        mock_http_check.return_value = (True, None)

        is_healthy, error = health_checker.check_server_health(
            1234, "localhost", 8099, "test-server", use_http_check=True
        )

        assert is_healthy is True
        assert error is None
        mock_process_check.assert_called_once_with(1234)
        mock_http_check.assert_called_once_with("localhost", 8099, "test-server")

    @patch.object(HealthChecker, 'check_process_alive')
    def test_check_server_health_process_failed(self, mock_process_check, health_checker):
        """Test comprehensive server health check when process check fails."""
        mock_process_check.return_value = (False, "Process not running")

        is_healthy, error = health_checker.check_server_health(
            1234, "localhost", 8099, "test-server", use_http_check=True
        )

        assert is_healthy is False
        assert error == "Process not running"

    @patch.object(HealthChecker, 'check_mcp_jsonrpc_health')
    @patch.object(HealthChecker, 'check_process_alive')
    def test_check_server_health_http_failed(
        self, mock_process_check, mock_http_check, health_checker
    ):
        """Test comprehensive server health check when HTTP check fails."""
        mock_process_check.return_value = (True, None)
        mock_http_check.return_value = (False, "Connection refused")

        is_healthy, error = health_checker.check_server_health(
            1234, "localhost", 8099, "test-server", use_http_check=True
        )

        assert is_healthy is False
        assert error == "Connection refused"

    @patch.object(HealthChecker, 'check_process_alive')
    def test_check_server_health_no_http_check(self, mock_process_check, health_checker):
        """Test comprehensive server health check without HTTP check."""
        mock_process_check.return_value = (True, None)

        is_healthy, error = health_checker.check_server_health(
            1234, "localhost", 8099, "test-server", use_http_check=False
        )

        assert is_healthy is True
        assert error is None
        mock_process_check.assert_called_once_with(1234)
