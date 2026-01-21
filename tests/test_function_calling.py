"""
Unit tests for vLLM function calling components.

Tests cover:
- ToolRegistry
- ToolExecutor
- FunctionRouter
- Integration scenarios
- Safety controls
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock

from fluidmcp.cli.services.tool_registry import ToolRegistry, get_global_registry
from fluidmcp.cli.services.tool_executor import ToolExecutor
from fluidmcp.cli.services.function_router import FunctionRouter


# Test fixtures

@pytest.fixture
def registry():
    """Create a fresh ToolRegistry for each test."""
    return ToolRegistry()


@pytest.fixture
def sample_tool_function():
    """Sample synchronous tool function."""
    def get_weather(city: str) -> dict:
        return {"city": city, "temperature": 25, "condition": "sunny"}
    return get_weather


@pytest.fixture
def async_sample_tool():
    """Sample async tool function."""
    async def search(query: str) -> dict:
        await asyncio.sleep(0.01)  # Simulate async work
        return {"query": query, "results": ["result1", "result2"]}
    return search


@pytest.fixture
def sample_tool_schema():
    """Sample tool parameter schema."""
    return {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name"
            }
        },
        "required": ["city"]
    }


# ToolRegistry Tests

class TestToolRegistry:
    """Test cases for ToolRegistry."""

    def test_register_tool(self, registry, sample_tool_function, sample_tool_schema):
        """Test registering a new tool."""
        registry.register(
            name="get_weather",
            function=sample_tool_function,
            description="Get weather for a city",
            parameters=sample_tool_schema
        )

        assert registry.is_registered("get_weather")
        assert "get_weather" in registry.list_tool_names()

    def test_register_duplicate_tool_raises_error(self, registry, sample_tool_function, sample_tool_schema):
        """Test that registering duplicate tool raises ValueError."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Description",
            sample_tool_schema
        )

        with pytest.raises(ValueError, match="already registered"):
            registry.register(
                "get_weather",
                sample_tool_function,
                "Description",
                sample_tool_schema
            )

    def test_get_tool(self, registry, sample_tool_function, sample_tool_schema):
        """Test retrieving a registered tool."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        tool = registry.get_tool("get_weather")
        assert tool is not None
        assert tool["function"] == sample_tool_function
        assert "schema" in tool

    def test_get_nonexistent_tool_returns_none(self, registry):
        """Test that getting nonexistent tool returns None."""
        assert registry.get_tool("nonexistent") is None

    def test_unregister_tool(self, registry, sample_tool_function, sample_tool_schema):
        """Test unregistering a tool."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        registry.unregister("get_weather")
        assert not registry.is_registered("get_weather")

    def test_unregister_nonexistent_tool_raises_error(self, registry):
        """Test that unregistering nonexistent tool raises KeyError."""
        with pytest.raises(KeyError):
            registry.unregister("nonexistent")

    def test_list_tool_schemas(self, registry, sample_tool_function, sample_tool_schema):
        """Test listing all tool schemas."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        schemas = registry.list_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "get_weather"

    def test_clear_registry(self, registry, sample_tool_function, sample_tool_schema):
        """Test clearing all tools from registry."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        registry.clear()
        assert len(registry.list_tool_names()) == 0

    def test_invalid_schema_missing_type(self, registry, sample_tool_function):
        """Test that invalid schema (missing type) raises ValueError."""
        invalid_schema = {"properties": {}}

        with pytest.raises(ValueError, match="must have 'type' field"):
            registry.register(
                "invalid_tool",
                sample_tool_function,
                "Invalid",
                invalid_schema
            )

    def test_invalid_schema_wrong_type(self, registry, sample_tool_function):
        """Test that invalid schema (wrong type) raises ValueError."""
        invalid_schema = {"type": "string", "properties": {}}

        with pytest.raises(ValueError, match="type must be 'object'"):
            registry.register(
                "invalid_tool",
                sample_tool_function,
                "Invalid",
                invalid_schema
            )

    def test_global_registry_singleton(self):
        """Test that global registry is a singleton."""
        # Reset global registry to ensure clean state
        import fluidmcp.cli.services.tool_registry as registry_module
        registry_module._global_registry = None

        registry1 = get_global_registry()
        registry2 = get_global_registry()
        assert registry1 is registry2

        # Clean up after test
        registry_module._global_registry = None


