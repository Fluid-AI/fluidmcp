"""
Load Testing for FluidMCP LLM Inference.

This script uses Locust to simulate concurrent users making LLM inference requests.

Installation:
    pip install locust

Usage:
    # Start FluidMCP
    fluidmcp run config.json --file --start-server

    # Run load test (web UI)
    locust -f examples/load_test_locust.py --host=http://localhost:8099

    # Run load test (headless)
    locust -f examples/load_test_locust.py --host=http://localhost:8099 \
           --users 10 --spawn-rate 2 --run-time 60s --headless

Configuration:
    - MODEL_ID: Model to test (default: uses first available)
    - AUTH_TOKEN: Bearer token if secure mode enabled
"""

import os
from locust import HttpUser, task, between, events  # type: ignore
from loguru import logger


class LLMInferenceUser(HttpUser):
    """
    Simulates a user making LLM inference requests.

    This user will:
    - List available models on start
    - Make chat completion requests
    - Make text completion requests
    - Check metrics periodically
    """

    # Wait 1-3 seconds between requests
    wait_time = between(1, 3)

    def on_start(self):
        """Called when a simulated user starts."""
        self.model_id = os.getenv("MODEL_ID")
        self.auth_token = os.getenv("AUTH_TOKEN")

        # Set auth header if token provided
        if self.auth_token:
            self.client.headers = {"Authorization": f"Bearer {self.auth_token}"}

        # Use default model if not specified via environment
        # Note: Model discovery endpoint /api/replicate/models has been deprecated
        # in favor of unified API. Users should specify MODEL_ID environment variable.
        if not self.model_id:
            logger.warning("MODEL_ID not set, using default model id 'default'")
            self.model_id = "default"

        logger.info(f"User started, targeting model: {self.model_id}")

    @task(3)
    def chat_completion(self):
        """Make a chat completion request (weighted 3x)."""
        response = self.client.post(
            "/api/llm/v1/chat/completions",
            json={
                "model": self.model_id,
                "messages": [
                    {"role": "user", "content": "What is 2+2?"}
                ],
                "max_tokens": 50,
                "temperature": 0.7
            },
            name="/api/llm/v1/chat/completions"
        )

        if response.status_code == 200:
            logger.debug(f"Chat completion success: {response.elapsed.total_seconds():.2f}s")
        else:
            logger.warning(f"Chat completion failed: {response.status_code}")

    @task(2)
    def text_completion(self):
        """Make a text completion request (weighted 2x)."""
        response = self.client.post(
            "/api/llm/v1/completions",
            json={
                "model": self.model_id,
                "prompt": "The capital of France is",
                "max_tokens": 20,
                "temperature": 0.5
            },
            name="/api/llm/v1/completions"
        )

        if response.status_code == 200:
            logger.debug(f"Text completion success: {response.elapsed.total_seconds():.2f}s")
        else:
            logger.warning(f"Text completion failed: {response.status_code}")

    @task(1)
    def check_metrics(self):
        """Check metrics endpoint (weighted 1x)."""
        response = self.client.get(
            "/api/metrics/json",
            name="/api/metrics/json"
        )

        if response.status_code == 200:
            data = response.json()
            logger.debug(f"Metrics: {len(data.get('models', {}))} models tracked")
        else:
            logger.warning(f"Metrics check failed: {response.status_code}")

    @task(1)
    def check_model_info(self):
        """Check model info endpoint (weighted 1x)."""
        response = self.client.get(
            f"/api/llm/v1/models?model={self.model_id}",
            name="/api/llm/v1/models"
        )

        if response.status_code == 200:
            logger.debug(f"Model info retrieved")
        else:
            logger.warning(f"Model info failed: {response.status_code}")


class StressTestUser(HttpUser):
    """
    Stress test user with rapid requests.

    Use this to test rate limiting and error handling under high load.
    """

    # Minimal wait time
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Called when user starts."""
        self.model_id = os.getenv("MODEL_ID", "default")
        auth_token = os.getenv("AUTH_TOKEN")

        if auth_token:
            self.client.headers = {"Authorization": f"Bearer {auth_token}"}

    @task
    def rapid_requests(self):
        """Make rapid small requests."""
        self.client.post(
            "/api/llm/v1/chat/completions",
            json={
                "model": self.model_id,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5
            },
            name="/api/llm/v1/chat/completions [stress]"
        )


# Event handlers for custom statistics
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    logger.info("=" * 60)
    logger.info("FluidMCP Load Test Starting")
    logger.info(f"Target: {environment.host}")
    logger.info(f"Model: {os.getenv('MODEL_ID', 'auto-detected')}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    logger.info("=" * 60)
    logger.info("FluidMCP Load Test Complete")
    logger.info("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Called for each request (optional: custom logging)."""
    if exception:
        logger.warning(f"Request failed: {name} - {exception}")
