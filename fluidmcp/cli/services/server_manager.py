"""
ServerManager - Centralized MCP server lifecycle management.

This module provides dynamic start/stop/restart capabilities for MCP servers,
process registry, state persistence, and integration with the backend API.
"""
import os
import asyncio
import subprocess
import json
import time
import atexit
from typing import Dict, Any, Optional, List, IO
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

from ..repositories.database import DatabaseManager
from .package_launcher import initialize_mcp_server
from .metrics import MetricsCollector
from .health_checker import HealthChecker
from .sse_handle import SseSubprocessHandle


class ServerManager:
    """Manages MCP server processes and lifecycle."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize ServerManager.

        Args:
            db_manager: Database manager for state persistence
        """
        self.db = db_manager

        # Process registry (in-memory)
        self.processes: Dict[str, subprocess.Popen] = {}
        self.configs: Dict[str, Dict[str, Any]] = {}
        self.start_times: Dict[str, float] = {}  # server_id -> start timestamp (monotonic)

        # Operation locks to prevent concurrent operations on same server
        self._operation_locks: Dict[str, asyncio.Lock] = {}

        # Event loop for async operations
        self._loop = None

        # Health checker for process validation
        self.health_checker = HealthChecker()

        # Stale PID update cache to throttle database writes
        # Maps server_id -> last_update_timestamp
        self._stale_pid_updates: Dict[str, float] = {}
        # Cache stale PID updates for 30s to balance UI responsiveness vs DB load
        # 30s provides quick feedback (max 30s delay) while preventing excessive writes
        # when repeatedly checking the same stale server
        self._stale_pid_cache_ttl = 30.0  # seconds

        # Stderr log file handles (for file-based stderr capture)
        self._stderr_logs: Dict[str, IO] = {}

        # Idle cleanup configuration
        self.idle_timeout_seconds = int(os.getenv("FMCP_IDLE_TIMEOUT", "3600"))  # Default 1 hour
        self.cleanup_interval_seconds = 300  # Run cleanup every 5 minutes
        self._cleanup_task: Optional[asyncio.Task] = None

        # Register cleanup handlers
        atexit.register(self._cleanup_on_exit)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup all processes."""
        self._cleanup_on_exit()
        return False

    def _cleanup_on_exit(self) -> None:
        """
        Cleanup handler called on process exit.
        Terminates all running MCP server processes.
        """
        if not self.processes:
            return

        logger.info(f"Cleaning up {len(self.processes)} running server(s)...")

        for server_id, process in list(self.processes.items()):
            try:
                if process.poll() is None:  # Process still running
                    logger.info(f"Terminating server '{server_id}' (PID: {process.pid})")

                    # Try graceful termination first (SIGTERM)
                    process.terminate()

                    # Wait up to 5 seconds for graceful shutdown
                    try:
                        process.wait(timeout=5)
                        logger.info(f"Server '{server_id}' terminated gracefully")
                    except subprocess.TimeoutExpired:
                        # Force kill if graceful shutdown failed
                        logger.warning(f"Server '{server_id}' did not terminate, forcing kill...")
                        process.kill()
                        process.wait(timeout=2)
                        logger.info(f"Server '{server_id}' force killed")

                    # Reap zombie process
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        # Intentional: timeout during cleanup is acceptable - process will be reaped by OS
                        pass

            except Exception as e:
                logger.error(f"Error cleaning up server '{server_id}': {e}")

        self.processes.clear()

        # Close all stderr log file handles
        for server_id in list(self._stderr_logs.keys()):
            self._close_stderr_log(server_id)

        logger.info("All servers cleaned up")

    async def shutdown_all(self) -> None:
        """
        Async shutdown handler for graceful cleanup.
        Should be called when the application is shutting down.
        """
        logger.info("Initiating graceful shutdown of all servers...")

        for server_id in list(self.processes.keys()):
            try:
                await self.stop_server(server_id)
            except Exception as e:
                logger.error(f"Error stopping server '{server_id}' during shutdown: {e}")

        logger.info("All servers shut down")

    # ==================== Server Lifecycle Methods ====================

    async def _start_server_unlocked(self, id: str, config: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None) -> bool:
        """
        Internal method to start a server without acquiring a lock.

        ⚠️ IMPORTANT: This method does NOT acquire operation locks.
        - Only call from restart_server() which holds the lock for the entire operation
        - DO NOT call directly from public APIs

        Args:
            id: Unique server identifier
            config: Server configuration (if None, loads from database)
            user_id: User who is starting the server (for tracking)

        Returns:
            True if started successfully, False otherwise
        """
        # Initialize name and collector early for exception handler
        name = id
        collector = MetricsCollector(id)

        try:
            # Check if already running
            if id in self.processes:
                process = self.processes[id]
                if process.poll() is None:
                    logger.warning(f"Server '{id}' is already running (PID: {process.pid})")
                    return False

            # Load config from database if not provided
            if config is None:
                config = await self.db.get_server_config(id)
                if not config:
                    logger.error(f"No configuration found for server '{id}'")
                    return False

            # Store config
            self.configs[id] = config

            # Get display name from config
            name = config.get("name", id)

            # Spawn the MCP process with timeout
            logger.info(f"Starting server '{name}' (id: {id})...")
            try:
                process = await asyncio.wait_for(
                    self._spawn_mcp_process(id, config),
                    timeout=30.0  # 30 second startup timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"Server '{name}' (id: {id}) startup timed out after 30 seconds")
                # Update metrics - server failed to start (status code: 3)
                collector.set_server_status(3)  # 3 = error
                collector.record_error("startup_timeout")
                # Save error to instance state
                await self.db.save_instance_state({
                    "server_id": id,
                    "state": "failed",
                    "last_error": "Server startup timed out after 30 seconds"
                })
                return False

            if not process:
                logger.error(f"Failed to spawn process for server '{name}' (id: {id})")
                return False

            # Store process
            self.processes[id] = process
            logger.info(f"Server '{name}' started (PID: {process.pid})")

            # Clear stale PID cache entry (if any) since server is now running
            self._stale_pid_updates.pop(id, None)

            # Get existing state for optimistic locking
            existing_state = await self.db.get_instance_state(id)
            existing_pid = existing_state.get("pid") if existing_state else None

            # Save state to database with user tracking and optimistic locking
            # Use optimistic locking to prevent race conditions with stale PID checker
            success = await self.db.save_instance_state({
                "server_id": id,
                "state": "running",
                "pid": process.pid,
                "start_time": datetime.utcnow(),
                "stop_time": None,
                "exit_code": None,
                "restart_count": 0,
                "last_health_check": datetime.utcnow(),
                "health_check_failures": 0,
                "started_by": user_id,  # Track who started this instance
                "last_used_at": datetime.utcnow()  # Initialize last_used_at when server starts
            }, expected_pid=existing_pid)

            if not success:
                logger.warning(f"Optimistic lock failed when starting server '{name}' - PID changed during start operation")
                # Still return True since the process started successfully
                # The state mismatch will be reconciled on next status check

            # Update metrics - server is now running (status code: 2)
            # Note: Metrics update after database save to ensure state consistency
            collector.set_server_status(2)  # 2 = running

            # Store start time for dynamic uptime calculation
            self.start_times[id] = time.monotonic()
            collector.set_uptime(0.0)  # Just started

            return True

        except Exception as e:
            logger.exception(f"Error starting server '{name}' (id: {id}): {e}")

            # Update metrics - server failed to start (status code: 3)
            collector.set_server_status(3)  # 3 = error
            collector.record_error("start_failed")

            # Save error to instance state (PDF spec: last_error field)
            await self.db.save_instance_state({
                "server_id": id,
                "state": "failed",
                "last_error": str(e)
            })

            return False

    async def start_server(self, id: str, config: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None) -> bool:
        """
        Start an MCP server.

        Uses a lock to prevent concurrent start operations on the same server.

        Args:
            id: Unique server identifier
            config: Server configuration (if None, loads from database)
            user_id: User who is starting the server (for tracking)

        Returns:
            True if started successfully, False otherwise
        """
        # Check for concurrent operations - fail fast
        lock = self._get_operation_lock(id)
        if lock.locked():
            logger.warning(f"Server '{id}' is already being modified by another operation")
            return False

        # Acquire lock for this operation
        async with lock:
            return await self._start_server_unlocked(id, config, user_id)

    async def _stop_server_unlocked(self, id: str, force: bool = False) -> bool:
        """
        Internal method to stop a server without acquiring a lock.

        ⚠️ IMPORTANT: This method does NOT acquire operation locks.
        - Only call from restart_server() which holds the lock for the entire operation
        - DO NOT call directly from public APIs

        Args:
            id: Server identifier
            force: If True, use SIGKILL instead of SIGTERM

        Returns:
            True if stopped successfully, False otherwise
        """
        # Initialize metrics collector early for consistent error tracking
        collector = MetricsCollector(id)

        try:
            # Check if server exists
            if id not in self.processes:
                logger.warning(f"Server '{id}' is not running")
                return False

            process = self.processes[id]

            # Get display name from config
            config = self.configs.get(id, {})
            name = config.get("name", id)

            # Check if already dead
            if process.poll() is not None:
                logger.info(f"Server '{name}' (id: {id}) already stopped (exit code: {process.returncode})")
                await self._cleanup_server(id, process.returncode, intentional=True)
                return True

            # Terminate process
            logger.info(f"Stopping server '{name}' (id: {id}, PID: {process.pid})...")

            if force:
                process.kill()  # SIGKILL
                logger.info(f"Sent SIGKILL to server '{name}' (id: {id})")
            else:
                process.terminate()  # SIGTERM
                logger.info(f"Sent SIGTERM to server '{name}' (id: {id})")

            # Wait for process to exit (with timeout)
            try:
                exit_code = await asyncio.wait_for(
                    asyncio.to_thread(process.wait),
                    timeout=10.0
                )
                logger.info(f"Server '{name}' (id: {id}) stopped (exit code: {exit_code})")
            except asyncio.TimeoutError:
                logger.warning(f"Server '{name}' (id: {id}) did not stop gracefully, forcing kill...")
                process.kill()
                exit_code = await asyncio.to_thread(process.wait)

            # Cleanup
            await self._cleanup_server(id, exit_code, intentional=True)

            # Update metrics - server is now stopped (status code: 0)
            collector.set_server_status(0)  # 0 = stopped

            return True

        except Exception as e:
            logger.exception(f"Error stopping server '{id}': {e}")
            collector.record_error("stop_failed")
            return False

    async def stop_server(self, id: str, force: bool = False) -> bool:
        """
        Stop a running MCP server.

        Uses a lock to prevent concurrent stop operations on the same server.

        Args:
            id: Server identifier
            force: If True, use SIGKILL instead of SIGTERM

        Returns:
            True if stopped successfully, False otherwise
        """
        # Check for concurrent operations - fail fast
        lock = self._get_operation_lock(id)
        if lock.locked():
            logger.warning(f"Server '{id}' is already being modified by another operation")
            return False

        # Acquire lock for this operation
        async with lock:
            return await self._stop_server_unlocked(id, force)

    def _get_operation_lock(self, server_id: str) -> asyncio.Lock:
        """
        Get or create an operation lock for a server.

        Prevents concurrent operations (start/stop/restart) on the same server.

        Args:
            server_id: Server identifier

        Returns:
            Asyncio lock for the server
        """
        if server_id not in self._operation_locks:
            self._operation_locks[server_id] = asyncio.Lock()
        return self._operation_locks[server_id]

    async def restart_server(self, id: str) -> bool:
        """
        Restart an MCP server atomically.

        Uses a lock to prevent concurrent restart operations on the same server.
        The lock is held for the entire restart operation (stop + start) to ensure atomicity.

        Args:
            id: Server identifier

        Returns:
            True if restarted successfully
        """
        # Acquire lock to prevent concurrent operations
        lock = self._get_operation_lock(id)

        # Try to acquire lock without waiting - fail fast if operation in progress
        if lock.locked():
            logger.warning(f"Server '{id}' is already being modified by another operation")
            return False

        async with lock:
            # Get current config before stopping
            config = self.configs.get(id)
            if not config:
                config = await self.db.get_server_config(id)

            # Get display name
            name = config.get("name", id) if config else id
            logger.info(f"Restarting server '{name}' (id: {id})...")

            # Stop server (using internal unlocked method - lock already held)
            if id in self.processes:
                stop_success = await self._stop_server_unlocked(id)
                if not stop_success:
                    logger.error(f"Failed to stop server '{name}' (id: {id}) during restart")
                    return False

            # Increment restart count
            instance = await self.db.get_instance_state(id)
            restart_count = instance.get("restart_count", 0) if instance else 0

            # Update config with new restart count
            if config:
                config["_restart_count"] = restart_count + 1

            # Start server (using internal unlocked method - lock already held)
            success = await self._start_server_unlocked(id, config)

            if success:
                # Update restart count in database
                await self.db.save_instance_state({
                    "server_id": id,
                    "restart_count": restart_count + 1
                })

                # Record restart in metrics
                collector = MetricsCollector(id)
                collector.record_restart("manual_restart")
                # Note: Status already set to 2 (running) by start_server() - no need to override

            return success

    async def get_server_status(self, id: str) -> Dict[str, Any]:
        """
        Get status of a server.

        Args:
            id: Server identifier

        Returns:
            Status dictionary with state, pid, uptime, etc.
        """
        # Check if process exists in registry
        if id in self.processes:
            process = self.processes[id]
            is_alive = process.poll() is None

            if is_alive:
                # Calculate uptime
                instance = await self.db.get_instance_state(id)
                start_time = instance.get("start_time") if instance else None

                uptime = None
                if start_time:
                    if isinstance(start_time, str):
                        start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    uptime = (datetime.utcnow() - start_time).total_seconds()

                return {
                    "id": id,
                    "state": "running",
                    "transport": "sse" if isinstance(process, SseSubprocessHandle) else "stdio",
                    "url": process.sse_url if isinstance(process, SseSubprocessHandle) else None,
                    "pid": process.pid,
                    "uptime": uptime,
                    "restart_count": instance.get("restart_count", 0) if instance else 0,
                    "exit_code": None
                }
            else:
                # Process died
                return {
                    "id": id,
                    "state": "failed",
                    "pid": None,
                    "uptime": None,
                    "restart_count": 0,
                    "exit_code": process.returncode
                }

        # Check database
        instance = await self.db.get_instance_state(id)
        if instance:
            state = instance.get("state", "unknown")
            pid = instance.get("pid")

            # Validate PID if state is "running" - fix stale PID issue
            if state == "running" and pid:
                is_alive, error_msg = self.health_checker.check_process_alive(pid)
                if not is_alive:
                    # Check if we recently updated this stale PID (throttling)
                    current_time = time.time()
                    last_update = self._stale_pid_updates.get(id, 0)

                    if current_time - last_update < self._stale_pid_cache_ttl:
                        # Return cached failed status without database write
                        logger.debug(f"Server {id} stale PID {pid} cached, skipping DB update")
                        return {
                            "id": id,
                            "state": "failed",
                            "pid": None,
                            "uptime": None,
                            "restart_count": instance.get("restart_count", 0),
                            "exit_code": -1
                        }

                    logger.warning(f"Server {id} has stale PID {pid}: {error_msg}. Updating state to 'failed'.")
                    # Update database with corrected state using optimistic locking
                    # Only update if PID hasn't changed (prevents race condition)
                    success = await self.db.save_instance_state({
                        "server_id": id,
                        "state": "failed",
                        "pid": None,
                        "exit_code": -1,  # Unknown exit code for stale PID
                        "updated_at": datetime.utcnow()
                    }, expected_pid=pid)

                    # If optimistic lock failed, PID changed - re-fetch status
                    if not success:
                        logger.debug(f"Server {id} PID changed during stale check, re-fetching status")
                        return await self.get_server_status(id)

                    # Check for auto-restart on crash
                    await self._check_auto_restart_on_crash(id, instance)

                    # Cache the update timestamp
                    self._stale_pid_updates[id] = current_time

                    # Return corrected status
                    return {
                        "id": id,
                        "state": "failed",
                        "pid": None,
                        "uptime": None,
                        "restart_count": instance.get("restart_count", 0),
                        "exit_code": -1
                    }

            # Return database state as-is (PID validated or not applicable)
            return {
                "id": id,
                "state": state,
                "pid": pid,
                "uptime": None,
                "restart_count": instance.get("restart_count", 0),
                "exit_code": instance.get("exit_code")
            }

        # Server not found
        return {
            "id": id,
            "state": "not_found",
            "pid": None,
            "uptime": None,
            "restart_count": 0,
            "exit_code": None
        }

    async def list_servers(self, enabled_only: bool = True, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        List all configured servers with their status.

        Args:
            enabled_only: If True, only return enabled servers. If False, return all servers including disabled ones.
            include_deleted: If True, include soft-deleted servers (for admin recovery).

        Returns:
            List of server info dictionaries with nested config structure
        """
        servers = []

        # Get configs from database (filter by enabled_only and include_deleted parameters)
        configs = await self.db.list_server_configs(enabled_only=enabled_only, include_deleted=include_deleted)

        # Merge with in-memory configs (for servers not in DB)
        config_ids = {c.get("id") for c in configs}
        for id, config in self.configs.items():
            if id not in config_ids:
                # Apply same filtering logic as database query
                if enabled_only:
                    # Only include enabled servers
                    if config.get("enabled", True):
                        if include_deleted or not config.get("deleted_at"):
                            configs.append(config)
                else:
                    # Include all servers, optionally including deleted ones
                    if include_deleted or not config.get("deleted_at"):
                        configs.append(config)

        for config in configs:
            id = config.get("id")
            status = await self.get_server_status(id)

            # Separate MCP config fields from metadata fields
            transport = config.get("transport", "stdio")
            if transport == "sse":
                mcp_config = {
                    "transport": "sse",
                    "url": config.get("url"),
                    "command": config.get("command"),
                    "args": config.get("args", []),
                }
            else:
                mcp_config = {
                    "transport": "stdio",
                    "command": config.get("command"),
                    "args": config.get("args", []),
                    "env": config.get("env", {})
                }

            # Build response with nested structure
            server_info = {
                "id": id,
                "name": config.get("name"),
                "config": mcp_config,
                "description": config.get("description", ""),
                "enabled": config.get("enabled", True),
                "restart_window_sec": config.get("restart_window_sec", 300),
                "restart_policy": config.get("restart_policy"),
                "max_restarts": config.get("max_restarts"),
                "tools": config.get("tools", []),
                "created_by": config.get("created_by"),
                "created_at": config.get("created_at"),
                "updated_at": config.get("updated_at"),
                "status": {
                    "state": status.get("state"),
                    "pid": status.get("pid"),
                    "uptime": status.get("uptime"),
                    "restart_count": status.get("restart_count", 0),
                    "exit_code": status.get("exit_code")
                }
            }

            servers.append(server_info)

        return servers

    async def stop_all_servers(self) -> None:
        """Stop all running servers."""
        logger.info("Stopping all servers...")

        for id in list(self.processes.keys()):
            await self.stop_server(id)

        logger.info("All servers stopped")

    # ==================== Private Helper Methods ====================

    async def _spawn_mcp_process(self, id: str, config: Dict[str, Any]) -> Optional[subprocess.Popen]:
        """
        Spawn MCP server process.

        Args:
            id: Server identifier
            config: Server configuration

        Returns:
            Popen process or None if failed
        """
        # Initialize name early for exception handler
        name = id
        try:
            # Extract configuration
            command = config.get("command")
            args = config.get("args", [])
            env_vars = config.get("env", {})
            working_dir = config.get("working_dir", ".")
            install_path = config.get("install_path", ".")
            working_dir_path = Path(working_dir)

            # 🔹 Auto-reclone if directory missing (Railway ephemeral container fix)
            if not working_dir_path.exists():
                logger.warning(f"Working directory missing for server '{id}': {working_dir}")

                if config.get("source") == "github":
                    from .github_utils import clone_github_repo
                    
                    repo = config.get("github_repo")
                    branch = config.get("github_branch", "main")

                    logger.info(f"Auto-recloning repository {repo}@{branch} to {working_dir}")

                    try:
                        # Get GitHub token from environment
                        github_token = os.getenv("FMCP_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
                        if not github_token:
                            logger.error(
                                "GitHub token not found in environment. "
                                "Available env vars: FMCP_GITHUB_TOKEN={}, GITHUB_TOKEN={}".format(
                                    "SET" if os.getenv("FMCP_GITHUB_TOKEN") else "NOT SET",
                                    "SET" if os.getenv("GITHUB_TOKEN") else "NOT SET"
                                )
                            )
                            raise RuntimeError(
                                "GitHub token required for auto-reclone. "
                                "Set FMCP_GITHUB_TOKEN or GITHUB_TOKEN environment variable."
                            )
                        
                        # Determine install_dir from the working_dir path structure
                        # e.g., /app/.fmcp-packages/Fluid-AI/fluid-ai-mcp-servers/main
                        # install_dir = /app/.fmcp-packages
                        parent_path = working_dir_path.parent.parent.parent
                        
                        # Re-clone to the original path using the proper function
                        clone_github_repo(
                            repo_path=repo,
                            branch=branch,
                            github_token=github_token,
                            install_dir=parent_path
                        )

                        # Persist config to database after successful reclone
                        await self.db.save_server_config(config)
                        logger.info(f"Repository auto-recloned successfully to {working_dir}")

                    except Exception as e:
                        logger.error(f"Failed to auto-reclone repository: {e}")
                        return None
                else:
                    logger.error(f"Working directory missing and source is not GitHub")
                    return None
                
            # Load instance-specific env vars (user's API keys, etc.)
            # These override config env vars
            instance_env = await self.db.get_instance_env(id)
            if instance_env:
                logger.debug(f"Merging instance env for server '{id}': {len(instance_env)} vars")
                env_vars = {**env_vars, **instance_env}

            # Get display name
            name = config.get("name", id)

            if not command:
                logger.error(f"No command specified for server '{name}' (id: {id})")
                return None

            # Build command list
            # Normalize --directory paths relative to install_path
            cleaned_args = []
            i = 0
            while i < len(args):
                if args[i] == "--directory" and i + 1 < len(args):
                    dir_path = args[i + 1]

                    # Remove redundant prefix like "embed_weather_mcp_app/"
                    install_name = Path(install_path).name
                    if dir_path.startswith(f"{install_name}/"):
                        dir_path = dir_path[len(install_name) + 1:]

                    cleaned_args.extend(["--directory", dir_path])
                    i += 2
                else:
                    cleaned_args.append(args[i])
                    i += 1

            cmd_list = [command] + cleaned_args

            # Merge environment variables (shell env takes precedence)
            env = dict(os.environ)
            for key, value in env_vars.items():
                if key not in env and value and not self._is_placeholder(value):
                    env[key] = value

            # Determine working directory
            working_dir = Path(config.get("working_dir") or install_path).resolve()

            if not working_dir.exists() or not working_dir.is_dir():
                logger.error(
                    f"Install path for server '{name}' (id: {id}) does not exist or is not a directory: {working_dir}"
                )
                return None

            # 🔥 SAFETY: ensure working_dir is not above install_path
            install_path_resolved = Path(install_path).resolve()
            if install_path_resolved not in working_dir.parents and working_dir != install_path_resolved:
                logger.warning(
                    f"Overriding working_dir {working_dir} → using install_path {install_path}"
                )
                working_dir = install_path_resolved
                
            logger.debug(f"Spawning process: {cmd_list}")
            logger.debug(f"Working directory: {working_dir}")
            logger.debug(f"COMMAND: {cmd_list}")
            logger.debug(f"INSTALL_PATH: {install_path}")
            logger.info("Starting MCP server subprocess")

            # Open stderr log file for persistent crash diagnostics
            try:
                stderr_fh = self._open_stderr_log(id)
            except Exception as e:
                logger.warning(f"Failed to open stderr log for '{name}' (id: {id}), falling back to pipe: {e}")
                stderr_fh = subprocess.PIPE

            # Set subprocess memory limit (default 0 = disabled; set FMCP_DEFAULT_MEMORY_LIMIT_MB to enable)
            memory_limit_mb = config.get("memory_limit_mb",
                int(os.getenv("FMCP_DEFAULT_MEMORY_LIMIT_MB", "0")))
            preexec_fn = self._create_preexec_fn(memory_limit_mb) if memory_limit_mb > 0 else None

            # Spawn subprocess
            process = subprocess.Popen(
                cmd_list,
                cwd=str(working_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_fh,
                env=env,
                text=True,
                bufsize=1,
                preexec_fn=preexec_fn
            )

            # Give process a moment to start
            await asyncio.sleep(0.5)

            # Check if process is still alive
            if process.poll() is not None:
                self._close_stderr_log(id)
                if stderr_fh == subprocess.PIPE and process.stderr:
                    try:
                        _, stderr_output = await asyncio.wait_for(
                            asyncio.to_thread(process.communicate),
                            timeout=2.0
                        )
                    except Exception:
                        stderr_output = ""
                else:
                    stderr_output = self._read_crash_stderr(id)
                logger.error(f"Process died immediately after spawn. stderr: {stderr_output}")
                return None

            # ── SSE transport: skip stdio handshake, wait for HTTP instead ──
            if config.get("transport") == "sse":
                handle = await self._handshake_sse_subprocess(id, config, process)
                if not handle:
                    self._close_stderr_log(id)
                    logger.error(f"SSE handshake failed for server '{name}' (id: {id})")
                    return None
                logger.info(f"[{id}] SSE server connected successfully")
                return handle  # tool discovery already done inside _handshake_sse_subprocess
            # ── stdio transport: normal handshake ───────────────────────────

            # Initialize MCP server with handshake (using shared utility)
            logger.info(f"[{id}] Initializing MCP server...")
            init_success = await asyncio.to_thread(initialize_mcp_server, process)

            if not init_success:
                logger.error(f"MCP initialization failed for server '{name}' (id: {id})")
                process.kill()
                try:
                    await asyncio.to_thread(lambda: process.wait(timeout=2))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
                self._close_stderr_log(id)
                # If stderr was piped (log file open failed), read directly from process;
                # otherwise read from the log file for crash diagnostics.
                stderr_output = ""
                if process.stderr is not None:
                    try:
                        _, stderr_bytes = await asyncio.to_thread(lambda: process.communicate(timeout=2))
                        if stderr_bytes:
                            stderr_output = stderr_bytes.decode(errors="replace") if isinstance(stderr_bytes, bytes) else str(stderr_bytes)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        pass
                if not stderr_output:
                    stderr_output = self._read_crash_stderr(id)
                if stderr_output:
                    logger.error(f"[{id}] Process stderr: {stderr_output[:500]}")
                return None

            logger.info(f"[{id}] MCP server initialized successfully")

            # Discover and cache tools (stdio only — SSE already handled above)
            await self._discover_and_cache_tools(id, process)

            return process

        except asyncio.CancelledError:
            self._close_stderr_log(id)
            raise
        except Exception as e:
            self._close_stderr_log(id)
            logger.exception(f"Error spawning process for server '{name}': {e}")
            return None

    async def _discover_and_cache_tools(self, server_id: str, process: subprocess.Popen) -> None:
        """
        Discover tools via MCP list_tools and cache in database (PDF spec).

        Args:
            server_id: Server identifier
            process: Running MCP server process
        """
        try:
            # Send tools/list request
            tools_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list"
            }

            logger.debug(f"Discovering tools for server '{server_id}'...")
            try:
                process.stdin.write(json.dumps(tools_request) + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                logger.warning(f"Failed to send tools/list request: {e}")
                return

            # Read response with timeout
            try:
                response_line = await asyncio.wait_for(
                    asyncio.to_thread(process.stdout.readline),
                    timeout=5.0
                )

                response_line = response_line.strip()
                logger.debug(f"Tools discovery response: {response_line}")

                response = json.loads(response_line)

                if "result" in response and "tools" in response["result"]:
                    tools = response["result"]["tools"]

                    # Update server config with discovered tools
                    config = await self.db.get_server_config(server_id)
                    if config:
                        config["tools"] = tools
                        try:
                            await self.db.save_server_config(config)
                            logger.info(f"Discovered and cached {len(tools)} tools for server '{server_id}'")
                        except Exception as e:
                            logger.warning(f"Failed to save tools for '{server_id}': {e}")
                    else:
                        logger.warning(f"Could not find config for '{server_id}' to cache tools")
                else:
                    logger.warning(f"No tools found in response for server '{server_id}'")

            except asyncio.TimeoutError:
                logger.warning(f"Tool discovery timeout for server '{server_id}'")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tools response for '{server_id}': {e}")

        except Exception as e:
            logger.warning(f"Tool discovery failed for '{server_id}': {e}")
            # Don't fail the server start if tool discovery fails

    async def _handshake_sse_subprocess(
        self,
        id: str,
        config: Dict[str, Any],
        process: subprocess.Popen,
    ) -> Optional["SseSubprocessHandle"]:
        """
        Complete startup for a subprocess-owned SSE MCP server.

        After the process is spawned we:
          1. Poll until the HTTP server is accepting connections (max 30 s).
          2. Discover and cache tools via POST /messages/.
          3. Return an SseSubprocessHandle wrapping the real Popen.

        Args:
            id:      Server identifier.
            config:  Server config dict (must contain 'url').
            process: The already-spawned subprocess.Popen.

        Returns:
            SseSubprocessHandle on success, None on failure.
        """
        import httpx

        url = config.get("url", "http://127.0.0.1:8000").rstrip("/")
        name = config.get("name", id)
        # Use custom health endpoint if specified, otherwise default to /sse
        health_endpoint = config.get("health_endpoint", "/sse")
        health_url = f"{url}{health_endpoint}"

        logger.info(
            f"[{id}] SSE server '{name}' spawned (PID {process.pid}), "
            f"waiting for HTTP readiness at {health_url}..."
        )

        loop = asyncio.get_event_loop()
        deadline = loop.time() + 30

        while loop.time() < deadline:
            # Guard: process must still be alive
            if process.poll() is not None:
                stderr_out = self._read_crash_stderr(id) or ""
                # If no rotated log available, fall back to the subprocess pipe
                if not stderr_out and getattr(process, "stderr", None) is not None:
                    try:
                        _, stderr_data = process.communicate(timeout=0.5)
                        if stderr_data:
                            stderr_out = stderr_data.decode(errors="replace") if isinstance(stderr_data, (bytes, bytearray)) else str(stderr_data)
                    except Exception:
                        pass
                logger.error(
                    f"[{id}] SSE server process died before HTTP became ready "
                    f"(exit code {process.returncode}). stderr: {stderr_out[:500]}"
                )
                return None

            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    async with client.stream("GET", health_url) as resp:
                        if resp.status_code == 200:
                            elapsed = 30 - (deadline - loop.time())
                            logger.info(
                                f"[{id}] SSE server is ready at {url} "
                                f"(took {elapsed:.1f}s)"
                            )
                            break
            except (httpx.ConnectError, httpx.TimeoutException):
                pass  # Server not up yet — keep polling

            await asyncio.sleep(1.0)
        else:
            logger.error(f"[{id}] SSE server did not become ready within 30s")
            try:
                process.kill()
            except Exception:
                pass
            return None

        # Discover and cache tools via HTTP
        await self._discover_and_cache_tools_sse(id, url)

        return SseSubprocessHandle(process=process, sse_url=url)

    async def _discover_and_cache_tools_sse(self, server_id: str, base_url: str) -> None:
        """
        Discover tools from an SSE MCP server via HTTP and cache in database.

        SSE MCP servers expose a POST /messages/ endpoint that accepts
        standard JSON-RPC 2.0 requests.

        Args:
            server_id: Server identifier.
            base_url:  Base URL of the SSE server (e.g. "http://127.0.0.1:8000").
        """
        import httpx

        messages_url = f"{base_url.rstrip('/')}/messages/"
        tools_request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(messages_url, json=tools_request)
                resp.raise_for_status()
                response = resp.json()

            if "result" in response and "tools" in response["result"]:
                tools = response["result"]["tools"]
                config = await self.db.get_server_config(server_id)
                if config:
                    config["tools"] = tools
                    try:
                        await self.db.save_server_config(config)
                        logger.info(
                            f"[SSE] Discovered and cached {len(tools)} tool(s) "
                            f"for server '{server_id}'"
                        )
                    except Exception as e:
                        logger.warning(
                            f"[SSE] Failed to save tools for '{server_id}': {e}"
                        )
                else:
                    logger.warning(
                        f"[SSE] Config not found for '{server_id}', cannot cache tools"
                    )
            else:
                logger.warning(
                    f"[SSE] No tools in response for server '{server_id}': {response}"
                )

        except Exception as e:
            # Tool discovery failure must never abort server startup
            logger.warning(f"[SSE] Tool discovery failed for '{server_id}': {e}")

    async def _cleanup_server(self, id: str, exit_code: int, intentional: bool = False, stderr_tail: str = "") -> None:
        """
        Clean up after server stops.

        Args:
            id: Server identifier
            exit_code: Process exit code
            intentional: True if this was a deliberate stop (not a crash)
            stderr_tail: Pre-captured stderr (e.g. from PIPE); falls back to log file if empty
        """
        uptime = self.get_uptime(id)

        # Remove from registry
        if id in self.processes:
            del self.processes[id]
        if id in self.start_times:
            del self.start_times[id]

        # Close stderr log file handle
        self._close_stderr_log(id)

        # Determine state
        if intentional or exit_code == 0:
            state = "stopped"
        else:
            state = "failed"

        # Update database
        await self.db.save_instance_state({
            "server_id": id,
            "state": state,
            "pid": None,
            "stop_time": datetime.utcnow(),
            "exit_code": exit_code
        })

        # Persist crash event for non-intentional failures
        if state == "failed":
            if not stderr_tail:
                stderr_tail = self._read_crash_stderr(id)
            try:
                await self.db.save_crash_event({
                    "server_id": id,
                    "exit_code": exit_code,
                    "stderr_tail": stderr_tail,
                    "uptime_seconds": uptime,
                    "timestamp": datetime.utcnow()
                })
            except Exception as e:
                logger.error(f"Failed to save crash event for server '{id}': {e}")
            uptime_str = f"{uptime:.1f}s" if uptime is not None else "unknown"
            logger.warning(f"Server '{id}' crashed (exit_code={exit_code}, uptime={uptime_str})")
        else:
            logger.info(f"Cleaned up server '{id}'")

    def get_uptime(self, server_id: str) -> Optional[float]:
        """
        Get current uptime for a server in seconds.

        Args:
            server_id: Server identifier

        Returns:
            Uptime in seconds since server start, or None if server not running
        """
        if server_id not in self.start_times:
            return None
        return time.monotonic() - self.start_times[server_id]

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        """Check if environment variable value is a placeholder."""
        if not isinstance(value, str):
            return False

        placeholder_indicators = [
            '<' in value and '>' in value,
            'xxxx' in value.lower(),
            'placeholder' in value.lower(),
            value.startswith('<') and value.endswith('>'),
            'your-' in value.lower(),
            'my-' in value.lower(),
        ]

        return any(placeholder_indicators)

    # ==================== Stderr File Logging ====================

    STDERR_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    STDERR_BACKUP_COUNT = 5

    @staticmethod
    def _get_stderr_log_dir() -> str:
        """Resolve stderr log directory (env override or ~/.fluidmcp/logs)."""
        return os.getenv("FLUIDMCP_STDERR_LOG_DIR") or os.path.join(os.path.expanduser("~"), ".fluidmcp", "logs")

    def _get_stderr_log_path(self, server_id: str) -> str:
        """Get the stderr log file path for a server."""
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in server_id)
        return os.path.join(self._get_stderr_log_dir(), f"mcp_{safe_id}_stderr.log")

    def _open_stderr_log(self, server_id: str) -> IO:
        """Open a stderr log file with rotation, returns file handle."""
        log_dir = self._get_stderr_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        log_path = self._get_stderr_log_path(server_id)

        # Rotate if file exceeds max size (rotation happens at spawn time only;
        # a long-running noisy process can exceed STDERR_MAX_BYTES mid-run)
        if os.path.exists(log_path) and os.path.getsize(log_path) > self.STDERR_MAX_BYTES:
            for i in range(self.STDERR_BACKUP_COUNT - 1, 0, -1):
                src = f"{log_path}.{i}"
                dst = f"{log_path}.{i + 1}"
                if os.path.exists(src):
                    os.replace(src, dst)
            os.replace(log_path, f"{log_path}.1")

        fh = open(log_path, "a", encoding="utf-8")
        try:
            os.chmod(log_path, 0o600)
        except OSError:
            pass
        self._stderr_logs[server_id] = fh
        return fh

    def _close_stderr_log(self, server_id: str) -> None:
        """Flush and close stderr log file handle for a server."""
        fh = self._stderr_logs.pop(server_id, None)
        if fh:
            try:
                fh.flush()
                fh.close()
            except Exception:
                pass

    def _read_crash_stderr(self, server_id: str, max_bytes: int = 2048) -> str:
        """Read the tail of a server's stderr log file for crash diagnostics."""
        log_path = self._get_stderr_log_path(server_id)
        try:
            if not os.path.exists(log_path):
                return ""
            size = os.path.getsize(log_path)
            with open(log_path, "rb") as f:
                if size > max_bytes:
                    f.seek(-max_bytes, os.SEEK_END)
                data = f.read()
            text = data.decode("utf-8", errors="replace")
            if size > max_bytes:
                # Skip the first (possibly partial) line
                lines = text.splitlines(keepends=True)
                text = "".join(lines[1:]) if len(lines) > 1 else ""
            return text
        except Exception as e:
            logger.debug(f"Failed to read stderr log for '{server_id}': {e}")
            return ""

    # ==================== Resource Limits ====================

    @staticmethod
    def _create_preexec_fn(memory_limit_mb: int):
        """Create a preexec_fn that sets memory limits for the subprocess."""
        if os.name == "nt":
            logger.warning("Subprocess memory limits (RLIMIT_AS) are not supported on Windows — skipping")
            return None

        def _set_limits():
            try:
                import resource
                limit_bytes = memory_limit_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
            except (ImportError, ValueError, OSError):
                # resource module unavailable or limit rejected — continue without limits
                pass

        return _set_limits

    # ==================== Idle Cleanup Methods ====================

    def start_idle_cleanup_task(self) -> None:
        """
        Start the background idle cleanup task.
        Should be called when the server starts.
        """
        if self._cleanup_task is not None:
            logger.warning("Idle cleanup task already running")
            return

        self._cleanup_task = asyncio.create_task(self._idle_cleanup_loop())
        logger.info(f"Started idle cleanup task (interval: {self.cleanup_interval_seconds}s, timeout: {self.idle_timeout_seconds}s)")

    async def stop_idle_cleanup_task(self) -> None:
        """
        Stop the background idle cleanup task.
        Should be called when the server shuts down.
        """
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Stopped idle cleanup task")

    async def _idle_cleanup_loop(self) -> None:
        """
        Background task that periodically checks for and stops idle servers.
        """
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self._perform_idle_cleanup()
            except asyncio.CancelledError:
                logger.info("Idle cleanup loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in idle cleanup loop: {e}")
                # Continue running despite errors

    async def _perform_idle_cleanup(self) -> None:
        """
        Check for idle servers and stop them if they exceed the idle timeout.
        """
        try:
            # Get all running instances from database
            running_instances = await self.db.list_instances_by_state("running")

            if not running_instances:
                return

            current_time = datetime.utcnow()
            idle_cutoff = current_time - timedelta(seconds=self.idle_timeout_seconds)

            stopped_count = 0

            for instance in running_instances:
                server_id = instance.get("server_id")
                last_used_at = instance.get("last_used_at")

                if last_used_at is None:
                    # Server has never been used, skip for now
                    # Could add a separate grace period for newly started servers
                    continue

                if isinstance(last_used_at, str):
                    last_used_at = datetime.fromisoformat(last_used_at.replace('Z', '+00:00'))

                if last_used_at < idle_cutoff:
                    logger.info(f"Stopping idle server '{server_id}' (last used: {last_used_at}, idle for {self.idle_timeout_seconds}s)")
                    await self.stop_server(server_id)
                    stopped_count += 1

            if stopped_count > 0:
                logger.info(f"Idle cleanup: stopped {stopped_count} server(s)")

        except Exception as e:
            logger.error(f"Error during idle cleanup: {e}")

    async def update_last_used(self, server_id: str) -> None:
        """
        Update the last_used_at timestamp for a server.
        Called when the server is actively used.

        Args:
            server_id: Server identifier
        """
        try:
            await self.db.save_instance_state({
                "server_id": server_id,
                "last_used_at": datetime.utcnow()
            })
        except Exception as e:
            logger.warning(f"Failed to update last_used_at for server '{server_id}': {e}")

    async def _check_auto_restart_on_crash(self, server_id: str, instance: Dict[str, Any]) -> None:
        """
        Check if a crashed server should be automatically restarted based on restart policy.

        Args:
            server_id: Server identifier
            instance: Current instance state from database
        """
        try:
            # Get server configuration
            config = await self.db.get_server_config(server_id)
            if not config:
                logger.debug(f"No config found for server '{server_id}', skipping auto-restart")
                return

            restart_policy = config.get("restart_policy", "on-failure")
            max_restarts = config.get("max_restarts", 3)
            restart_window_sec = config.get("restart_window_sec", 300)

            # Check if restart policy allows auto-restart
            if restart_policy not in ["on-failure", "always"]:
                logger.debug(f"Server '{server_id}' restart policy '{restart_policy}' does not allow auto-restart")
                return

            current_restart_count = instance.get("restart_count", 0)
            last_start_time = instance.get("start_time")

            # Check restart count limit
            if current_restart_count >= max_restarts:
                logger.warning(f"Server '{server_id}' has reached max restarts ({max_restarts}), not auto-restarting")
                return

            # Check restart window
            if last_start_time and restart_window_sec > 0:
                if isinstance(last_start_time, str):
                    last_start_time = datetime.fromisoformat(last_start_time.replace('Z', '+00:00'))

                time_since_start = (datetime.utcnow() - last_start_time).total_seconds()
                if time_since_start < restart_window_sec:
                    logger.debug(f"Server '{server_id}' still within restart window ({time_since_start:.1f}s < {restart_window_sec}s)")
                    return

            # Attempt auto-restart
            logger.info(f"Auto-restarting crashed server '{server_id}' (restart {current_restart_count + 1}/{max_restarts})")

            # Use internal method to avoid lock contention since we're already in a status check
            success = await self._start_server_unlocked(server_id, config)

            if success:
                logger.info(f"Successfully auto-restarted server '{server_id}'")
            else:
                logger.error(f"Failed to auto-restart server '{server_id}'")

        except Exception as e:
            logger.error(f"Error during auto-restart check for server '{server_id}': {e}")


class MCPHealthMonitor:
    """Background health monitor for MCP server processes with automatic restart."""

    MAX_BACKOFF_EXPONENT = 5  # Max 2^5 = 32x multiplier
    DEFAULT_RESTART_DELAY = 5  # Base delay in seconds

    def __init__(self, server_manager: ServerManager, check_interval: int = 30):
        self._sm = server_manager
        self.check_interval = check_interval
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self._restarts_in_progress: set = set()
        self._restart_counts: Dict[str, int] = {}

    def start(self) -> None:
        """Start the background health monitor."""
        if self._running:
            logger.warning("MCP health monitor already running")
            return
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"MCP health monitor started (interval: {self.check_interval}s)")

    async def stop(self) -> None:
        """Stop the background health monitor."""
        if not self._running:
            return
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("MCP health monitor stopped")

    def is_running(self) -> bool:
        return self._running and self._monitor_task is not None and not self._monitor_task.done()

    def _calculate_restart_delay(self, server_id: str) -> float:
        """Exponential backoff: base_delay * 2^min(count, MAX_BACKOFF_EXPONENT)."""
        count = self._restart_counts.get(server_id, 0)
        exponent = min(count, self.MAX_BACKOFF_EXPONENT)
        return self.DEFAULT_RESTART_DELAY * (2 ** exponent)

    async def _monitor_loop(self) -> None:
        """Main monitoring loop — polls all MCP server processes."""
        while self._running:
            try:
                # Snapshot to avoid mutation during iteration
                for server_id, process in list(self._sm.processes.items()):
                    try:
                        await self._check_server(server_id, process)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.error(f"Error checking MCP server '{server_id}': {e}")

                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in MCP health monitor loop: {e}")
                await asyncio.sleep(self.check_interval)

        logger.info("MCP health monitor loop exited")

    async def _check_server(self, server_id: str, process) -> None:
        """Check a single server's health and restart if needed."""
        is_alive = True

        # Check process liveness
        if isinstance(process, SseSubprocessHandle):
            alive, reason = self._sm.health_checker.check_process_alive(process.pid)
            if not alive:
                is_alive = False
                # Refresh returncode so exit_code is accurate for restart policy
                try:
                    process.poll()
                except Exception:
                    pass
                logger.warning(f"MCP server '{server_id}' SSE process dead: {reason}")
        else:
            if process.poll() is not None:
                is_alive = False
                logger.warning(f"MCP server '{server_id}' process exited (code={process.returncode})")

        if is_alive:
            # Process alive — reset restart count on sustained health
            if server_id in self._restart_counts:
                # Reset after 5 minutes of healthy operation
                uptime = self._sm.get_uptime(server_id)
                if uptime and uptime > 300:
                    self._restart_counts.pop(server_id, None)
            return

        # Process is dead — always clean up DB state
        rc = getattr(process, "returncode", None)
        exit_code = rc if rc is not None else -1

        if server_id in self._restarts_in_progress:
            return

        # Get config to check restart policy
        config = await self._sm.db.get_server_config(server_id)
        if not config:
            # Config deleted — clean up stale state but don't restart
            op_lock = self._sm._get_operation_lock(server_id)
            async with op_lock:
                if self._sm.processes.get(server_id) is process:
                    await self._sm._cleanup_server(server_id, exit_code)
            return

        restart_policy = config.get("restart_policy", "on-failure")
        max_restarts = config.get("max_restarts", 3)

        should_restart = restart_policy in ("on-failure", "always")

        # on-failure: only restart on non-zero exit codes
        if restart_policy == "on-failure" and exit_code == 0:
            logger.info(f"MCP server '{server_id}' exited cleanly (code=0), not restarting")
            should_restart = False

        if should_restart and self._restart_counts.get(server_id, 0) >= max_restarts:
            logger.warning(f"MCP server '{server_id}' reached max restarts ({max_restarts})")
            should_restart = False

        if not should_restart:
            # Still clean up DB state even if not restarting
            op_lock = self._sm._get_operation_lock(server_id)
            async with op_lock:
                if self._sm.processes.get(server_id) is process:
                    await self._sm._cleanup_server(server_id, exit_code)
            return

        count = self._restart_counts.get(server_id, 0)

        # Mark in-progress BEFORE first await to prevent a concurrent monitor cycle
        # from triggering a second restart while sleeping/restarting
        self._restarts_in_progress.add(server_id)
        try:
            # Exponential backoff before acquiring lock
            delay = self._calculate_restart_delay(server_id)
            logger.info(f"Restarting MCP server '{server_id}' in {delay:.0f}s (attempt {count + 1}/{max_restarts})")
            await asyncio.sleep(delay)

            op_lock = self._sm._get_operation_lock(server_id)
            async with op_lock:
                # Re-check under lock — a manual restart during backoff may have replaced the process
                current = self._sm.processes.get(server_id)
                if current is not None and current is not process:
                    logger.info(f"MCP server '{server_id}' was restarted manually during backoff, skipping")
                    return
                await self._sm._cleanup_server(server_id, exit_code)
                success = await self._sm._start_server_unlocked(server_id, config)
            self._restart_counts[server_id] = count + 1
            if success:
                logger.info(f"MCP server '{server_id}' restarted successfully")
            else:
                logger.error(f"MCP server '{server_id}' failed to restart")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error restarting MCP server '{server_id}': {e}")
        finally:
            self._restarts_in_progress.discard(server_id)