# ToolExecutor Tests

class TestToolExecutor:
    """Test cases for ToolExecutor."""

    @pytest.mark.asyncio
    async def test_execute_tool_call_success(self, registry, sample_tool_function, sample_tool_schema):
        """Test successful tool execution."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        executor = ToolExecutor(registry, "test_model")

        tool_call = {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{"city": "Bangalore"}'
            }
        }

        result = await executor.execute_tool_call(tool_call)

        assert result["tool_call_id"] == "call_123"
        assert result["role"] == "tool"
        assert result["name"] == "get_weather"
        assert "Bangalore" in result["content"]

    @pytest.mark.asyncio
    async def test_execute_tool_call_not_in_allowlist(self, registry, sample_tool_function, sample_tool_schema):
        """Test that tool not in allowlist is rejected."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        config = {"allowed_tools": ["other_tool"]}
        executor = ToolExecutor(registry, "test_model", config)

        tool_call = {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{}'
            }
        }

        result = await executor.execute_tool_call(tool_call)

        content = json.loads(result["content"])
        assert content["error"] is True
        assert "not allowed" in content["message"]

    @pytest.mark.asyncio
    async def test_execute_tool_call_invalid_json_arguments(self, registry, sample_tool_function, sample_tool_schema):
        """Test handling of invalid JSON arguments."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        executor = ToolExecutor(registry, "test_model")

        tool_call = {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": 'invalid json'
            }
        }

        result = await executor.execute_tool_call(tool_call)

        content = json.loads(result["content"])
        assert content["error"] is True
        assert "Invalid JSON" in content["message"]

    @pytest.mark.asyncio
    async def test_execute_tool_call_timeout(self, registry, sample_tool_schema):
        """Test tool execution timeout."""
        async def slow_function(city: str):
            await asyncio.sleep(10)  # Will timeout
            return {"city": city}

        registry.register(
            "slow_tool",
            slow_function,
            "Slow tool",
            sample_tool_schema
        )

        config = {"timeout_per_tool": 0.1}  # 100ms timeout
        executor = ToolExecutor(registry, "test_model", config)

        tool_call = {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "slow_tool",
                "arguments": '{"city": "Test"}'
            }
        }

        result = await executor.execute_tool_call(tool_call)

        content = json.loads(result["content"])
        assert content["error"] is True
        assert "timeout" in content["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_tool_call_max_depth(self, registry, sample_tool_function, sample_tool_schema):
        """Test max call depth limit."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        config = {"max_call_depth": 2}
        executor = ToolExecutor(registry, "test_model", config)

        tool_call = {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{"city": "Test"}'
            }
        }

        # Execute at depth 2 (should succeed)
        result = await executor.execute_tool_call(tool_call, depth=1)
        content = json.loads(result["content"])
        assert "error" not in content or not content.get("error")

        # Execute at depth 2 (should fail - at limit)
        result = await executor.execute_tool_call(tool_call, depth=2)
        content = json.loads(result["content"])
        assert content["error"] is True
        assert "depth" in content["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_multiple_tool_calls(self, registry, sample_tool_function, sample_tool_schema):
        """Test executing multiple tool calls in parallel."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        executor = ToolExecutor(registry, "test_model")

        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "Bangalore"}'
                }
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "Mumbai"}'
                }
            }
        ]

        results = await executor.execute_tool_calls(tool_calls)

        assert len(results) == 2
        assert results[0]["tool_call_id"] == "call_1"
        assert results[1]["tool_call_id"] == "call_2"

    @pytest.mark.asyncio
    async def test_execute_async_tool(self, registry, async_sample_tool):
        """Test executing async tool function."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }

        registry.register(
            "search",
            async_sample_tool,
            "Search tool",
            schema
        )

        executor = ToolExecutor(registry, "test_model")

        tool_call = {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": '{"query": "test"}'
            }
        }

        result = await executor.execute_tool_call(tool_call)

        assert result["role"] == "tool"
        assert "test" in result["content"]


