"""
Tests for Replicate model client.

Tests HTTP-based inference using mock responses, including predictions,
streaming, error handling, and retry logic.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, Mock, patch
from fluidmcp.cli.services.replicate_client import (
    ReplicateClient,
    initialize_replicate_models,
    stop_all_replicate_models,
    get_replicate_client,
    list_replicate_models
)


@pytest.fixture
def replicate_config():
    """Sample Replicate configuration."""
    return {
        "model": "meta/llama-2-70b-chat",
        "api_key": "r8_test_key_12345",
        "endpoints": {"base_url": "https://api.replicate.com/v1"},
        "default_params": {"temperature": 0.7, "max_tokens": 1000},
        "timeout": 60.0,
        "max_retries": 3
    }


@pytest.fixture
def minimal_config():
    """Minimal Replicate configuration."""
    return {
        "model": "meta/llama-2-7b-chat",
        "api_key": "r8_minimal_key"
    }


@pytest.fixture(autouse=True)
async def cleanup_replicate_registry():
    """Clean up the global Replicate registry before/after each test."""
    # Cleanup before test
    await stop_all_replicate_models()
    yield
    # Cleanup after test
    await stop_all_replicate_models()


@pytest.fixture
async def mock_http_client():
    """Create a mock httpx AsyncClient (tests must manually assign to avoid resource leak)."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.aclose = AsyncMock()  # Ensure aclose is mockable
    yield client


class TestReplicateClientInitialization:
    """Test Replicate client initialization."""

    @pytest.mark.asyncio
    async def test_successful_initialization(self, replicate_config):
        """Test successful client initialization with full config."""
        client = ReplicateClient("test-model", replicate_config)

        try:
            assert client.model_id == "test-model"
            assert client.model_name == "meta/llama-2-70b-chat"
            assert client.api_key == "r8_test_key_12345"
            assert client.base_url == "https://api.replicate.com/v1"
            assert client.default_params == {"temperature": 0.7, "max_tokens": 1000}
            assert client.timeout == 60.0
            assert client.max_retries == 3
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_minimal_initialization(self, minimal_config):
        """Test initialization with minimal config uses defaults."""
        client = ReplicateClient("minimal", minimal_config)

        try:
            assert client.model_id == "minimal"
            assert client.model_name == "meta/llama-2-7b-chat"
            assert client.base_url == "https://api.replicate.com/v1"  # Default
            assert client.default_params == {}  # Default empty
            assert client.timeout == 60.0  # Default
            assert client.max_retries == 3  # Default
        finally:
            await client.close()

    def test_missing_model_raises_error(self):
        """Test that missing 'model' field raises ValueError."""
        config = {"api_key": "test_key"}

        with pytest.raises(ValueError, match="missing 'model' in config"):
            ReplicateClient("test", config)

    def test_missing_api_key_raises_error(self):
        """Test that missing 'api_key' field raises ValueError."""
        config = {"model": "meta/llama-2-70b-chat"}

        with pytest.raises(ValueError, match="missing 'api_key' in config"):
            ReplicateClient("test", config)

    @pytest.mark.asyncio
    async def test_env_var_expansion_success(self, monkeypatch):
        """Test that environment variables in api_key are expanded correctly."""
        # Set environment variable
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_expanded_key_12345")

        config = {
            "model": "meta/llama-2-70b-chat",
            "api_key": "${REPLICATE_API_TOKEN}"
        }

        client = ReplicateClient("test", config)

        try:
            assert client.api_key == "r8_expanded_key_12345"
        finally:
            await client.close()

    def test_env_var_expansion_unset_raises_error(self, monkeypatch):
        """Test that unresolved environment variables raise a clear error."""
        # Ensure variable is NOT set
        monkeypatch.delenv("REPLICATE_UNSET_TOKEN", raising=False)

        config = {
            "model": "meta/llama-2-70b-chat",
            "api_key": "${REPLICATE_UNSET_TOKEN}"
        }

        with pytest.raises(ValueError, match="unresolved environment variable.*REPLICATE_UNSET_TOKEN"):
            ReplicateClient("test", config)

    @pytest.mark.asyncio
    async def test_env_var_expansion_alternative_format(self, monkeypatch):
        """Test that $VAR format (without braces) also works."""
        monkeypatch.setenv("REPLICATE_KEY", "r8_alt_format_key")

        config = {
            "model": "meta/llama-2-70b-chat",
            "api_key": "$REPLICATE_KEY"
        }

        client = ReplicateClient("test", config)

        try:
            assert client.api_key == "r8_alt_format_key"
        finally:
            await client.close()


