"""
Tool Executor for vLLM Function Calling.

This module handles the execution of tools/functions called by vLLM models,
including validation, timeout handling, and error management.
"""

import asyncio
import json
from typing import Dict, Any, Optional
from loguru import logger

from .tool_registry import ToolRegistry
from .metrics import MetricsCollector, ToolTimer


class ToolExecutor:
    """
    Executor for running tools called by vLLM models.

    This class handles tool execution with safety controls including:
    - Allowlist validation
    - Timeout enforcement
    - Call depth limiting
    - Error normalization
    - Metrics tracking
    """

    def __init__(
        self,
        registry: ToolRegistry,
        model_id: str,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the tool executor.

        Args:
            registry: ToolRegistry instance containing registered tools
            model_id: Identifier for the model using this executor
            config: Configuration dict with safety settings
        """
        self.registry = registry
        self.model_id = model_id
        self.config = config or {}

        # Safety settings
        self.allowed_tools = self.config.get("allowed_tools", [])
        self.timeout_per_tool = self.config.get("timeout_per_tool", 10)
        self.max_call_depth = self.config.get("max_call_depth", 3)

        # Metrics
        self.metrics = MetricsCollector(model_id)

        logger.debug(
            f"Tool executor initialized for model '{model_id}' "
            f"(allowed_tools={self.allowed_tools}, "
            f"timeout={self.timeout_per_tool}s, "
            f"max_depth={self.max_call_depth})"
        )

    async def execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        depth: int = 0
    ) -> Dict[str, Any]:
        """
        Execute a single tool call from the model.

        Args:
            tool_call: Tool call dict with 'id', 'type', 'function' fields
            depth: Current call depth (for recursion limiting)

        Returns:
            Dict with tool execution result or error
        """
        tool_call_id = tool_call.get("id", "unknown")
        function_data = tool_call.get("function", {})
        function_name = function_data.get("name", "unknown")

        logger.info(
            f"Executing tool call '{tool_call_id}' "
            f"(function={function_name}, depth={depth})"
        )

        # Track with metrics
        with ToolTimer(self.metrics, function_name):
            # Check call depth limit
            if depth >= self.max_call_depth:
                logger.warning(
                    f"Tool call depth limit exceeded: {depth} >= {self.max_call_depth}"
                )
                return self._error_response(
                    tool_call_id,
                    function_name,
                    "Maximum call depth exceeded"
                )

            # Validate tool is allowed
            if not self._is_tool_allowed(function_name):
                logger.warning(f"Tool '{function_name}' not in allowlist")
                return self._error_response(
                    tool_call_id,
                    function_name,
                    f"Tool '{function_name}' is not allowed"
                )

            # Get tool from registry
            tool = self.registry.get_tool(function_name)
            if not tool:
                logger.error(f"Tool '{function_name}' not found in registry")
                return self._error_response(
                    tool_call_id,
                    function_name,
                    f"Tool '{function_name}' not found"
                )

            # Parse arguments
            try:
                arguments_str = function_data.get("arguments", "{}")
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool arguments: {e}")
                return self._error_response(
                    tool_call_id,
                    function_name,
                    f"Invalid JSON arguments: {str(e)}"
                )

            # Execute tool with timeout
            try:
                function = tool["function"]
                result = await self._execute_with_timeout(
                    function,
                    arguments,
                    function_name
                )

                logger.info(f"Tool '{function_name}' executed successfully")
                return self._success_response(tool_call_id, function_name, result)

            except asyncio.TimeoutError:
                logger.error(
                    f"Tool '{function_name}' execution timed out "
                    f"after {self.timeout_per_tool}s"
                )
                self.metrics.record_error("tool_timeout")
                return self._error_response(
                    tool_call_id,
                    function_name,
                    f"Tool execution timeout ({self.timeout_per_tool}s)"
                )

            except Exception as e:
                logger.exception(f"Tool '{function_name}' execution failed: {e}")
                self.metrics.record_error("tool_execution_error")
                return self._error_response(
                    tool_call_id,
                    function_name,
                    f"Tool execution error: {str(e)}"
                )

    async def execute_tool_calls(
        self,
        tool_calls: list[Dict[str, Any]],
        depth: int = 0
    ) -> list[Dict[str, Any]]:
        """
        Execute multiple tool calls in parallel.

        Args:
            tool_calls: List of tool call dicts
            depth: Current call depth

        Returns:
            List of execution results
        """
        if not tool_calls:
            return []

        logger.info(f"Executing {len(tool_calls)} tool calls in parallel")

        # Execute all tool calls concurrently
        tasks = [
            self.execute_tool_call(tool_call, depth)
            for tool_call in tool_calls
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error responses
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tool_call = tool_calls[i]
                tool_call_id = tool_call.get("id", "unknown")
                function_name = tool_call.get("function", {}).get("name", "unknown")
                processed_results.append(
                    self._error_response(
                        tool_call_id,
                        function_name,
                        f"Unexpected error: {str(result)}"
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    async def _execute_with_timeout(
        self,
        function: callable,
        arguments: Dict[str, Any],
        function_name: str
    ) -> Any:
        """
        Execute function with timeout.

        Args:
            function: Callable to execute
            arguments: Arguments to pass
            function_name: Name for logging

        Returns:
            Function result

        Raises:
            asyncio.TimeoutError: If execution exceeds timeout
        """
        logger.debug(
            f"Executing function '{function_name}' "
            f"with timeout {self.timeout_per_tool}s"
        )

        # Check if function is async or sync
        if asyncio.iscoroutinefunction(function):
            # Async function - await with timeout
            result = await asyncio.wait_for(
                function(**arguments),
                timeout=self.timeout_per_tool
            )
        else:
            # Sync function - run in executor with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: function(**arguments)),
                timeout=self.timeout_per_tool
            )

        return result

    def _is_tool_allowed(self, tool_name: str) -> bool:
        """
        Check if tool is in allowlist.

        Args:
            tool_name: Name of the tool

        Returns:
            True if allowed (or no allowlist configured), False otherwise
        """
        # If no allowlist configured, allow all registered tools
        if not self.allowed_tools:
            return True

        return tool_name in self.allowed_tools

    def _success_response(
        self,
        tool_call_id: str,
        function_name: str,
        result: Any
    ) -> Dict[str, Any]:
        """
        Format successful tool execution response.

        Args:
            tool_call_id: ID of the tool call
            function_name: Name of the function
            result: Execution result

        Returns:
            Formatted response dict
        """
        # Convert result to string if not already
        if not isinstance(result, str):
            result = json.dumps(result)

        return {
            "tool_call_id": tool_call_id,
            "role": "tool",
            "name": function_name,
            "content": result
        }

    def _error_response(
        self,
        tool_call_id: str,
        function_name: str,
        error_message: str
    ) -> Dict[str, Any]:
        """
        Format error response for failed tool execution.

        Args:
            tool_call_id: ID of the tool call
            function_name: Name of the function
            error_message: Error description

        Returns:
            Formatted error response dict
        """
        return {
            "tool_call_id": tool_call_id,
            "role": "tool",
            "name": function_name,
            "content": json.dumps({
                "error": True,
                "message": error_message
            })
        }
