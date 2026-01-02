"""Watchdog manager for monitoring and auto-restarting MCP servers."""

import asyncio
import threading
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger

from ..models.server_status import ServerState, ServerStatus, RestartPolicy
from .process_monitor import ProcessMonitor
from .restart_manager import RestartManager


class WatchdogManager:
    """Manages monitoring and auto-restart for all MCP servers."""

    def __init__(
        self,
        health_check_interval: int = 30,
        default_restart_policy: Optional[RestartPolicy] = None
    ):
        """Initialize watchdog manager.

        Args:
            health_check_interval: Interval in seconds between health checks
            default_restart_policy: Default restart policy for all servers
        """
        self.health_check_interval = health_check_interval
        self.default_restart_policy = default_restart_policy or RestartPolicy()

        self.monitors: Dict[str, ProcessMonitor] = {}
        self.restart_manager = RestartManager()

        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def add_server(
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
        auto_start: bool = True,
        enable_restart: bool = True
    ) -> bool:
        """Add a server to the watchdog.

        Args:
            server_name: Name of the MCP server
            command: Command to execute
            args: Command arguments
            env: Environment variables
            working_dir: Working directory
            port: Server port
            host: Server host
            restart_policy: Restart policy (uses default if None)
            health_check_enabled: Whether to perform health checks
            auto_start: Whether to start the server immediately

        Returns:
            True if added and started successfully, False otherwise
        """
        if server_name in self.monitors:
            logger.warning(f"Server {server_name} already exists in watchdog")
            return False

        # Create process monitor
        monitor = ProcessMonitor(
            server_name=server_name,
            command=command,
            args=args,
            env=env,
            working_dir=working_dir,
            port=port,
            host=host,
            restart_policy=restart_policy or self.default_restart_policy,
            health_check_enabled=health_check_enabled
        )

        self.monitors[server_name] = monitor

        # Store restart enabled flag on the monitor
        monitor.restart_enabled = enable_restart

        # Start the server if auto_start is enabled
        if auto_start:
            success = monitor.start()
            if not success:
                logger.error(f"Failed to start {server_name}")
                return False

        logger.info(f"Added {server_name} to watchdog")
        return True

    def remove_server(self, server_name: str) -> bool:
        """Remove a server from the watchdog.

        Args:
            server_name: Name of the server to remove

        Returns:
            True if removed successfully, False otherwise
        """
        if server_name not in self.monitors:
            logger.warning(f"Server {server_name} not found in watchdog")
            return False

        # Stop the server
        monitor = self.monitors[server_name]
        monitor.stop()

        # Remove from tracking
        del self.monitors[server_name]
        self.restart_manager.reset_restart_history(server_name)

        logger.info(f"Removed {server_name} from watchdog")
        return True

    def start_monitoring(self) -> None:
        """Start the monitoring loop in a background thread."""
        if self._monitoring:
            logger.warning("Monitoring is already running")
            return

        self._monitoring = True
        self._stop_event.clear()

        self._monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="WatchdogMonitorThread"
        )
        self._monitor_thread.start()

        logger.info(
            f"Started watchdog monitoring for {len(self.monitors)} servers "
            f"(interval: {self.health_check_interval}s)"
        )

    def stop_monitoring(self) -> None:
        """Stop the monitoring loop."""
        if not self._monitoring:
            return

        logger.info("Stopping watchdog monitoring...")
        self._monitoring = False
        self._stop_event.set()

        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)

        logger.info("Watchdog monitoring stopped")

    def _monitoring_loop(self) -> None:
        """Main monitoring loop (runs in background thread)."""
        logger.info("Watchdog monitoring loop started")

        while self._monitoring and not self._stop_event.is_set():
            try:
                # Check health of all servers
                for server_name, monitor in list(self.monitors.items()):
                    self._check_and_restart_if_needed(server_name, monitor)

                # Clean up old restart history
                self.restart_manager.cleanup_old_history()

                # Wait for next check interval
                self._stop_event.wait(self.health_check_interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                # Continue monitoring despite errors
                self._stop_event.wait(5)

        logger.info("Watchdog monitoring loop ended")

    def _check_and_restart_if_needed(
        self,
        server_name: str,
        monitor: ProcessMonitor
    ) -> None:
        """Check server health and restart if needed.

        Args:
            server_name: Name of the server
            monitor: ProcessMonitor instance
        """
        # Skip monitoring if server is already in terminal FAILED state
        if monitor.status.state == ServerState.FAILED:
            return

        status = monitor.get_status()

        # Check health
        is_healthy = monitor.check_health()

        if is_healthy:
            # Server is healthy, no action needed
            return

        # Server is unhealthy or crashed
        logger.warning(
            f"Server {server_name} is unhealthy: {status.state.value} - "
            f"{status.error_message or 'Unknown error'}"
        )

        # Check if restart is enabled for this server
        if not getattr(monitor, 'restart_enabled', True):
            logger.info(
                f"Auto-restart is disabled for {server_name} (stdio-based server). "
                f"Marking as FAILED and stopping watchdog monitoring."
            )
            monitor.status.state = ServerState.FAILED
            # Note: We keep the server in monitors dict for status reporting,
            # but the FAILED state check above prevents further monitoring
            return

        # Check if we can restart
        can_restart, reason = self.restart_manager.can_restart(
            server_name=server_name,
            policy=monitor.restart_policy,
            current_restart_count=status.restart_count
        )

        if not can_restart:
            logger.error(
                f"Cannot restart {server_name}: {reason}. "
                f"Server marked as FAILED."
            )
            monitor.status.state = ServerState.FAILED
            return

        # Attempt restart
        self._restart_server(server_name, monitor)

    def _restart_server(
        self,
        server_name: str,
        monitor: ProcessMonitor
    ) -> None:
        """Restart a server with exponential backoff.

        Args:
            server_name: Name of the server
            monitor: ProcessMonitor instance
        """
        logger.info(f"Attempting to restart {server_name}")

        # Update state
        monitor.status.state = ServerState.RESTARTING

        # Stop the current process
        monitor.stop()

        # Wait for backoff delay
        self.restart_manager.wait_with_backoff(
            server_name=server_name,
            policy=monitor.restart_policy,
            restart_count=monitor.status.restart_count
        )

        # Increment restart counter
        monitor.increment_restart_count()

        # Record restart attempt
        self.restart_manager.record_restart(server_name)

        # Start the server
        success = monitor.start()

        if success:
            logger.info(
                f"Successfully restarted {server_name} "
                f"(restart #{monitor.status.restart_count})"
            )
        else:
            logger.error(f"Failed to restart {server_name}")

    def get_all_status(self) -> List[ServerStatus]:
        """Get status of all monitored servers.

        Returns:
            List of ServerStatus objects
        """
        return [monitor.get_status() for monitor in self.monitors.values()]

    def get_server_status(self, server_name: str) -> Optional[ServerStatus]:
        """Get status of a specific server.

        Args:
            server_name: Name of the server

        Returns:
            ServerStatus object or None if not found
        """
        monitor = self.monitors.get(server_name)
        if monitor:
            return monitor.get_status()
        return None

    def stop_all_servers(self) -> None:
        """Stop all monitored servers."""
        logger.info(f"Stopping all {len(self.monitors)} servers...")

        for server_name, monitor in self.monitors.items():
            try:
                monitor.stop()
            except Exception as e:
                logger.error(f"Error stopping {server_name}: {e}")

        logger.info("All servers stopped")

    def restart_server(self, server_name: str) -> bool:
        """Manually restart a specific server.

        Args:
            server_name: Name of the server to restart

        Returns:
            True if restarted successfully, False otherwise
        """
        monitor = self.monitors.get(server_name)
        if not monitor:
            logger.error(f"Server {server_name} not found")
            return False

        logger.info(f"Manually restarting {server_name}")

        # Stop the server
        monitor.stop()

        # Start the server
        success = monitor.start()

        if success:
            # Reset restart history on manual restart
            self.restart_manager.reset_restart_history(server_name)
            logger.info(f"Successfully restarted {server_name}")
        else:
            logger.error(f"Failed to restart {server_name}")

        return success

    def get_summary(self) -> Dict:
        """Get summary of all servers.

        Returns:
            Dictionary with summary statistics
        """
        total = len(self.monitors)
        states = {}

        for monitor in self.monitors.values():
            status = monitor.get_status()
            state = status.state.value
            states[state] = states.get(state, 0) + 1

        return {
            "total_servers": total,
            "monitoring_enabled": self._monitoring,
            "health_check_interval": self.health_check_interval,
            "states": states
        }