class TestReplicateClientPredictions:
    """Test prediction creation and retrieval."""

    @pytest.mark.asyncio
    async def test_successful_prediction(self, replicate_config, mock_http_client):
        """Test successful prediction creation."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "pred_abc123",
            "status": "starting",
            "input": {"prompt": "Hello"}
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.post.return_value = mock_response

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        # Create prediction
        result = await client.predict({"prompt": "Hello"})

        assert result["id"] == "pred_abc123"
        assert result["status"] == "starting"
        mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_prediction_merges_default_params(self, replicate_config, mock_http_client):
        """Test that predictions merge default params with input."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": "pred_123", "status": "starting"}
        mock_response.raise_for_status = Mock()
        mock_http_client.post.return_value = mock_response

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        # Create prediction with partial input
        await client.predict({"prompt": "Test"})

        # Check that default params were merged
        call_args = mock_http_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["input"]["temperature"] == 0.7  # From default_params
        assert payload["input"]["max_tokens"] == 1000  # From default_params
        assert payload["input"]["prompt"] == "Test"  # From input

    @pytest.mark.asyncio
    async def test_prediction_retry_on_failure(self, replicate_config, mock_http_client):
        """Test retry logic on transient errors (network errors and 5xx)."""
        # Create a mock request for httpx.RequestError
        mock_request = httpx.Request("POST", "https://api.replicate.com/v1/predictions")

        # First two calls fail with retryable errors, third succeeds
        mock_http_client.post.side_effect = [
            httpx.RequestError("Network error", request=mock_request),
            httpx.RequestError("Network error", request=mock_request),
            Mock(json=lambda: {"id": "pred_123", "status": "starting"}, raise_for_status=Mock())
        ]

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        # Patch asyncio.sleep to avoid real delays in tests
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # Should eventually succeed after retries
            result = await client.predict({"prompt": "Test"})

        assert result["id"] == "pred_123"
        assert mock_http_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_prediction_fails_after_max_retries(self, replicate_config, mock_http_client):
        """Test that prediction fails after max retries on transient errors."""
        # Create a mock request for httpx.RequestError
        mock_request = httpx.Request("POST", "https://api.replicate.com/v1/predictions")

        # All calls fail with retryable errors
        mock_http_client.post.side_effect = httpx.RequestError("Network error", request=mock_request)

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        # Patch asyncio.sleep to avoid real delays in tests
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # Should raise after max_retries attempts (3 retries + 1 initial = 4 total)
            with pytest.raises(httpx.RequestError):
                await client.predict({"prompt": "Test"})

        assert mock_http_client.post.call_count == 4  # 1 initial + max_retries (3)

    @pytest.mark.asyncio
    async def test_get_prediction(self, replicate_config, mock_http_client):
        """Test retrieving prediction status."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "pred_abc123",
            "status": "succeeded",
            "output": "Hello World"
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get.return_value = mock_response

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        result = await client.get_prediction("pred_abc123")

        assert result["id"] == "pred_abc123"
        assert result["status"] == "succeeded"
        assert result["output"] == "Hello World"

    @pytest.mark.asyncio
    async def test_cancel_prediction(self, replicate_config, mock_http_client):
        """Test canceling a running prediction."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "pred_abc123",
            "status": "canceled"
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.post.return_value = mock_response

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        result = await client.cancel_prediction("pred_abc123")

        assert result["status"] == "canceled"
        mock_http_client.post.assert_called_once_with("/predictions/pred_abc123/cancel")


class TestReplicateClientStreaming:
    """Test streaming predictions."""

    @pytest.mark.asyncio
    async def test_stream_prediction_success(self, replicate_config, mock_http_client):
        """Test successful streaming prediction."""
        # Mock prediction creation
        create_response = Mock()
        create_response.json.return_value = {"id": "pred_stream_123", "status": "starting"}
        create_response.raise_for_status = Mock()

        # Mock status checks
        status_response_1 = Mock()
        status_response_1.json.return_value = {
            "id": "pred_stream_123",
            "status": "processing",
            "output": "Hello"
        }
        status_response_1.raise_for_status = Mock()

        status_response_2 = Mock()
        status_response_2.json.return_value = {
            "id": "pred_stream_123",
            "status": "succeeded",
            "output": "Hello World"
        }
        status_response_2.raise_for_status = Mock()

        mock_http_client.post.return_value = create_response
        mock_http_client.get.side_effect = [status_response_1, status_response_2]

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        # Patch asyncio.sleep to avoid real delays in tests
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # Stream prediction
            chunks = []
            async for chunk in client.stream_prediction({"prompt": "Test"}):
                chunks.append(chunk)

            assert "Hello" in chunks or "Hello World" in chunks
            assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_stream_prediction_failure(self, replicate_config, mock_http_client):
        """Test streaming prediction handles failures."""
        # Mock prediction creation
        create_response = Mock()
        create_response.json.return_value = {"id": "pred_fail_123", "status": "starting"}
        create_response.raise_for_status = Mock()

        # Mock failed status
        status_response = Mock()
        status_response.json.return_value = {
            "id": "pred_fail_123",
            "status": "failed",
            "error": "Model error"
        }
        status_response.raise_for_status = Mock()

        mock_http_client.post.return_value = create_response
        mock_http_client.get.return_value = status_response

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        # Should raise exception on failure
        with pytest.raises(Exception, match="Prediction failed"):
            async for _ in client.stream_prediction({"prompt": "Test"}):
                pass


