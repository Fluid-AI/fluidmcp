"""
Function Router for vLLM Function Calling.

This module routes function calls between vLLM models and tool executors,
managing the conversation flow with tool results.
"""

from typing import Dict, List, Any, Optional
from loguru import logger

from .tool_registry import ToolRegistry
from .tool_executor import ToolExecutor


class FunctionRouter:
    """
    Router for managing function calling flow between vLLM and tools.

    This class handles:
    - Parsing tool calls from vLLM responses
    - Routing tool calls to executors
    - Injecting tool results back into conversation
    - Loop detection
    - Streaming support
    """

    def __init__(
        self,
        registry: ToolRegistry,
        model_id: str,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the function router.

        Args:
            registry: ToolRegistry instance
            model_id: Model identifier
            config: Configuration dict with safety settings
        """
        self.registry = registry
        self.model_id = model_id
        self.config = config or {}

        # Create executor
        self.executor = ToolExecutor(registry, model_id, config)

        # Loop detection
        self.max_iterations = self.config.get("max_iterations", 5)

        logger.debug(
            f"Function router initialized for model '{model_id}' "
            f"(max_iterations={self.max_iterations})"
        )

    async def handle_completion(
        self,
        messages: List[Dict[str, Any]],
        vllm_client: Any,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        stream: bool = False,
        **completion_kwargs
    ) -> Dict[str, Any]:
        """
        Handle chat completion with function calling support.

        Args:
            messages: Conversation messages
            vllm_client: vLLM client instance
            tools: Tool definitions (optional, uses registry if not provided)
            tool_choice: Tool choice mode ("auto", "none", or specific tool)
            stream: Whether to stream response
            **completion_kwargs: Additional completion parameters

        Returns:
            Final completion response with all tool calls resolved
        """
        # Use tools from registry if not provided
        if tools is None and tool_choice != "none":
            tools = self.registry.list_tool_schemas()

        # If no tools available or tool_choice is "none", do normal completion
        if not tools or tool_choice == "none":
            logger.debug("No tools available or tool_choice=none, doing normal completion")
            return await self._call_vllm(
                vllm_client,
                messages,
                stream=stream,
                **completion_kwargs
            )

        # Iteration loop for multi-turn tool calling
        current_messages = messages.copy()
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            logger.debug(f"Function calling iteration {iteration}/{self.max_iterations}")

            # Call vLLM with tools
            response = await self._call_vllm(
                vllm_client,
                current_messages,
                tools=tools,
                tool_choice=tool_choice,
                stream=stream,
                **completion_kwargs
            )

            # Check if model made tool calls
            tool_calls = self._extract_tool_calls(response)

            if not tool_calls:
                # No tool calls, return final response
                logger.info("No tool calls in response, returning final answer")
                return response

            logger.info(f"Model requested {len(tool_calls)} tool calls")

            # Add assistant message with tool calls to conversation
            assistant_message = {
                "role": "assistant",
                "content": response.get("choices", [{}])[0].get("message", {}).get("content"),
                "tool_calls": tool_calls
            }
            current_messages.append(assistant_message)

            # Execute tool calls
            tool_results = await self.executor.execute_tool_calls(
                tool_calls,
                depth=iteration - 1
            )

            # Add tool results to conversation
            for tool_result in tool_results:
                current_messages.append(tool_result)

            logger.debug(
                f"Added {len(tool_results)} tool results, "
                f"continuing to next iteration"
            )

            # Set tool_choice to "none" for subsequent calls
            # (model should now use tool results to provide final answer)
            tool_choice = "none"

        # Max iterations reached
        logger.warning(
            f"Max iterations ({self.max_iterations}) reached, "
            f"returning last response"
        )

        return response

    async def _call_vllm(
        self,
        vllm_client: Any,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call vLLM completion API.

        Args:
            vllm_client: vLLM client instance
            messages: Conversation messages
            tools: Tool schemas
            tool_choice: Tool choice mode
            stream: Whether to stream
            **kwargs: Additional completion parameters

        Returns:
            vLLM completion response
        """
        request_params = {
            "model": self.model_id,
            "messages": messages,
            "stream": stream,
            **kwargs
        }

        # Add tools if provided
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = tool_choice

        logger.debug(f"Calling vLLM with {len(messages)} messages")

        # Call vLLM (implementation depends on your vLLM client)
        # This is a placeholder - replace with actual vLLM client call
        if hasattr(vllm_client, 'chat') and hasattr(vllm_client.chat, 'completions'):
            # OpenAI-compatible client
            if stream:
                return await vllm_client.chat.completions.create(**request_params)
            else:
                response = await vllm_client.chat.completions.create(**request_params)
                return response.model_dump() if hasattr(response, 'model_dump') else dict(response)
        else:
            # Direct HTTP call
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{vllm_client.base_url}/v1/chat/completions",
                    json=request_params,
                    headers={"Authorization": f"Bearer {vllm_client.api_key}"}
                    if hasattr(vllm_client, 'api_key') else None
                )
                response.raise_for_status()
                return response.json()

    def _extract_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract tool calls from vLLM response.

        Args:
            response: vLLM completion response

        Returns:
            List of tool call dicts, or empty list if none
        """
        try:
            choices = response.get("choices", [])
            if not choices:
                return []

            message = choices[0].get("message", {})
            tool_calls = message.get("tool_calls", [])

            if tool_calls:
                logger.debug(f"Extracted {len(tool_calls)} tool calls from response")
                return tool_calls
            else:
                return []

        except (KeyError, IndexError, TypeError) as e:
            logger.warning(f"Failed to extract tool calls from response: {e}")
            return []

    def parse_streaming_tool_call(self, delta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse tool call from streaming delta.

        Args:
            delta: Streaming delta chunk

        Returns:
            Parsed tool call if complete, None otherwise
        """
        # For streaming, tool calls may come incrementally
        # This is a simplified implementation - you may need to accumulate chunks
        tool_calls = delta.get("tool_calls", [])
        if tool_calls:
            return tool_calls[0]
        return None


def create_function_router(
    model_id: str,
    config: Optional[Dict[str, Any]] = None
) -> FunctionRouter:
    """
    Factory function to create a FunctionRouter with global registry.

    Args:
        model_id: Model identifier
        config: Configuration dict

    Returns:
        Configured FunctionRouter instance
    """
    from .tool_registry import get_global_registry
    registry = get_global_registry()
    return FunctionRouter(registry, model_id, config)
