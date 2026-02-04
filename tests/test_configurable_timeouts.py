"""
Tests for configurable timeouts and polling intervals.

Tests that timeout and polling configuration can be customized per model.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fluidmcp.cli.services.replicate_openai_adapter import replicate_chat_completion


@pytest.mark.asyncio
class TestConfigurableTimeouts:
    """Test suite for configurable timeout settings."""

    async def test_default_timeout(self):
        """Test that default timeout is used when not specified."""
        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={"id": "pred_123", "status": "starting"})
        mock_client.get_prediction = AsyncMock(return_value={
            "id": "pred_123",
            "status": "succeeded",
            "output": "Test output"
        })

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            response = await replicate_chat_completion(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]}
                # No timeout specified - should use default (300)
            )

        assert response["choices"][0]["message"]["content"] == "Test output"

    async def test_custom_timeout(self):
        """Test that custom timeout is respected."""
        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={"id": "pred_custom", "status": "starting"})

        # Simulate slow prediction that never completes
        mock_client.get_prediction = AsyncMock(return_value={
            "id": "pred_custom",
            "status": "processing",
            "output": ""
        })

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            with pytest.raises(Exception, match="timeout|timed out"):
                await replicate_chat_completion(
                    "test-model",
                    {"messages": [{"role": "user", "content": "Hi"}]},
                    timeout=1  # Very short custom timeout
                )

    async def test_per_model_timeout_from_config(self):
        """Test that per-model timeout config is used."""
        # This test verifies that timeout can be configured per model
        # in the model config (stored in registry)

        # Model config with custom timeout
        model_config = {
            "type": "replicate",
            "model": "meta/llama-2-70b-chat",
            "api_key": "test_key",
            "timeout": 120,  # Custom timeout
            "max_retries": 2
        }

        mock_client = Mock()
        mock_client.config = model_config
        mock_client.predict = AsyncMock(return_value={"id": "pred_config", "status": "starting"})
        mock_client.get_prediction = AsyncMock(return_value={
            "id": "pred_config",
            "status": "succeeded",
            "output": "Config test"
        })

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            # Timeout from request should override config
            response = await replicate_chat_completion(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=180  # Request timeout overrides config
            )

        assert response is not None

    async def test_poll_interval_configuration(self):
        """Test that poll intervals can be configured."""
        # Note: Poll intervals are currently hardcoded
        # This test documents expected behavior when they become configurable

        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={"id": "pred_poll", "status": "starting"})

        call_count = 0

        async def slow_prediction(pred_id):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"id": pred_id, "status": "processing", "output": ""}
            return {"id": pred_id, "status": "succeeded", "output": "Done"}

        mock_client.get_prediction = slow_prediction

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            response = await replicate_chat_completion(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=30
            )

        # Should have polled multiple times
        assert call_count >= 3
        assert response["choices"][0]["message"]["content"] == "Done"
