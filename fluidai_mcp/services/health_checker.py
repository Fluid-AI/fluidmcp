"""Health checking utilities for MCP server monitoring."""

import json
import psutil
import requests
from typing import Optional, Tuple
from datetime import datetime
from loguru import logger


class HealthChecker:
    """Performs health checks on MCP servers."""

    def __init__(self, http_timeout: int = 5):
        """Initialize health checker.

        Args:
            http_timeout: Timeout in seconds for HTTP health checks
        """
        self.http_timeout = http_timeout

    def check_process_alive(self, pid: int) -> Tuple[bool, Optional[str]]:
        """Check if a process is still running.

        Args:
            pid: Process ID to check

        Returns:
            Tuple of (is_alive, error_message)
        """
        try:
            process = psutil.Process(pid)

            # Check if process exists and is running
            if not process.is_running():
                return False, f"Process {pid} is not running"

            # Check process status
            status = process.status()
            if status == psutil.STATUS_ZOMBIE:
                return False, f"Process {pid} is a zombie"
            elif status == psutil.STATUS_DEAD:
                return False, f"Process {pid} is dead"

            return True, None

        except psutil.NoSuchProcess:
            return False, f"Process {pid} does not exist"
        except psutil.AccessDenied:
            # Process exists but we can't access it - assume it's alive
            logger.warning(f"Access denied checking process {pid}, assuming alive")
            return True, None
        except Exception as e:
            return False, f"Error checking process {pid}: {e}"

    def check_http_health(
        self,
        host: str,
        port: int,
        path: str = "/health",
        method: str = "GET"
    ) -> Tuple[bool, Optional[str]]:
        """Check HTTP endpoint health.

        Args:
            host: Server host
            port: Server port
            path: Health check endpoint path
            method: HTTP method (GET or POST)

        Returns:
            Tuple of (is_healthy, error_message)
        """
        url = f"http://{host}:{port}{path}"

        try:
            if method.upper() == "POST":
                response = requests.post(url, timeout=self.http_timeout)
            else:
                response = requests.get(url, timeout=self.http_timeout)

            # Consider 2xx and 3xx as healthy
            if 200 <= response.status_code < 400:
                return True, None
            else:
                return False, f"HTTP {response.status_code} from {url}"

        except requests.exceptions.ConnectionError:
            return False, f"Connection refused to {url}"
        except requests.exceptions.Timeout:
            return False, f"Timeout connecting to {url}"
        except Exception as e:
            return False, f"Error checking {url}: {e}"

    def check_mcp_jsonrpc_health(
        self,
        host: str,
        port: int,
        server_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Check MCP server health via JSON-RPC tools/list request.

        Args:
            host: Server host
            port: Server port
            server_name: Name of the MCP server

        Returns:
            Tuple of (is_healthy, error_message)
        """
        url = f"http://{host}:{port}/{server_name}/mcp"

        # JSON-RPC tools/list request (standard MCP method)
        payload = {
            "jsonrpc": "2.0",
            "id": f"health_check_{datetime.now().timestamp()}",
            "method": "tools/list",
            "params": {}
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.http_timeout
            )

            if response.status_code != 200:
                return False, f"HTTP {response.status_code} from {url}"

            data = response.json()

            # Check for JSON-RPC error
            if "error" in data:
                error = data["error"]
                return False, f"JSON-RPC error: {error.get('message', str(error))}"

            # Successful response
            return True, None

        except requests.exceptions.ConnectionError:
            return False, f"Connection refused to {url}"
        except requests.exceptions.Timeout:
            return False, f"Timeout connecting to {url}"
        except json.JSONDecodeError:
            return False, f"Invalid JSON response from {url}"
        except Exception as e:
            return False, f"Error checking {url}: {e}"

    def check_server_health(
        self,
        pid: int,
        host: str,
        port: int,
        server_name: str,
        use_http_check: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """Perform comprehensive health check on a server.

        Checks both process status and HTTP endpoint (if enabled).

        Args:
            pid: Process ID
            host: Server host
            port: Server port
            server_name: Name of the MCP server
            use_http_check: Whether to check HTTP endpoint

        Returns:
            Tuple of (is_healthy, error_message)
        """
        # First check if process is alive
        process_alive, process_error = self.check_process_alive(pid)

        if not process_alive:
            return False, process_error

        # If HTTP checks are disabled, just return process status
        if not use_http_check:
            return True, None

        # Check MCP JSON-RPC endpoint
        http_healthy, http_error = self.check_mcp_jsonrpc_health(host, port, server_name)

        if not http_healthy:
            return False, http_error

        return True, None