class TestReplicateClientModelInfo:
    """Test model information retrieval."""

    @pytest.mark.asyncio
    async def test_get_model_info(self, replicate_config, mock_http_client):
        """Test retrieving model information."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "owner": "meta",
            "name": "llama-2-70b-chat",
            "description": "A 70B parameter language model",
            "latest_version": {
                "id": "version_123"
            }
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get.return_value = mock_response

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        result = await client.get_model_info()

        assert result["owner"] == "meta"
        assert result["name"] == "llama-2-70b-chat"
        mock_http_client.get.assert_called_once_with("/models/meta/llama-2-70b-chat")

    @pytest.mark.asyncio
    async def test_get_model_info_invalid_format(self, replicate_config, mock_http_client):
        """Test that invalid model format raises error."""
        config = {**replicate_config, "model": "invalid-format"}
        client = ReplicateClient("test", config)

        try:
            with pytest.raises(ValueError, match="Invalid model format"):
                await client.get_model_info()
        finally:
            await client.close()


class TestReplicateClientHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, replicate_config, mock_http_client):
        """Test successful health check."""
        mock_response = Mock()
        mock_response.json.return_value = {"owner": "meta", "name": "llama-2-70b-chat"}
        mock_response.raise_for_status = Mock()
        mock_http_client.get.return_value = mock_response

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, replicate_config, mock_http_client):
        """Test health check handles errors."""
        mock_http_client.get.side_effect = httpx.HTTPError("API unavailable")

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        result = await client.health_check()

        assert result is False


class TestReplicateClientContextManager:
    """Test async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager(self, replicate_config, mock_http_client):
        """Test client can be used as async context manager."""
        mock_http_client.aclose = AsyncMock()

        original_client = ReplicateClient("test", replicate_config)
        await original_client.client.aclose()  # Close original to prevent leak
        client = original_client
        client.client = mock_http_client

        async with client as c:
            assert c == client

        mock_http_client.aclose.assert_called_once()


class TestReplicateModelManagement:
    """Test global model initialization and management."""

    @pytest.mark.asyncio
    async def test_initialize_replicate_models(self, replicate_config):
        """Test initializing multiple Replicate models."""
        configs = {
            "model1": replicate_config,
            "model2": {**replicate_config, "model": "mistralai/mistral-7b"}
        }

        with patch('fluidmcp.cli.services.replicate_client.ReplicateClient') as MockClient:
            # Mock client instances
            mock_client1 = AsyncMock()
            mock_client1.health_check.return_value = True
            mock_client1.close = AsyncMock()

            mock_client2 = AsyncMock()
            mock_client2.health_check.return_value = True
            mock_client2.close = AsyncMock()

            MockClient.side_effect = [mock_client1, mock_client2]

            clients = await initialize_replicate_models(configs)

            assert len(clients) == 2
            assert "model1" in clients
            assert "model2" in clients

    @pytest.mark.asyncio
    async def test_initialize_skips_failed_health_check(self, replicate_config):
        """Test that models failing health check are skipped."""
        configs = {"model1": replicate_config}

        with patch('fluidmcp.cli.services.replicate_client.ReplicateClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = False  # Health check fails
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            clients = await initialize_replicate_models(configs)

            assert len(clients) == 0
            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_all_replicate_models(self, replicate_config):
        """Test stopping all Replicate clients."""
        # First initialize models
        configs = {"model1": replicate_config}

        with patch('fluidmcp.cli.services.replicate_client.ReplicateClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = True
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            await initialize_replicate_models(configs)

            # Now stop all models
            await stop_all_replicate_models()

            mock_client.close.assert_called()

    def test_get_replicate_client(self, replicate_config):
        """Test retrieving a specific client."""
        # This would require a running client registry
        # Test basic functionality
        client = get_replicate_client("nonexistent")
        assert client is None

    def test_list_replicate_models(self):
        """Test listing all active model IDs."""
        # Initially should be empty (after cleanup)
        models = list_replicate_models()
        assert isinstance(models, list)
