"""
Base interface for persistence backends.

This module defines the abstract interface that all persistence backends must implement.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class PersistenceBackend(ABC):
    """Abstract base class for persistence backends."""

    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to persistence backend.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from persistence backend and cleanup resources."""
        pass

    @abstractmethod
    async def save_server_config(self, config: Dict[str, Any]) -> bool:
        """
        Save server configuration.

        Args:
            config: Server configuration dict with fields like id, name, mcp_config, etc.

        Returns:
            True if save successful
        """
        pass

    @abstractmethod
    async def get_server_config(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Get server configuration by ID.

        Args:
            id: Unique server identifier

        Returns:
            Server config dict or None if not found
        """
        pass

    @abstractmethod
    async def list_server_configs(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """
        List all server configurations.

        Args:
            enabled_only: If True, only return enabled servers

        Returns:
            List of server configuration dicts
        """
        pass

    @abstractmethod
    async def delete_server_config(self, id: str) -> bool:
        """
        Delete server configuration.

        Args:
            id: Server identifier

        Returns:
            True if deletion successful
        """
        pass

    @abstractmethod
    async def save_instance_state(self, state: Dict[str, Any], expected_pid: Optional[int] = None) -> bool:
        """
        Save server instance runtime state.

        Args:
            state: Instance state dict with fields like server_id, state, pid, etc.
            expected_pid: Optional PID for optimistic locking. Update only if current PID matches.

        Returns:
            True if save successful (or False if optimistic lock failed)
        """
        pass

    @abstractmethod
    async def get_instance_state(self, server_id: str) -> Optional[Dict[str, Any]]:
        """
        Get server instance state.

        Args:
            server_id: Server identifier

        Returns:
            Instance state dict or None if not found
        """
        pass

    @abstractmethod
    async def save_log_entry(self, log_entry: Dict[str, Any]) -> None:
        """
        Save log entry.

        Args:
            log_entry: Log entry dict with fields like server_name, timestamp, stream, content
        """
        pass

    @abstractmethod
    async def get_logs(self, server_name: str, lines: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent logs for server.

        Args:
            server_name: Server name
            lines: Maximum number of log lines to return

        Returns:
            List of log entry dicts, most recent last
        """
        pass
