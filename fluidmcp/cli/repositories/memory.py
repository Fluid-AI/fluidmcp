"""
In-memory persistence backend.

Data is stored in Python dictionaries and lost on server restart.
Suitable for testing and development.
"""
import os
from typing import Dict, Any, List, Optional
from collections import deque, defaultdict
from datetime import datetime
from loguru import logger
from .base import PersistenceBackend


class InMemoryBackend(PersistenceBackend):
    """
    In-memory persistence backend.

    Data is stored in Python dictionaries and lost on server restart.
    Suitable for testing and development.
    """

    def __init__(self):
        """Initialize in-memory storage."""
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._instances: Dict[str, Dict[str, Any]] = {}
        self._logs: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._connected = False

    async def connect(self) -> bool:
        """No actual connection needed for in-memory."""
        logger.info("Using in-memory persistence (data will be lost on restart)")
        logger.warning("⚠️  In-memory mode: All server configurations and logs will be lost on restart")
        self._connected = True
        return True

    async def disconnect(self) -> None:
        """Clear in-memory data."""
        self._servers.clear()
        self._instances.clear()
        self._logs.clear()
        self._connected = False
        logger.info("Disconnected in-memory backend")

    async def save_server_config(self, config: Dict[str, Any]) -> bool:
        """Save config to memory."""
        config_id = config.get("id")
        if not config_id:
            logger.error("Cannot save config without 'id' field")
            return False

        # Make a deep copy to avoid mutations
        self._servers[config_id] = dict(config)
        logger.debug(f"Saved server config '{config_id}' to memory")
        return True

    async def get_server_config(self, id: str) -> Optional[Dict[str, Any]]:
        """Get config from memory."""
        config = self._servers.get(id)
        if config:
            # Return a copy to avoid mutations
            return dict(config)
        return None

    async def list_server_configs(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List configs from memory."""
        configs = list(self._servers.values())
        if enabled_only:
            configs = [c for c in configs if c.get("enabled", True)]
        # Return copies to avoid mutations
        return [dict(c) for c in configs]

    async def delete_server_config(self, id: str) -> bool:
        """Delete config from memory."""
        if id in self._servers:
            del self._servers[id]
            logger.debug(f"Deleted server config '{id}' from memory")
            return True
        logger.warning(f"Server config '{id}' not found in memory")
        return False

    async def save_instance_state(self, state: Dict[str, Any], expected_pid: Optional[int] = None) -> bool:
        """Save instance state to memory."""
        server_id = state.get("server_id")
        if not server_id:
            logger.error("Cannot save instance state without 'server_id' field")
            return False

        # Optimistic locking: check if PID matches if expected_pid is provided
        if expected_pid is not None:
            current_state = self._instances.get(server_id)
            if current_state and current_state.get("pid") != expected_pid:
                logger.debug(f"Optimistic lock failed for {server_id}: PID changed from {expected_pid}")
                return False

        # Make a deep copy to avoid mutations
        self._instances[server_id] = dict(state)
        logger.debug(f"Saved instance state for '{server_id}' to memory")
        return True

    async def get_instance_state(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Get instance state from memory."""
        state = self._instances.get(server_id)
        if state:
            # Return a copy to avoid mutations
            return dict(state)
        return None

    async def save_log_entry(self, log_entry: Dict[str, Any]) -> None:
        """Save log to memory (capped at 1000 lines per server)."""
        server_name = log_entry.get("server_name")
        if server_name:
            # Global memory limit check
            total_logs = sum(len(logs) for logs in self._logs.values())
            max_total_logs = int(os.getenv("FMCP_MAX_MEMORY_LOGS", "10000"))

            if total_logs >= max_total_logs:
                # Remove oldest logs from the server with most logs
                if self._logs:
                    largest_server = max(self._logs.items(), key=lambda x: len(x[1]))[0]
                    if self._logs[largest_server]:
                        self._logs[largest_server].popleft()
                        logger.warning(
                            f"Memory log limit reached ({max_total_logs}), "
                            f"removed oldest log from {largest_server}"
                        )

            self._logs[server_name].append(dict(log_entry))

    async def get_logs(self, server_name: str, lines: int = 100) -> List[Dict[str, Any]]:
        """Get recent logs from memory."""
        logs = list(self._logs.get(server_name, []))
        # Return most recent 'lines' logs
        return logs[-lines:] if logs else []
