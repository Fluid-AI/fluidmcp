"""
Integration tests for LLM inference API endpoints.

Tests FastAPI routes with mocked backends to verify request/response handling,
error propagation, and multi-model scenarios.
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from unittest.mock import patch, AsyncMock, Mock


@pytest.fixture
def app_with_management_routes():
    """Create FastAPI app with management routes for testing."""
    from fluidmcp.cli.api.management import router as management_router

    app = FastAPI()
    app.include_router(management_router, prefix="/api")
    return app


@pytest.fixture
def client(app_with_management_routes):
    """Create test client."""
    # Disable secure mode for testing
    with patch.dict('os.environ', {'FMCP_SECURE_MODE': 'false'}):
        return TestClient(app_with_management_routes)


class TestReplicateEndpoints:
    """Integration tests for Replicate-specific endpoints."""

    def test_replicate_chat_completion_success(self, client):
        """Test successful Replicate chat completion via unified endpoint."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock_complete:
                mock_complete.return_value = {
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "created": 1677652288,
                    "model": "llama-2-70b",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Hello! How can I help you today?"
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 20,
                        "total_tokens": 30
                    }
                }

                response = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Hello"}],
                        "temperature": 0.7
                    }
                )

                assert response.status_code == 200
                data = response.json()
                assert data["object"] == "chat.completion"
                assert data["choices"][0]["message"]["content"] == "Hello! How can I help you today?"
                assert data["usage"]["total_tokens"] == 30

    def test_replicate_endpoint_not_found(self, client):
        """Test 404 when Replicate model doesn't exist."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value=None):
            response = client.post(
                "/api/llm/v1/chat/completions",
                json={"model": "nonexistent-model", "messages": [{"role": "user", "content": "Test"}]}
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_replicate_timeout_error(self, client):
        """Test timeout handling for Replicate requests."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock_complete:
                from fastapi import HTTPException
                mock_complete.side_effect = HTTPException(504, "Request timeout")

                response = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test"}]}
                )

                assert response.status_code == 504
                assert "timeout" in response.json()["detail"].lower()