# FunctionRouter Tests

class TestFunctionRouter:
    """Test cases for FunctionRouter."""

    @pytest.mark.asyncio
    async def test_extract_tool_calls_from_response(self, registry):
        """Test extracting tool calls from vLLM response."""
        router = FunctionRouter(registry, "test_model")

        response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city": "Test"}'
                            }
                        }
                    ]
                }
            }]
        }

        tool_calls = router._extract_tool_calls(response)

        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "call_123"
        assert tool_calls[0]["function"]["name"] == "get_weather"

    @pytest.mark.asyncio
    async def test_extract_tool_calls_no_calls(self, registry):
        """Test extracting when response has no tool calls."""
        router = FunctionRouter(registry, "test_model")

        response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Just a regular response"
                }
            }]
        }

        tool_calls = router._extract_tool_calls(response)

        assert len(tool_calls) == 0

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self, registry, sample_tool_function, sample_tool_schema):
        """Test that max iterations limit is enforced."""
        registry.register(
            "get_weather",
            sample_tool_function,
            "Get weather",
            sample_tool_schema
        )

        config = {"max_iterations": 2}
        router = FunctionRouter(registry, "test_model", config)

        # Mock vLLM client that always returns tool calls
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "Test"}'
                        }
                    }]
                }
            }]
        })

        messages = [{"role": "user", "content": "What's the weather?"}]

        # Should stop after max_iterations
        await router.handle_completion(
            messages,
            mock_client,
            stream=False
        )

        # Verify it was called but stopped at limit
        assert mock_client.chat.completions.create.call_count <= config["max_iterations"] + 1


# Integration Tests

class TestIntegration:
    """Integration tests for complete function calling flow."""

    @pytest.mark.asyncio
    async def test_complete_function_calling_flow(self, registry):
        """Test complete flow: register tool -> call model -> execute tool -> final answer."""
        # Register tool
        def calculator(operation: str, x: float, y: float) -> dict:
            if operation == "add":
                result = x + y
            elif operation == "multiply":
                result = x * y
            else:
                result = 0
            return {"result": result}

        schema = {
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "x": {"type": "number"},
                "y": {"type": "number"}
            },
            "required": ["operation", "x", "y"]
        }

        registry.register(
            "calculator",
            calculator,
            "Perform calculations",
            schema
        )

        # Create router
        router = FunctionRouter(registry, "test_model")

        # Mock vLLM client with two-stage response
        call_count = 0
        max_expected_calls = 2

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1

            # Safety check: prevent infinite calls if router logic fails
            if call_count > max_expected_calls:
                pytest.fail(
                    f"Mock called {call_count} times, expected max {max_expected_calls}. "
                    f"Router may not be stopping correctly."
                )

            if call_count == 1:
                # First call: return tool call
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "call_123",
                                "type": "function",
                                "function": {
                                    "name": "calculator",
                                    "arguments": '{"operation": "add", "x": 5, "y": 3}'
                                }
                            }]
                        }
                    }]
                }
            else:
                # Second call: return final answer
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": "The answer is 8"
                        }
                    }]
                }

        mock_client = AsyncMock()
        mock_client.chat.completions.create = mock_create

        # Execute
        messages = [{"role": "user", "content": "What is 5 + 3?"}]
        result = await router.handle_completion(
            messages,
            mock_client,
            stream=False
        )

        # Verify final answer
        assert "answer" in result["choices"][0]["message"]["content"].lower()
        assert call_count == 2  # Two model calls


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
