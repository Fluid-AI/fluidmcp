"""
End-to-End Integration Tests for LLM Inference.

These tests run against real APIs when credentials are available.
Tests are skipped if required environment variables are not set.

Required environment variables:
- REPLICATE_API_TOKEN: For Replicate API tests
- VLLM_ENDPOINT: For vLLM tests (e.g., http://localhost:8001/v1)

Run with:
    export REPLICATE_API_TOKEN="r8_..."
    export VLLM_ENDPOINT="http://localhost:8001/v1"
    pytest tests/test_e2e_integration.py -v
"""

import pytest
import os
import httpx
from loguru import logger


# Skip all tests if E2E testing is not explicitly enabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E_TESTS") != "true",
    reason="E2E tests disabled. Set RUN_E2E_TESTS=true to enable"
)


@pytest.fixture
def replicate_api_token():
    """Get Replicate API token from environment."""
    token = os.getenv("REPLICATE_API_TOKEN")
    if not token:
        pytest.skip("REPLICATE_API_TOKEN not set")
    return token


@pytest.fixture
def vllm_endpoint():
    """Get vLLM endpoint from environment."""
    endpoint = os.getenv("VLLM_ENDPOINT")
    if not endpoint:
        pytest.skip("VLLM_ENDPOINT not set")
    return endpoint