class TestUnifiedEndpoints:
    """Integration tests for unified LLM endpoints."""

    def test_unified_chat_completion_replicate(self, client):
        """Test unified endpoint routes Replicate correctly."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock:
                mock.return_value = {"id": "test", "object": "chat.completion"}

                response = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Hi"}]}
                )

                assert response.status_code == 200
                mock.assert_called_once()

    def test_unified_chat_completion_vllm(self, client):
        """Test unified endpoint proxies vLLM correctly."""
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

                    async def mock_post(*args, **kwargs):
                        return mock_response

                    mock_http_client.post = mock_post
                    mock_get_client.return_value = mock_http_client

                    response = client.post(
                        "/api/llm/v1/chat/completions",
                        json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test"}],
                            "stream": False
                        }
                    )

                    assert response.status_code == 200
                    assert response.json() == {"id": "vllm-response"}

    def test_unified_completions_endpoint(self, client):
        """Test unified text completions endpoint."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='vllm'):
            with patch('fluidmcp.cli.api.management.get_model_config', return_value={
                "endpoints": {"base_url": "http://localhost:8001/v1"}
            }):
                with patch('fluidmcp.cli.api.management._get_http_client') as mock_get_client:
                    mock_http_client = Mock()
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "id": "cmpl-123",
                        "object": "text_completion",
                        "choices": [{"text": "Generated text", "index": 0}]
                    }
                    mock_response.raise_for_status = Mock()

                    async def mock_post(*args, **kwargs):
                        return mock_response

                    mock_http_client.post = mock_post
                    mock_get_client.return_value = mock_http_client

                    response = client.post(
                        "/api/llm/v1/completions",
                        json={"model": "vllm-model", "prompt": "Once upon a time", "max_tokens": 50}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["object"] == "text_completion"
                    assert len(data["choices"]) == 1


class TestMultiModelScenarios:
    """Integration tests for multi-model workflows."""

    def test_sequential_requests_different_models(self, client):
        """Test sequential requests to different model types."""
        # First request to Replicate
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock:
                mock.return_value = {"id": "replicate-1", "object": "chat.completion"}

                response1 = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test 1"}]}
                )

                assert response1.status_code == 200
                assert response1.json()["id"] == "replicate-1"

        # Second request to vLLM
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='vllm'):
            with patch('fluidmcp.cli.api.management.get_model_config', return_value={
                "endpoints": {"base_url": "http://localhost:8001/v1"}
            }):
                with patch('fluidmcp.cli.api.management._get_http_client') as mock_get_client:
                    mock_http_client = Mock()
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"id": "vllm-2"}
                    mock_response.raise_for_status = Mock()

                    async def mock_post(*args, **kwargs):
                        return mock_response

                    mock_http_client.post = mock_post
                    mock_get_client.return_value = mock_http_client

                    response2 = client.post(
                        "/api/llm/v1/chat/completions",
                        json={"model": "vllm-model", "messages": [{"role": "user", "content": "Test 2"}],
                            "stream": False
                        }
                    )

                    assert response2.status_code == 200
                    assert response2.json()["id"] == "vllm-2"

    def test_model_failover_scenario(self, client):
        """Test graceful handling when one model fails."""
        # First model fails
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock:
                from fastapi import HTTPException
                mock.side_effect = HTTPException(503, "Model unavailable")

                response1 = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test"}]}
                )

                assert response1.status_code == 503

        # Fallback to different model succeeds
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock:
                mock.return_value = {"id": "fallback-success", "object": "chat.completion"}

                response2 = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "llama-2-13b", "messages": [{"role": "user", "content": "Test"}]}
                )

                assert response2.status_code == 200
                assert response2.json()["id"] == "fallback-success"


