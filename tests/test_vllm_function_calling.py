"""
Integration tests for vLLM function calling pass-through.

These tests verify that FluidMCP correctly forwards `tools` and `tool_choice`
parameters to vLLM and returns the response unchanged (Mode 1: pass-through).
"""

import pytest
from unittest.mock import AsyncMock, patch, Mock


class TestVLLMFunctionCallingPassThrough:
    """Test that tools parameter is passed through to vLLM unchanged."""

    @pytest.mark.asyncio
    async def test_tools_parameter_forwarded_to_vllm(self):
        """Test that tools array is included in request to vLLM backend."""
        # Mock vLLM response with tool_calls
        mock_vllm_response = {
            "id": "chatcmpl-test123",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_abc",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "San Francisco"}'
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        }

        # Create mock HTTP client
        mock_response = Mock()
        mock_response.json.return_value = mock_vllm_response
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        # Mock model config
        mock_config = {
            "base_url": "http://localhost:8000",
            "chat": "/v1/chat/completions"
        }

        # Patch _get_http_client and _llm_endpoints
        with patch('fluidmcp.cli.services.run_servers._get_http_client') as mock_get_client:
            with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {"test-model": mock_config}):
                with patch('fluidmcp.cli.services.run_servers._llm_processes', {"test-model": None}):
                    mock_get_client.return_value = mock_client

                    # Import after patching
                    from fluidmcp.cli.services.run_servers import _proxy_llm_request

                    # Request body with tools parameter
                    request_body = {
                        "messages": [
                            {"role": "user", "content": "What's the weather in San Francisco?"}
                        ],
                        "tools": [{
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "description": "Get weather for a city",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "city": {"type": "string"}
                                    },
                                    "required": ["city"]
                                }
                            }
                        }],
                        "tool_choice": "auto"
                    }

                    # Call proxy function
                    result = await _proxy_llm_request(
                        model_id="test-model",
                        endpoint_key="chat",
                        method="POST",
                        body=request_body
                    )

            # Verify request was forwarded with tools parameter
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args

            # Check URL
            assert call_args[0][0] == "http://localhost:8000/v1/chat/completions"

            # Check body includes tools
            forwarded_body = call_args[1]["json"]
            assert "tools" in forwarded_body
            assert forwarded_body["tools"] == request_body["tools"]
            assert forwarded_body["tool_choice"] == "auto"
            assert forwarded_body["messages"] == request_body["messages"]

            # Verify response is returned unchanged
            assert result == mock_vllm_response

    @pytest.mark.asyncio
    async def test_tool_choice_parameter_forwarded(self):
        """Test that tool_choice parameter is forwarded to vLLM."""
        mock_vllm_response = {
            "id": "test",
            "choices": [{"message": {"role": "assistant", "content": "response"}}]
        }

        mock_response = Mock()
        mock_response.json.return_value = mock_vllm_response
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        mock_config = {
            "base_url": "http://localhost:8000",
            "chat": "/v1/chat/completions"
        }

        with patch('fluidmcp.cli.services.run_servers._get_http_client') as mock_get_client:
            with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {"test-model": mock_config}):
                with patch('fluidmcp.cli.services.run_servers._llm_processes', {"test-model": None}):
                    mock_get_client.return_value = mock_client

                    from fluidmcp.cli.services.run_servers import _proxy_llm_request

                    # Force specific tool
                    request_body = {
                        "messages": [{"role": "user", "content": "test"}],
                        "tools": [{"type": "function", "function": {"name": "test_tool"}}],
                        "tool_choice": {
                            "type": "function",
                            "function": {"name": "test_tool"}
                        }
                    }

                    await _proxy_llm_request(
                        model_id="test-model",
                        endpoint_key="chat",
                        method="POST",
                        body=request_body
                    )

            # Verify tool_choice was forwarded
            call_args = mock_client.post.call_args
            forwarded_body = call_args[1]["json"]
            assert forwarded_body["tool_choice"] == request_body["tool_choice"]

    @pytest.mark.asyncio
    async def test_response_with_tool_calls_returned_unchanged(self):
        """Test that vLLM response with tool_calls is returned to client unchanged."""
        # Response with tool_calls
        vllm_response = {
            "id": "chatcmpl-abc123",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "llama-3-70b",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_xyz789",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"operation": "multiply", "x": 25, "y": 4}'
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 20,
                "total_tokens": 70
            }
        }

        mock_response = Mock()
        mock_response.json.return_value = vllm_response
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        mock_config = {
            "base_url": "http://localhost:8000",
            "chat": "/v1/chat/completions"
        }

        with patch('fluidmcp.cli.services.run_servers._get_http_client') as mock_get_client:
            with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {"test-model": mock_config}):
                with patch('fluidmcp.cli.services.run_servers._llm_processes', {"test-model": None}):
                    mock_get_client.return_value = mock_client

                    from fluidmcp.cli.services.run_servers import _proxy_llm_request

                    request_body = {
                        "messages": [{"role": "user", "content": "What is 25 * 4?"}],
                        "tools": [{"type": "function", "function": {"name": "calculator"}}]
                    }

                    result = await _proxy_llm_request(
                        model_id="test-model",
                        endpoint_key="chat",
                        method="POST",
                        body=request_body
                    )

            # Verify response structure is preserved
            assert result["id"] == "chatcmpl-abc123"
            assert result["choices"][0]["message"]["tool_calls"] is not None
            assert result["choices"][0]["message"]["content"] is None
            assert result["choices"][0]["finish_reason"] == "tool_calls"
            assert result["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "calculator"

    @pytest.mark.asyncio
    async def test_request_without_tools_still_works(self):
        """Test that requests without tools parameter work normally."""
        vllm_response = {
            "id": "test",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Hello! How can I help you?"
                },
                "finish_reason": "stop"
            }]
        }

        mock_response = Mock()
        mock_response.json.return_value = vllm_response
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        mock_config = {
            "base_url": "http://localhost:8000",
            "chat": "/v1/chat/completions"
        }

        with patch('fluidmcp.cli.services.run_servers._get_http_client') as mock_get_client:
            with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {"test-model": mock_config}):
                with patch('fluidmcp.cli.services.run_servers._llm_processes', {"test-model": None}):
                    mock_get_client.return_value = mock_client

                    from fluidmcp.cli.services.run_servers import _proxy_llm_request

                    # Request without tools
                    request_body = {
                        "messages": [{"role": "user", "content": "Hello"}]
                    }

                    result = await _proxy_llm_request(
                        model_id="test-model",
                        endpoint_key="chat",
                        method="POST",
                        body=request_body
                    )

            # Verify normal response works
            assert result["choices"][0]["message"]["content"] == "Hello! How can I help you?"
            assert result["choices"][0]["finish_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_streaming_validation_passes_for_configured_model(self):
        """Test that _validate_streaming_request accepts properly configured models.

        Note: This tests validation only, not actual streaming behavior with tools.
        Full streaming integration would require async generator mocking.
        """
        mock_config = {
            "base_url": "http://localhost:8000",
            "chat": "/v1/chat/completions"
        }

        mock_process = Mock()
        mock_process.is_running.return_value = True

        with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {"test-model": mock_config}):
            with patch('fluidmcp.cli.services.run_servers._llm_processes', {"test-model": mock_process}):
                from fluidmcp.cli.services.run_servers import _validate_streaming_request

                # Should not raise exception for valid configuration
                _validate_streaming_request("test-model", "chat")
