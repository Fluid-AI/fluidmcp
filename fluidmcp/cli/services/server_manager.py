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
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
from loguru import logger

from ..repositories.database import DatabaseManager
from .package_launcher import initialize_mcp_server


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

        # Event loop for async operations
        self._loop = None

    # ==================== Server Lifecycle Methods ====================

    async def start_server(self, id: str, config: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None) -> bool:
        """
        Start an MCP server.

        Args:
            id: Unique server identifier
            config: Server configuration (if None, loads from database)
            user_id: User who is starting the server (for tracking)

        Returns:
            True if started successfully, False otherwise
        """
        # Initialize name early for exception handler
        name = id
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

            return True

        except Exception as e:
            logger.exception(f"Error starting server '{name}' (id: {id}): {e}")

            # Save error to instance state (PDF spec: last_error field)
            await self.db.save_instance_state({
                "server_id": id,
                "state": "failed",
                "last_error": str(e)
            })

            return False

    async def stop_server(self, id: str, force: bool = False) -> bool:
        """
        Stop a running MCP server.

        Args:
            id: Server identifier
            force: If True, use SIGKILL instead of SIGTERM

        Returns:
            True if stopped successfully, False otherwise
        """
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
            return True

        except Exception as e:
            logger.exception(f"Error stopping server '{id}': {e}")
            return False

    async def restart_server(self, id: str) -> bool:
        """
        Restart an MCP server.

        Args:
            id: Server identifier

        Returns:
            True if restarted successfully
        """
        # Get current config before stopping
        config = self.configs.get(id)
        if not config:
            config = await self.db.get_server_config(id)

        # Get display name
        name = config.get("name", id) if config else id
        logger.info(f"Restarting server '{name}' (id: {id})...")

        # Stop server
        if id in self.processes:
            await self.stop_server(id)

        # Increment restart count
        instance = await self.db.get_instance_state(id)
        restart_count = instance.get("restart_count", 0) if instance else 0

        # Update config with new restart count
        if config:
            config["_restart_count"] = restart_count + 1

        # Start server
        success = await self.start_server(id, config)

        if success:
            # Update restart count in database
            await self.db.save_instance_state({
                "server_id": id,
                "restart_count": restart_count + 1
            })

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
                        await self.db.save_server_config(config)
                        logger.info(f"Discovered and cached {len(tools)} tools for server '{server_id}'")
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

        # Update database
        await self.db.save_instance_state({
            "server_id": id,
            "state": "stopped",
            "pid": None,
            "stop_time": datetime.utcnow(),
            "exit_code": exit_code
        })

        logger.info(f"Cleaned up server '{id}'")

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