class TestErrorHandling:
    """Integration tests for error scenarios."""

    def test_invalid_request_body(self, client):
        """Test validation of malformed request body."""
        response = client.post(
            "/api/llm/v1/chat/completions",
            json={"invalid": "no messages field"}
        )

        # Should fail validation
        # 400 if missing required "model" field
        # 404 if model not found
        # 422 if model found but other validation fails
        assert response.status_code in [400, 404, 422]

    def test_unsupported_provider_type(self, client):
        """Test error when provider type is not supported."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='unsupported_type'):
            response = client.post(
                "/api/llm/v1/chat/completions",
                json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test"}]}
            )

            assert response.status_code == 501
            assert "not yet supported" in response.json()["detail"].lower()

    def test_vllm_connection_error(self, client):
        """Test handling of vLLM connection failures."""
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='vllm'):
            with patch('fluidmcp.cli.api.management.get_model_config', return_value={
                "endpoints": {"base_url": "http://localhost:8001/v1"}
            }):
                with patch('fluidmcp.cli.api.management._get_http_client') as mock_get_client:
                    mock_http_client = Mock()

                    async def mock_post(*args, **kwargs):
                        import httpx
                        raise httpx.RequestError("Connection refused")

                    mock_http_client.post = mock_post
                    mock_get_client.return_value = mock_http_client

                    response = client.post(
                        "/api/llm/v1/chat/completions",
                        json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test"}],
                            "stream": False
                        }
                    )

                    assert response.status_code == 502
                    assert "failed to connect" in response.json()["detail"].lower()


class TestMetricsIntegration:
    """Integration tests for metrics collection during API calls."""

    def test_metrics_recorded_on_successful_request(self, client):
        """Test that successful requests are recorded in metrics."""
        from fluidmcp.cli.services.llm_metrics import reset_metrics_collector, get_metrics_collector

        # Reset metrics before test
        reset_metrics_collector()

        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock:
                mock.return_value = {
                    "id": "test-123",
                    "object": "chat.completion",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 20,
                        "total_tokens": 30
                    }
                }

                response = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test"}]}
                )

                assert response.status_code == 200

                # Verify metrics were recorded
                collector = get_metrics_collector()
                metrics = collector.get_model_metrics("llama-2-70b")
                assert metrics is not None
                assert metrics.total_requests == 1
                assert metrics.successful_requests == 1
                assert metrics.failed_requests == 0
                assert metrics.total_prompt_tokens == 10
                assert metrics.total_completion_tokens == 20

    def test_metrics_recorded_on_failed_request(self, client):
        """Test that failed requests are recorded in metrics."""
        from fluidmcp.cli.services.llm_metrics import reset_metrics_collector, get_metrics_collector

        # Reset metrics before test
        reset_metrics_collector()

        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock:
                from fastapi import HTTPException
                mock.side_effect = HTTPException(503, "Service unavailable")

                response = client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test"}]}
                )

                assert response.status_code == 503

                # Verify metrics were recorded
                collector = get_metrics_collector()
                metrics = collector.get_model_metrics("llama-2-70b")
                assert metrics is not None
                assert metrics.total_requests == 1
                assert metrics.successful_requests == 0
                assert metrics.failed_requests == 1
                assert 503 in metrics.errors_by_status
                assert metrics.errors_by_status[503] == 1

    def test_metrics_endpoint_returns_data_after_requests(self, client):
        """Test that /api/metrics endpoint returns collected metrics."""
        from fluidmcp.cli.services.llm_metrics import reset_metrics_collector

        # Reset metrics before test
        reset_metrics_collector()

        # Make a successful request
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='replicate'):
            with patch('fluidmcp.cli.api.management.replicate_chat_completion', new_callable=AsyncMock) as mock:
                mock.return_value = {
                    "id": "test-123",
                    "object": "chat.completion",
                    "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}
                }

                client.post(
                    "/api/llm/v1/chat/completions",
                    json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test"}]}
                )

        # Fetch metrics via API (use /metrics/json endpoint for JSON format)
        metrics_response = client.get("/api/metrics/json")
        assert metrics_response.status_code == 200

        metrics_data = metrics_response.json()
        assert "models" in metrics_data
        assert "llama-2-70b" in metrics_data["models"]
        assert metrics_data["models"]["llama-2-70b"]["requests"]["total"] == 1
        assert metrics_data["models"]["llama-2-70b"]["tokens"]["prompt"] == 5
        assert metrics_data["models"]["llama-2-70b"]["tokens"]["completion"] == 10

    def test_metrics_prometheus_format(self, client):
        """Test that metrics are available in Prometheus format."""
        from fluidmcp.cli.services.llm_metrics import reset_metrics_collector

        # Reset metrics before test
        reset_metrics_collector()

        # Make a request
        with patch('fluidmcp.cli.api.management.get_model_type', return_value='vllm'):
            with patch('fluidmcp.cli.api.management.get_model_config', return_value={
                "endpoints": {"base_url": "http://localhost:8001/v1"}
            }):
                with patch('fluidmcp.cli.api.management._get_http_client') as mock_get_client:
                    mock_http_client = Mock()
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "id": "test",
                        "usage": {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10}
                    }
                    mock_response.raise_for_status = Mock()

                    async def mock_post(*args, **kwargs):
                        return mock_response

                    mock_http_client.post = mock_post
                    mock_get_client.return_value = mock_http_client

                    client.post(
                        "/api/llm/v1/chat/completions",
                        json={"model": "llama-2-70b", "messages": [{"role": "user", "content": "Test"}], "stream": False}
                    )

        # Fetch Prometheus metrics
        prom_response = client.get("/api/metrics")
        assert prom_response.status_code == 200
        prom_text = prom_response.text

        # Verify Prometheus format
        assert "fluidmcp_llm_requests_total" in prom_text
        assert 'model_id="llama-2-70b"' in prom_text
        assert 'provider="vllm"' in prom_text
