"""Process monitoring for individual MCP servers."""

import subprocess
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from loguru import logger

from ..models.server_status import ServerState, ServerStatus, RestartPolicy
from .health_checker import HealthChecker


class ProcessMonitor:
    """Monitors a single MCP server process."""

    def __init__(
        self,
        server_name: str,
        command: str,
        args: list,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[Path] = None,
        port: Optional[int] = None,
        host: str = "localhost",
        restart_policy: Optional[RestartPolicy] = None,
        health_check_enabled: bool = True
    ):
        """Initialize process monitor.

        Args:
            server_name: Name of the MCP server
            command: Command to execute
            args: Command arguments
            env: Environment variables
            working_dir: Working directory for the process
            port: Server port for health checks
            host: Server host for health checks
            restart_policy: Restart policy (uses default if None)
            health_check_enabled: Whether to perform health checks
        """
        self.server_name = server_name
        self.command = command
        self.args = args
        self.env = env or {}
        self.working_dir = working_dir
        self.port = port
        self.host = host
        self.restart_policy = restart_policy or RestartPolicy()
        self.health_check_enabled = health_check_enabled

        self.process: Optional[subprocess.Popen] = None
        self.status = ServerStatus(
            name=server_name,
            state=ServerState.STOPPED,
            port=port
        )

        self.health_checker = HealthChecker()

    def start(self) -> bool:
        """Start the server process.

        Returns:
            True if started successfully, False otherwise
        """
        if self.process is not None and self.is_running():
            logger.warning(f"Server {self.server_name} is already running")
            return True

        try:
            logger.info(f"Starting server {self.server_name}: {self.command} {' '.join(self.args)}")

            self.status.state = ServerState.STARTING
            self.status.started_at = datetime.now()

            # Start the process
            self.process = subprocess.Popen(
                [self.command] + self.args,
                env=self.env,
                cwd=self.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            self.status.pid = self.process.pid
            self.status.state = ServerState.RUNNING
            self.status.error_message = None

            logger.info(f"Started {self.server_name} with PID {self.process.pid}")
            return True

        except Exception as e:
            error_msg = f"Failed to start {self.server_name}: {e}"
            logger.error(error_msg)
            self.status.state = ServerState.FAILED
            self.status.error_message = error_msg
            return False

    def stop(self) -> bool:
        """Stop the server process.

        Returns:
            True if stopped successfully, False otherwise
        """
        if self.process is None:
            logger.warning(f"Server {self.server_name} is not running")
            return True

        try:
            logger.info(f"Stopping server {self.server_name} (PID {self.process.pid})")

            self.process.terminate()

            # Wait up to 10 seconds for graceful shutdown
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(f"Server {self.server_name} did not stop gracefully, forcing kill")
                self.process.kill()
                self.process.wait()

            self.status.state = ServerState.STOPPED
            self.status.pid = None
            self.process = None

            logger.info(f"Stopped {self.server_name}")
            return True

        except Exception as e:
            error_msg = f"Error stopping {self.server_name}: {e}"
            logger.error(error_msg)
            self.status.error_message = error_msg
            return False

    def is_running(self) -> bool:
        """Check if the process is running.

        Returns:
            True if process is running, False otherwise
        """
        if self.process is None:
            return False

        # Check if process has terminated
        if self.process.poll() is not None:
            return False

        return True

    def check_health(self) -> bool:
        """Perform health check on the server.

        Returns:
            True if healthy, False otherwise
        """
        if not self.is_running():
            self.status.state = ServerState.CRASHED
            self.status.error_message = "Process not running"
            return False

        # If health checks are disabled, just check if process is alive
        if not self.health_check_enabled or self.port is None:
            self.status.state = ServerState.RUNNING
            self.status.last_health_check = datetime.now()
            return True

        # Perform comprehensive health check
        is_healthy, error_msg = self.health_checker.check_server_health(
            pid=self.status.pid,
            host=self.host,
            port=self.port,
            server_name=self.server_name,
            use_http_check=True
        )

        self.status.last_health_check = datetime.now()

        if is_healthy:
            self.status.state = ServerState.HEALTHY
            self.status.error_message = None
        else:
            self.status.state = ServerState.UNHEALTHY
            self.status.error_message = error_msg
            logger.warning(f"Health check failed for {self.server_name}: {error_msg}")

        return is_healthy

    def get_status(self) -> ServerStatus:
        """Get current server status.

        Returns:
            ServerStatus object
        """
        # Update uptime if running
        if self.status.started_at and self.is_running():
            uptime = (datetime.now() - self.status.started_at).total_seconds()
            # Store uptime in a custom attribute (not in dataclass)
            setattr(self.status, '_uptime_seconds', uptime)

        return self.status

    def increment_restart_count(self) -> None:
        """Increment the restart counter."""
        self.status.restart_count += 1

    def get_logs(self, lines: int = 50) -> Dict[str, str]:
        """Get recent logs from the process.

        Args:
            lines: Number of lines to retrieve

        Returns:
            Dictionary with stdout and stderr logs
        """
        if self.process is None:
            return {"stdout": "", "stderr": ""}

        try:
            # Read available output (non-blocking)
            stdout_lines = []
            stderr_lines = []

            # Note: This is a simplified version
            # In production, you'd want to use a proper log buffer
            if self.process.stdout:
                try:
                    stdout_lines = self.process.stdout.readlines()[-lines:]
                except:
                    pass

            if self.process.stderr:
                try:
                    stderr_lines = self.process.stderr.readlines()[-lines:]
                except:
                    pass

            return {
                "stdout": "".join(stdout_lines),
                "stderr": "".join(stderr_lines)
            }

        except Exception as e:
            logger.error(f"Error reading logs for {self.server_name}: {e}")
            return {"stdout": "", "stderr": ""}

    def get_exit_code(self) -> Optional[int]:
        """Get process exit code if terminated.

        Returns:
            Exit code or None if still running
        """
        if self.process is None:
            return None

        return self.process.poll()
