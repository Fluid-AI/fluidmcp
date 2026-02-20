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
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
from loguru import logger

from ..repositories.database import DatabaseManager
from .package_launcher import initialize_mcp_server
from .metrics import MetricsCollector


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

            # Spawn the MCP process
            logger.info(f"Starting server '{name}' (id: {id})...")
            process = await self._spawn_mcp_process(id, config)

            if not process:
                logger.error(f"Failed to spawn process for server '{name}' (id: {id})")
                return False

            # Store process
            self.processes[id] = process
            logger.info(f"Server '{name}' started (PID: {process.pid})")

            # Save state to database with user tracking
            await self.db.save_instance_state({
                "server_id": id,
                "state": "running",
                "pid": process.pid,
                "start_time": datetime.utcnow(),
                "stop_time": None,
                "exit_code": None,
                "restart_count": 0,
                "last_health_check": datetime.utcnow(),
                "health_check_failures": 0,
                "started_by": user_id  # Track who started this instance
            })

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
                await self._cleanup_server(id, process.returncode)
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
            await self._cleanup_server(id, exit_code)

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
            return {
                "id": id,
                "state": instance.get("state", "unknown"),
                "pid": instance.get("pid"),
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

    async def list_servers(self) -> List[Dict[str, Any]]:
        """
        List all configured servers with their status.

        Returns:
            List of server info dictionaries with nested config structure
        """
        servers = []

        # Get all configs from database
        configs = await self.db.list_server_configs()

        # Merge with in-memory configs (for servers not in DB)
        config_ids = {c.get("id") for c in configs}
        for id, config in self.configs.items():
            if id not in config_ids:
                configs.append(config)

        for config in configs:
            id = config.get("id")
            status = await self.get_server_status(id)

            # Separate MCP config fields from metadata fields
            mcp_config = {
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
            cmd_list = [command] + args

            # Merge environment variables (shell env takes precedence)
            env = dict(os.environ)
            for key, value in env_vars.items():
                if key not in env and value and not self._is_placeholder(value):
                    env[key] = value

            # Determine working directory
            working_dir = Path(working_dir).resolve() if working_dir else Path(install_path).resolve()

            logger.debug(f"Spawning process: {cmd_list}")
            logger.debug(f"Working directory: {working_dir}")

            # Spawn subprocess
            process = subprocess.Popen(
                cmd_list,
                cwd=str(working_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1
            )

            # Give process a moment to start
            await asyncio.sleep(0.5)

            # Check if process is still alive
            if process.poll() is not None:
                stderr_output = "No stderr available"
                if process.stderr:
                    try:
                        stderr_output = await asyncio.to_thread(process.stderr.read)
                    except Exception as exc:
                        logger.exception(f"Failed to read stderr: {exc}")
                logger.error(f"Process died immediately after spawn. stderr: {stderr_output}")
                return None

            # Initialize MCP server with handshake (using shared utility)
            logger.info(f"[{id}] Initializing MCP server...")
            init_success = await asyncio.to_thread(initialize_mcp_server, process)

            if not init_success:
                logger.error(f"MCP initialization failed for server '{name}' (id: {id})")
                # Read stderr for debugging (non-blocking)
                stderr_output = None
                if process.stderr:
                    try:
                        stderr_output = await asyncio.wait_for(
                            asyncio.to_thread(process.stderr.read),
                            timeout=1.0
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to read stderr: {exc}")
                if stderr_output:
                    logger.error(f"[{id}] Process stderr: {stderr_output[:500]}")
                process.kill()
                return None

            logger.info(f"[{id}] MCP server initialized successfully")

            # Discover and cache tools (PDF spec requirement)
            await self._discover_and_cache_tools(id, process)

            return process

        except Exception as e:
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

    async def _cleanup_server(self, id: str, exit_code: int) -> None:
        """
        Clean up after server stops.

        Args:
            id: Server identifier
            exit_code: Process exit code
        """
        # Remove from registry
        if id in self.processes:
            del self.processes[id]
        if id in self.start_times:
            del self.start_times[id]

        # Update database
        await self.db.save_instance_state({
            "server_id": id,
            "state": "stopped",
            "pid": None,
            "stop_time": datetime.utcnow(),
            "exit_code": exit_code
        })

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
