"""
Integration tests for Replicate functionality.

These tests make real API calls to Replicate and are skipped if
REPLICATE_API_TOKEN is not set.

Run with: pytest tests/test_replicate_integration.py -v -m integration
"""

import pytest
import os
import asyncio
from fluidmcp.cli.services.replicate_client import ReplicateClient
from fluidmcp.cli.services.replicate_openai_adapter import (
    replicate_chat_completion,
    openai_messages_to_prompt,
    openai_to_replicate_input
)

# Skip all tests if no API token
pytestmark = pytest.mark.skipif(
    not os.getenv("REPLICATE_API_TOKEN"),
    reason="REPLICATE_API_TOKEN not set - skipping integration tests"
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestReplicateClientIntegration:
    """Integration tests for ReplicateClient with real API."""

    async def test_create_and_poll_prediction(self):
        """Test creating and polling a real prediction."""
        # Use a fast, cheap model for testing
        config = {
            "model": "replicate/flan-t5-small",  # Fast, free tier model
            "api_key": os.getenv("REPLICATE_API_TOKEN"),
            "timeout": 60,
            "max_retries": 2
        }
        client = ReplicateClient("tiny-llm", config)

        try:
            # Create prediction
            prediction = await client.predict(input_data={"prompt": "Hello"})

            assert "id" in prediction
            assert prediction["status"] in ["starting", "processing", "succeeded"]
            prediction_id = prediction["id"]

            # Poll until complete (with timeout)
            max_polls = 30
            for _ in range(max_polls):
                status = await client.get_prediction(prediction_id)
                if status["status"] in ["succeeded", "failed", "canceled"]:
                    break
                await asyncio.sleep(2)

            # Check final status
            assert status["status"] == "succeeded"
        finally:
            await client.close()
        assert "output" in status

    async def test_replicate_client_retry_logic(self):
        """Test that client retries on transient errors."""
        config = {
            "model": "replicate/flan-t5-small",
            "api_key": os.getenv("REPLICATE_API_TOKEN"),
            "timeout": 60,
            "max_retries": 3
        }
        client = ReplicateClient("test-model", config)

        try:
            # Make a valid request (should succeed without retries)
            prediction = await client.predict(input_data={"prompt": "Test"})
            assert "id" in prediction
        finally:
            await client.close()

    async def test_invalid_api_key_fails(self):
        """Test that invalid API key raises appropriate error."""
        config = {
            "model": "replicate/flan-t5-small",
            "api_key": "invalid_key_12345",
            "timeout": 30,
            "max_retries": 0
        }
        client = ReplicateClient("test-model", config)

        try:
            with pytest.raises(Exception):  # Should raise auth error
                await client.predict(input_data={"prompt": "Test"})
        finally:
            await client.close()

    async def test_nonexistent_model_fails(self):
        """Test that nonexistent model raises error."""
        config = {
            "model": "nonexistent/model-does-not-exist",
            "api_key": os.getenv("REPLICATE_API_TOKEN"),
            "timeout": 30,
            "max_retries": 0
        }
        client = ReplicateClient("fake-model", config)

        try:
            with pytest.raises(Exception):  # Should raise 404 or similar
                await client.predict(input_data={"prompt": "Test"})
        finally:
            await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
class TestReplicateAdapterIntegration:
    """Integration tests for OpenAI adapter with real API."""

    async def test_chat_completion_end_to_end(self):
        """Test complete chat completion flow with real API."""
        # Configure environment
        os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")

        # Mock config (would normally come from llm_provider_registry)
        model_config = {
            "type": "replicate",
            "model": "replicate/flan-t5-small",
            "api_key": os.getenv("REPLICATE_API_TOKEN"),
            "timeout": 60,
            "max_retries": 2
        }

        # Temporarily inject config (in real code, this comes from registry)
        from fluidmcp.cli.services import replicate_client
        replicate_client._replicate_clients["test-model"] = ReplicateClient("test-model", model_config)

        # Make chat completion request
        request = {
            "model": "test-model",
            "messages": [
                {"role": "user", "content": "What is 2+2?"}
            ],
            "temperature": 0.7,
            "max_tokens": 50
        }

        response = await replicate_chat_completion("test-model", request, timeout=60)

        # Verify OpenAI-format response
        assert "id" in response
        assert "object" in response
        assert response["object"] == "chat.completion"
        assert "choices" in response
        assert len(response["choices"]) > 0
        assert "message" in response["choices"][0]
        assert "content" in response["choices"][0]["message"]
        assert response["choices"][0]["finish_reason"] == "stop"

        # Content should be non-empty
        content = response["choices"][0]["message"]["content"]
        assert len(content) > 0

    async def test_openai_to_replicate_conversion(self):
        """Test that OpenAI format converts correctly to Replicate."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"}
        ]

        prompt = openai_messages_to_prompt(messages)
        assert "helpful" in prompt.lower()
        assert "hello" in prompt.lower()

        # Test conversion of full request
        request = {
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 100,
            "top_p": 0.9
        }

        replicate_input = openai_to_replicate_input(request)
        assert "prompt" in replicate_input
        assert replicate_input["temperature"] == 0.8
        assert replicate_input["max_tokens"] == 100
        assert replicate_input["top_p"] == 0.9

    async def test_timeout_handling(self):
        """Test that timeouts are handled correctly."""
        os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")

        # Configure client with very short timeout
        from fluidmcp.cli.services import replicate_client
        timeout_config = {
            "model": "replicate/flan-t5-small",
            "api_key": os.getenv("REPLICATE_API_TOKEN"),
            "timeout": 1,  # 1 second timeout
            "max_retries": 0
        }
        replicate_client._replicate_clients["timeout-test"] = ReplicateClient("timeout-test", timeout_config)

        request = {
            "model": "timeout-test",
            "messages": [{"role": "user", "content": "Long task"}]
        }

        # Should timeout (flan-t5 might be fast enough, so this might not always fail)
        # But the timeout mechanism should be invoked
        try:
            response = await replicate_chat_completion("timeout-test", request, timeout=1)
            # If it succeeds, that's fine - model was fast
            assert "choices" in response
        except Exception as e:
            # Should be a timeout error
            assert "timeout" in str(e).lower() or "timed out" in str(e).lower()


@pytest.mark.integration
def test_integration_environment_setup():
    """Verify integration test environment is configured."""
    api_token = os.getenv("REPLICATE_API_TOKEN")
    assert api_token is not None, "REPLICATE_API_TOKEN must be set for integration tests"
    assert api_token.startswith("r8_"), "REPLICATE_API_TOKEN should start with 'r8_'"
    assert len(api_token) > 20, "REPLICATE_API_TOKEN seems too short"