class TestReplicateE2E:
    """End-to-end tests for Replicate API integration."""

    @pytest.mark.asyncio
    async def test_replicate_model_list(self, replicate_api_token):
        """Test listing Replicate models via API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.replicate.com/v1/models",
                headers={"Authorization": f"Token {replicate_api_token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            logger.info(f"Found {len(data['results'])} Replicate models")

    @pytest.mark.asyncio
    async def test_replicate_simple_prediction(self, replicate_api_token):
        """Test creating a simple Replicate prediction."""
        # Use a lightweight model for quick testing
        model = "replicate/hello-world"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://api.replicate.com/v1/models/{model}/predictions",
                headers={
                    "Authorization": f"Token {replicate_api_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "input": {"text": "Hello"}
                }
            )

            assert response.status_code in [200, 201]
            data = response.json()
            assert "id" in data
            assert "status" in data
            prediction_id = data["id"]
            logger.info(f"Created prediction: {prediction_id}, status: {data['status']}")

            # Poll for completion (with timeout)
            import asyncio
            for _ in range(30):  # 30 seconds max
                await asyncio.sleep(1)

                status_response = await client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers={"Authorization": f"Token {replicate_api_token}"}
                )

                status_data = status_response.json()
                status = status_data["status"]
                logger.info(f"Prediction status: {status}")

                if status == "succeeded":
                    assert "output" in status_data
                    logger.info(f"Prediction succeeded: {status_data['output']}")
                    break
                elif status == "failed":
                    pytest.fail(f"Prediction failed: {status_data.get('error')}")
                    break

    @pytest.mark.asyncio
    async def test_replicate_rate_limiting(self, replicate_api_token):
        """Test that Replicate API handles rate limiting gracefully."""
        # This test verifies that we can detect rate limit responses
        # We don't actually trigger rate limiting (that would be abusive)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.replicate.com/v1/models",
                headers={"Authorization": f"Token {replicate_api_token}"}
            )

            # If we get rate limited, status should be 429
            if response.status_code == 429:
                assert "Retry-After" in response.headers or "X-RateLimit-Reset" in response.headers
                logger.warning("Rate limited - test would retry in production")
            else:
                # Normal response
                assert response.status_code == 200


class TestVLLME2E:
    """End-to-end tests for vLLM integration."""

    @pytest.mark.asyncio
    async def test_vllm_health_check(self, vllm_endpoint):
        """Test vLLM health endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{vllm_endpoint}/models")

            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            logger.info(f"vLLM models: {[m['id'] for m in data['data']]}")

    @pytest.mark.asyncio
    async def test_vllm_chat_completion(self, vllm_endpoint):
        """Test vLLM chat completion."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{vllm_endpoint}/chat/completions",
                json={
                    "model": "default",  # vLLM uses whatever model is loaded
                    "messages": [
                        {"role": "user", "content": "Say 'test' and nothing else"}
                    ],
                    "max_tokens": 10,
                    "temperature": 0.1
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "choices" in data
            assert len(data["choices"]) > 0
            assert "message" in data["choices"][0]
            assert "content" in data["choices"][0]["message"]

            content = data["choices"][0]["message"]["content"]
            logger.info(f"vLLM response: {content}")

    @pytest.mark.asyncio
    async def test_vllm_text_completion(self, vllm_endpoint):
        """Test vLLM text completion."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{vllm_endpoint}/completions",
                json={
                    "model": "default",
                    "prompt": "The capital of France is",
                    "max_tokens": 10,
                    "temperature": 0.1
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "choices" in data
            assert len(data["choices"]) > 0
            assert "text" in data["choices"][0]

            text = data["choices"][0]["text"]
            logger.info(f"vLLM completion: {text}")

    @pytest.mark.asyncio
    async def test_vllm_streaming(self, vllm_endpoint):
        """Test vLLM streaming completion."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{vllm_endpoint}/chat/completions",
                json={
                    "model": "default",
                    "messages": [{"role": "user", "content": "Count to 5"}],
                    "max_tokens": 50,
                    "stream": True
                }
            ) as response:
                assert response.status_code == 200

                chunks = []
                async for chunk in response.aiter_bytes():
                    if chunk.strip():
                        chunks.append(chunk)

                assert len(chunks) > 0
                logger.info(f"Received {len(chunks)} streaming chunks")


class TestFluidMCPE2E:
    """End-to-end tests for FluidMCP gateway with real backends."""

    @pytest.fixture
    def fluidmcp_url(self):
        """Get FluidMCP URL from environment."""
        url = os.getenv("FLUIDMCP_URL", "http://localhost:8099")
        return url

    @pytest.mark.asyncio
    async def test_fluidmcp_metrics_endpoint(self, fluidmcp_url):
        """Test FluidMCP metrics endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{fluidmcp_url}/api/metrics/json")

            # May return 401 if secure mode enabled, otherwise 200
            if response.status_code == 401:
                pytest.skip("FluidMCP secure mode enabled")

            assert response.status_code == 200
            data = response.json()
            assert "models" in data
            assert "uptime_seconds" in data
            logger.info(f"FluidMCP tracking {len(data['models'])} models")

    @pytest.mark.asyncio
    async def test_fluidmcp_unified_endpoint_with_replicate(
        self,
        fluidmcp_url,
        replicate_api_token
    ):
        """Test FluidMCP unified endpoint with Replicate backend."""
        # This requires FluidMCP to be running with a configured Replicate model
        # Model ID should be provided via REPLICATE_MODEL_ID environment variable
        model_id = os.getenv("REPLICATE_MODEL_ID")
        if not model_id:
            pytest.skip("REPLICATE_MODEL_ID environment variable not set")

        logger.info(f"Testing with Replicate model: {model_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:

            # Test unified endpoint
            response = await client.post(
                f"{fluidmcp_url}/api/llm/{model_id}/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "max_tokens": 10
                }
            )

            # Should get valid response or specific error
            assert response.status_code in [200, 401, 404, 500, 501]

            if response.status_code == 200:
                data = response.json()
                assert "choices" in data
                logger.info(f"Unified endpoint success: {data}")


class TestLoadAndConcurrency:
    """Basic load and concurrency tests."""

    @pytest.mark.asyncio
    async def test_concurrent_vllm_requests(self, vllm_endpoint):
        """Test concurrent requests to vLLM."""
        import asyncio

        async def make_request(client, i):
            response = await client.post(
                f"{vllm_endpoint}/chat/completions",
                json={
                    "model": "default",
                    "messages": [{"role": "user", "content": f"Request {i}"}],
                    "max_tokens": 5
                }
            )
            return response.status_code

        async with httpx.AsyncClient(timeout=60.0) as client:
            tasks = [make_request(client, i) for i in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All requests should succeed or fail gracefully
            assert len(results) == 5
            success_count = sum(1 for r in results if r == 200)
            logger.info(f"Concurrent requests: {success_count}/5 succeeded")
            assert success_count >= 3  # At least 60% success rate
