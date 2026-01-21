"""
Tool Registry for vLLM Function Calling.

This module manages registration and retrieval of tools/functions that can be
called by vLLM models during chat completion.
"""

import threading
from typing import Dict, List, Optional, Callable, Any
from loguru import logger


class ToolRegistry:
    """
    Registry for managing tools/functions available for vLLM function calling.

    This class maintains a registry of tools with their schemas and implementations,
    providing validation and conversion to OpenAI-compatible format.
    """

    def __init__(self):
        """Initialize the tool registry."""
        self.tools: Dict[str, Dict[str, Any]] = {}
        logger.debug("Tool registry initialized")

    def register(
        self,
        name: str,
        function: Callable,
        description: str,
        parameters: Dict[str, Any]
    ) -> None:
        """
        Register a new tool/function.

        Args:
            name: Unique identifier for the tool
            function: Callable that implements the tool logic
            description: Human-readable description of what the tool does
            parameters: JSON Schema defining the function parameters

        Raises:
            ValueError: If tool name already registered or schema is invalid
        """
        if name in self.tools:
            raise ValueError(f"Tool '{name}' is already registered")

        # Validate schema structure
        self._validate_schema(parameters)

        # Store tool with metadata
        self.tools[name] = {
            "function": function,
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters
                }
            }
        }

        logger.info(f"Registered tool: {name}")

    def unregister(self, name: str) -> None:
        """
        Unregister a tool.

        Args:
            name: Name of the tool to remove

        Raises:
            KeyError: If tool is not registered
        """
        if name not in self.tools:
            raise KeyError(f"Tool '{name}' is not registered")

        del self.tools[name]
        logger.info(f"Unregistered tool: {name}")

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a registered tool by name.

        Args:
            name: Name of the tool

        Returns:
            Tool dictionary with 'function' and 'schema', or None if not found
        """
        return self.tools.get(name)

    def get_function(self, name: str) -> Optional[Callable]:
        """
        Get the callable function for a tool.

        Args:
            name: Name of the tool

        Returns:
            The callable function, or None if tool not found
        """
        tool = self.get_tool(name)
        return tool["function"] if tool else None

    def list_tool_names(self) -> List[str]:
        """
        Get list of all registered tool names.

        Returns:
            List of tool names
        """
        return list(self.tools.keys())

    def list_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Get OpenAI-compatible tool schemas for all registered tools.

        Returns:
            List of tool schemas in OpenAI format
        """
        return [tool["schema"] for tool in self.tools.values()]

    def is_registered(self, name: str) -> bool:
        """
        Check if a tool is registered.

        Args:
            name: Name of the tool

        Returns:
            True if tool is registered, False otherwise
        """
        return name in self.tools

    def clear(self) -> None:
        """Clear all registered tools."""
        count = len(self.tools)
        self.tools.clear()
        logger.info(f"Cleared {count} tools from registry")

    def _validate_schema(self, parameters: Dict[str, Any]) -> None:
        """
        Validate that parameters follow JSON Schema format.

        Args:
            parameters: Parameters schema to validate

        Raises:
            ValueError: If schema is invalid
        """
        if not isinstance(parameters, dict):
            raise ValueError("Parameters must be a dictionary")

        # Check for required JSON Schema fields
        if "type" not in parameters:
            raise ValueError("Parameters schema must have 'type' field")

        if parameters["type"] != "object":
            raise ValueError("Parameters type must be 'object'")

        if "properties" not in parameters:
            raise ValueError("Parameters schema must have 'properties' field")

        if not isinstance(parameters["properties"], dict):
            raise ValueError("Properties must be a dictionary")

        # Validate required field if present
        if "required" in parameters:
            if not isinstance(parameters["required"], list):
                raise ValueError("Required must be a list")

            # Check that all required fields exist in properties
            for field in parameters["required"]:
                if field not in parameters["properties"]:
                    raise ValueError(
                        f"Required field '{field}' not found in properties"
                    )


# Global registry instance
_global_registry: Optional[ToolRegistry] = None
_registry_lock = threading.Lock()


def get_global_registry() -> ToolRegistry:
    """
    Get the global tool registry singleton.

    Returns:
        The global ToolRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            if _global_registry is None:  # Double-checked locking
                _global_registry = ToolRegistry()
    return _global_registry
