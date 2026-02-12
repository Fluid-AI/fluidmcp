"""
Unit tests for unified chat completions endpoint in management API.

Tests the provider-agnostic /llm/{model_id}/v1/chat/completions endpoint
that routes to different providers (Replicate, vLLM) based on model configuration.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException


@pytest.fixture
def app_with_management_routes():
    """Create FastAPI app with management routes for testing."""
    from fluidmcp.cli.api.management import router as management_router

    app = FastAPI()
    app.include_router(management_router, prefix="/api")
    return app


@pytest.fixture
def client(app_with_management_routes):
    """Create test client with secure mode disabled for entire test duration."""
    # Disable secure mode for testing - keep patch active for entire test
    with patch.dict('os.environ', {'FMCP_SECURE_MODE': 'false'}):
        yield TestClient(app_with_management_routes)


class TestUnifiedChatCompletionsRouting:
    """Test provider routing logic in unified endpoint."""

    def test_replicate_model_routes_to_replicate_adapter(self, client):
        """Test that Replicate models are routed to replicate_chat_completion."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock_replicate:
                mock_replicate.return_value = {
                    "id": "test-completion",
                    "object": "chat.completion",
                    "choices": [{"message": {"content": "Hello"}}]
                }

                response = client.post(
                    "/api/llm/v1/chat/completions",
                    json={
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "Test"}],
                        "temperature": 0.7
                    }
                )

                assert response.status_code == 200
                mock_replicate.assert_called_once()
                # Verify correct arguments passed
                call_args = mock_replicate.call_args
                assert call_args[0][0] == "test-model"  # model_id
                assert "messages" in call_args[0][1]  # request_body

    def test_vllm_model_routes_to_http_client(self, client):
        """Test that vLLM models are proxied via HTTP client."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='vllm'):
            with patch('fluidmcp.cli.api.management.get_model_config', return_value={
                "endpoints": {"base_url": "http://localhost:8001/v1"}
            }):
                with patch('fluidmcp.cli.api.management._get_http_client') as mock_get_client:
                    mock_http_client = Mock()
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"id": "vllm-response"}
                    mock_response.raise_for_status = Mock()

                    # Create async mock for post method
                    async def mock_post(*args, **kwargs):
                        return mock_response

                    mock_http_client.post = mock_post
                    mock_get_client.return_value = mock_http_client

                    response = client.post(
                        "/api/llm/v1/chat/completions",
                        json={
                            "model": "vllm-model",
                            "messages": [{"role": "user", "content": "Test"}],
                            "stream": False
                        }
                    )

                    assert response.status_code == 200
                    assert response.json() == {"id": "vllm-response"}

    def test_unknown_model_returns_404(self, client):
        """Test that unknown model IDs return 404."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value=None):
            response = client.post(
                "/api/llm/v1/chat/completions",
                json={"model": "unknown-model", "messages": [{"role": "user", "content": "Test"}]}
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_unsupported_provider_returns_501(self, client):
        """Test that unsupported provider types return 501."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='unsupported_provider'):
            response = client.post(
                "/api/llm/v1/chat/completions",
                json={"model": "fake-model", "messages": [{"role": "user", "content": "Test"}]}
            )

            assert response.status_code == 501
            assert "not yet supported" in response.json()["detail"].lower()


class TestReplicateErrorHandling:
    """Test error handling for Replicate models."""

    def test_replicate_streaming_returns_501(self, client):
        """Test that streaming requests for Replicate models return 501."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock_replicate:
                # Adapter should raise 501 for streaming
                mock_replicate.side_effect = HTTPException(
                    501,
                    "Streaming is not supported for Replicate models"
                )

                response = client.post(
                    "/api/llm/v1/chat/completions",
                    json={
                        "model": "replicate-model",
                        "messages": [{"role": "user", "content": "Test"}],
                        "stream": True
                    }
                )

                assert response.status_code == 501
                assert "streaming" in response.json()["detail"].lower()

    def test_replicate_http_error_preserved(self, client):
        """Test that Replicate HTTP errors preserve status codes."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock_replicate:
                # Simulate upstream 429 rate limit
                mock_replicate.side_effect = HTTPException(429, "Rate limit exceeded")

                response = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "replicate-model", "messages": [{"role": "user", "content": "Test"}]}
                )

                assert response.status_code == 429
                assert "rate limit" in response.json()["detail"].lower()


class TestVLLMErrorHandling:
    """Test error handling for vLLM models."""

    def test_vllm_missing_base_url_returns_500(self, client):
        """Test that vLLM models without base_url return 500."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='vllm'):
            with patch('fluidmcp.cli.api.management.get_model_config', return_value={
                "endpoints": {}  # Missing base_url
            }):
                response = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "vllm-model", "messages": [{"role": "user", "content": "Test"}]}
                )

                assert response.status_code == 500
                assert "missing base_url" in response.json()["detail"].lower()

    def test_vllm_connection_error_returns_502(self, client):
        """Test that vLLM connection errors return 502."""
        import httpx

        with patch('fluidmcp.cli.api.management.get_model_type', return_value='vllm'):
            with patch('fluidmcp.cli.api.management.get_model_config', return_value={
                "endpoints": {"base_url": "http://localhost:8001/v1"}
            }):
                with patch('fluidmcp.cli.api.management._get_http_client') as mock_get_client:
                    mock_http_client = AsyncMock()
                    mock_http_client.post.side_effect = httpx.RequestError("Connection refused")
                    mock_get_client.return_value = mock_http_client

                    response = client.post(
                        "/api/llm/v1/chat/completions",
                        json={"model": "vllm-model", "messages": [{"role": "user", "content": "Test"}]}
                    )

                    assert response.status_code == 502
                    assert "failed to connect" in response.json()["detail"].lower()


class TestHTTPClientLifecycle:
    """Test HTTP client lazy initialization and cleanup."""

    @pytest.mark.asyncio
    async def test_http_client_lazy_initialization(self):
        """Test that HTTP client is only created when first used."""
        from fluidmcp.cli.api.management import _get_http_client, cleanup_http_client
        from unittest.mock import AsyncMock

        # Mock httpx.AsyncClient to avoid creating real client
        with patch('fluidmcp.cli.api.management.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # First call should create client
            client = _get_http_client()
            assert client is not None
            assert mock_client_class.called

            # Second call should return same instance
            client2 = _get_http_client()
            assert client is client2

            # Cleanup (even though mocked, demonstrates proper pattern)
            await cleanup_http_client()

    @pytest.mark.asyncio
    async def test_cleanup_http_client_handles_none(self):
        """Test that cleanup handles None client gracefully."""
        from fluidmcp.cli.api.management import cleanup_http_client

        with patch('fluidmcp.cli.api.management._http_client', None):
            # Should not raise error
            await cleanup_http_client()

    @pytest.mark.asyncio
    async def test_cleanup_http_client_closes_and_resets(self):
        """Test that cleanup closes client and resets to None."""
        from fluidmcp.cli.api.management import cleanup_http_client
        import httpx

        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch('fluidmcp.cli.api.management._http_client', mock_client):
            await cleanup_http_client()
            mock_client.aclose.assert_called_once()


# TODO: Additional test coverage needed (from Copilot feedback):
# 1. Integration tests with actual FastAPI test client and full request lifecycle
# 2. Streaming SSE tests for vLLM (currently skipped due to TestClient limitations)
# 3. Multi-model scenarios with different API tokens
# 4. Timeout handling for both Replicate and vLLM
# 5. Request validation (malformed JSON, missing required fields)
# 6. Concurrent request handling
# 7. Rate limiting integration tests
