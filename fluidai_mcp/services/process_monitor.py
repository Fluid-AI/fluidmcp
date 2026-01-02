"""Process monitoring for individual MCP servers.

Threading Model:
    ProcessMonitor instances are designed to be accessed from multiple threads:
    - WatchdogManager's monitoring thread calls check_health() and get_status()
    - Main thread or other threads may call start(), stop(), or restart operations
    - Individual ProcessMonitor methods are NOT internally synchronized
    - Thread safety is managed at the WatchdogManager level via _monitors_lock
    - Once a monitor is created and added to WatchdogManager, concurrent read
      operations (check_health, get_status) are safe
    - Write operations (start, stop, restart) should only be called by one thread
      at a time (enforced by WatchdogManager's lock when accessing monitors dict)
"""

import subprocess
from datetime import datetime
from typing import Optional, Dict
from pathlib import Path
from loguru import logger

from ..models.server_status import ServerState, ServerStatus, RestartPolicy
from .health_checker import HealthChecker


class ProcessMonitor:
    """Monitors a single MCP server process.

    Note: This class is NOT internally thread-safe. Thread safety is managed
    by WatchdogManager via _monitors_lock. See module docstring for details.
    """

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
        health_check_enabled: bool = True,
        restart_enabled: bool = True
    ):
        """Initialize process monitor.

        Args:
            server_name: Name of the MCP server
            command: Command to execute
            args: Command arguments
            env: Environment variables dict to use for the subprocess.
                 IMPORTANT: Callers MUST pass a merged environment dict (os.environ + custom vars)
                 to ensure proper inheritance. Passing None or an empty dict will result in
                 no environment variables being available to the subprocess, which will likely
                 cause failures. The implementation does not automatically merge with os.environ.
            working_dir: Working directory for the process
            port: Server port for health checks
            host: Server host for health checks
            restart_policy: Restart policy (uses default if None)
            health_check_enabled: Whether to perform health checks
            restart_enabled: Whether automatic restart is enabled
        """
        self.server_name = server_name
        self.command = command
        self.args = args
        # Callers are responsible for merging with os.environ if needed
        self.env = env
        self.working_dir = working_dir
        self.port = port
        self.host = host
        self.restart_policy = restart_policy or RestartPolicy()
        self.health_check_enabled = health_check_enabled
        self.restart_enabled = restart_enabled

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

    def attach_existing_process(
        self,
        process_handle: subprocess.Popen,
        pid: int,
        state: ServerState,
        started_at: datetime
    ) -> None:
        """Attach an existing process to this monitor.

        Used when a process is already running and needs to be registered
        with the watchdog after the fact.

        Args:
            process_handle: Subprocess.Popen object
            pid: Process ID
            state: Initial server state
            started_at: Process start timestamp
        """
        self.process = process_handle
        self.status.pid = pid
        self.status.state = state
        self.status.started_at = started_at
        logger.info(f"Attached existing process {pid} to monitor {self.server_name}")

    def stop(self) -> bool:
        """Stop the server process.

        Returns:
            True if stopped successfully, False otherwise
        """
        if self.process is None:
            logger.warning(f"Server {self.server_name} is not running")
            return True

        try:
            # Safely get PID before attempting to access it
            pid = getattr(self.process, "pid", None)
            if pid is not None:
                logger.info(f"Stopping server {self.server_name} (PID {pid})")
            else:
                logger.info(f"Stopping server {self.server_name} (PID unknown)")

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
            ServerStatus object with computed uptime via get_uptime_seconds()
        """
        return self.status

    def increment_restart_count(self) -> None:
        """Increment the restart counter."""
        self.status.restart_count += 1

    def get_logs(self, lines: int = 50) -> Dict[str, str]:
        """Get recent logs from the process.

        IMPORTANT: For stdio-based MCP servers, stdout/stderr pipes are used for JSON-RPC
        communication and may contain large amounts of protocol traffic. Reading from these
        pipes to obtain a "tail" of logs would require consuming the entire stream into
        memory, which can cause memory issues for terminated processes with large outputs
        and interfere with the router's management of the pipes.

        To avoid these problems, this method intentionally does not read from the process
        pipes. If detailed logs are required, the underlying server should be configured to
        write to log files, and those files should be read through a separate, dedicated
        mechanism.

        Args:
            lines: Number of lines to retrieve (unused, kept for API compatibility)

        Returns:
            Dictionary with empty strings for stdout/stderr and explanatory message
        """
        # For stdio-based MCP servers, pipes are managed by FastAPI router
        # and should not be read from this monitoring code
        return {
            "stdout": "",
            "stderr": "",
            "message": "Logs not available for stdio-based servers (pipes managed by router)"
        }

    def get_exit_code(self) -> Optional[int]:
        """Get process exit code if terminated.

        Returns:
            Exit code or None if still running
        """
        if self.process is None:
            return None

        return self.process.poll()
