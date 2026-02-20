"""
Base interface for persistence backends.

This module defines the abstract interface that all persistence backends must implement.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class DuplicateKeyError(Exception):
    """
    Custom exception for duplicate key violations.

    This exception is raised when attempting to insert/update a document
    with a key that already exists in the persistence backend.

    Used by all backends (MongoDB, in-memory) to provide consistent error handling
    without requiring pymongo dependency for in-memory operations.
    """
    pass


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

        Raises:
            DuplicateKeyError: If server id already exists
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
    async def save_instance_state(self, state: Dict[str, Any]) -> bool:
        """
        Save server instance runtime state.

        Args:
            state: Instance state dict with fields like server_id, state, pid, etc.

        Returns:
            True if save successful
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

    # ==================== LLM Model Management ====================

    @abstractmethod
    async def save_llm_model(self, model_config: Dict[str, Any]) -> bool:
        """
        Register a new LLM model configuration.

        Args:
            model_config: Model configuration dict with 'model_id' and other fields

        Returns:
            True if saved successfully

        Raises:
            DuplicateKeyError: If model_id already exists
        """
        pass

    @abstractmethod
    async def get_llm_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve LLM model configuration by model_id.

        Args:
            model_id: Model identifier

        Returns:
            Model config dict or None if not found
        """
        pass

    @abstractmethod
    async def list_llm_models(self, filter_dict: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        List all LLM model configurations.

        Args:
            filter_dict: Optional filter (e.g., {"type": "replicate"})

        Returns:
            List of model configuration dicts
        """
        pass

    @abstractmethod
    async def delete_llm_model(self, model_id: str) -> bool:
        """
        Delete LLM model configuration.

        Args:
            model_id: Model identifier

        Returns:
            True if deletion successful, False if not found
        """
        pass

    @abstractmethod
    async def update_llm_model(self, model_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update LLM model configuration.

        Args:
            model_id: Model identifier
            updates: Fields to update

        Returns:
            True if update successful, False if not found
        """
        pass

    def supports_rollback(self) -> bool:
        """
        Check if this backend supports model rollback/versioning.

        Returns:
            True if rollback is supported (default: False)

        Note:
            Backends that support versioning should override this method to return True.
        """
        return False

    async def rollback_llm_model(self, model_id: str, version: Optional[int] = None) -> bool:
        """
        Rollback LLM model to a previous version.

        Args:
            model_id: Model identifier
            version: Specific version to rollback to (None = most recent)

        Returns:
            True if rollback successful

        Raises:
            NotImplementedError: If backend doesn't support versioning

        Note:
            This is an optional method. Backends without versioning support
            should not implement this (it will raise NotImplementedError by default).
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support model rollback/versioning")
