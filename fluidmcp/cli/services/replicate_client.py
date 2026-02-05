"""
Replicate Model Client for FluidMCP.

This module provides HTTP-based inference support for Replicate models,
enabling users to run AI models via Replicate's cloud API without local GPU requirements.

Includes error handling, retry logic, and streaming support.
"""

import os
import re
import time
import httpx
import asyncio
import threading
from typing import Dict, Any, Optional, AsyncIterator, List
from loguru import logger

# Constants
DEFAULT_TIMEOUT = 60.0  # Default timeout for API requests (seconds)
DEFAULT_MAX_RETRIES = 3  # Default maximum retry attempts for failed requests
DEFAULT_MAX_STREAM_SECONDS = 600  # Default maximum time for streaming predictions (10 minutes)
REPLICATE_API_BASE = "https://api.replicate.com/v1"


class ReplicateClient:
    """
    Client for interacting with Replicate's inference API.

    Handles model predictions, streaming responses, and error recovery for
    Replicate-hosted models.

    Attributes:
        model_id: Local registry key for this model instance (e.g., "llama-2-70b")
        model_name: Replicate model path (e.g., "meta/llama-2-70b-chat")
        api_key: Replicate API authentication token
        config: Model configuration including endpoints and default parameters
    """

    def __init__(self, model_id: str, config: Dict[str, Any]):
        """
        Initialize Replicate client.

        Args:
            model_id: Unique identifier for this model instance
            config: Configuration dictionary containing:
                - model: Replicate model name (e.g., "meta/llama-2-70b-chat")
                - api_key: Replicate API token
                - endpoints: Optional custom endpoints
                - default_params: Optional default inference parameters
                - timeout: Optional request timeout in seconds
                - max_retries: Optional maximum retry attempts

        Raises:
            ValueError: If required configuration fields are missing
        """
        self.model_id = model_id
        self.config = config

        # Validate required fields
        if "model" not in config:
            raise ValueError(f"Replicate model '{model_id}' missing 'model' in config")
        if "api_key" not in config:
            raise ValueError(f"Replicate model '{model_id}' missing 'api_key' in config")

        self.model_name = config["model"]
        # Expand environment variables in API key (e.g., ${REPLICATE_API_TOKEN})
        api_key_raw = config["api_key"]
        if isinstance(api_key_raw, str):
            api_key_expanded = os.path.expandvars(api_key_raw)
            # Check if ${VAR} or $VAR pattern was not resolved
            # Support both uppercase and lowercase variable names (e.g., $PATH, $api_key)
            if re.search(r'\$\{[^}]+\}|\$[a-zA-Z_][a-zA-Z0-9_]*', api_key_raw):
                if api_key_expanded == api_key_raw:
                    raise ValueError(
                        f"Replicate model '{model_id}' has unresolved environment variable "
                        f"in 'api_key': {api_key_raw!r}. Make sure the environment variable is set."
                    )
            self.api_key = api_key_expanded
        else:
            self.api_key = api_key_raw
        # Validate optional dict-typed configuration fields
        endpoints = config.get("endpoints")
        if endpoints is not None and not isinstance(endpoints, dict):
            raise ValueError(
                f"Replicate model '{model_id}' has invalid 'endpoints' config: "
                f"expected a dict, got {type(endpoints).__name__}"
            )
        default_params = config.get("default_params")
        if default_params is not None and not isinstance(default_params, dict):
            raise ValueError(
                f"Replicate model '{model_id}' has invalid 'default_params' config: "
                f"expected a dict, got {type(default_params).__name__}"
            )
        self.base_url = (endpoints or {}).get("base_url", REPLICATE_API_BASE)
        self.default_params = default_params or {}

        # Validate numeric configuration fields
        timeout = config.get("timeout", DEFAULT_TIMEOUT)
        if not isinstance(timeout, (int, float)):
            raise ValueError(
                f"Replicate model '{model_id}' has invalid 'timeout' config: "
                f"expected a number, got {type(timeout).__name__}"
            )
        if timeout <= 0:
            raise ValueError(
                f"Replicate model '{model_id}' has invalid 'timeout' config: "
                f"must be positive, got {timeout}"
            )
        self.timeout = timeout

        max_retries = config.get("max_retries", DEFAULT_MAX_RETRIES)
        if not isinstance(max_retries, int):
            raise ValueError(
                f"Replicate model '{model_id}' has invalid 'max_retries' config: "
                f"expected an integer, got {type(max_retries).__name__}"
            )
        if max_retries < 0:
            raise ValueError(
                f"Replicate model '{model_id}' has invalid 'max_retries' config: "
                f"must be non-negative, got {max_retries}"
            )
        self.max_retries = max_retries

        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=self.timeout
        )

        logger.info(f"Initialized Replicate client for model '{model_id}' (model: {self.model_name})")

    async def predict(
        self,
        input_data: Dict[str, Any],
        version: Optional[str] = None,
        webhook: Optional[str] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Run a prediction on the Replicate model.

        Args:
            input_data: Input parameters for the model
            version: Optional specific model version to use
            webhook: Optional webhook URL for completion notification
            stream: Whether to stream the response

        Returns:
            Prediction response from Replicate API containing:
                - id: Prediction ID
                - status: Prediction status (starting, processing, succeeded, failed)
                - output: Model output (when completed)
                - error: Error message (if failed)

        Raises:
            httpx.HTTPError: If API request fails after retries
        """
        # Merge default params with provided input
        merged_input = {**self.default_params, **input_data}

        payload = {
            "input": merged_input
        }

        # Only include version if explicitly provided (version ID, not model name)
        if version:
            payload["version"] = version

        if webhook:
            payload["webhook"] = webhook
        if stream:
            payload["stream"] = True

        # Use model-scoped endpoint (accepts owner/name) if no version specified
        # Otherwise use version-scoped endpoint
        endpoint = f"/models/{self.model_name}/predictions" if not version else "/predictions"

        logger.debug(f"Creating prediction for model '{self.model_id}' with input keys: {list(merged_input.keys())}")

        # Retry logic (max_retries = number of retries AFTER initial attempt)
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post(endpoint, json=payload)
                response.raise_for_status()
                result = response.json()

                logger.info(
                    f"Prediction created for model '{self.model_id}': "
                    f"{result.get('id')} (status: {result.get('status')})"
                )
                return result

            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code

                # Only retry on transient errors (429 rate limit and 5xx server errors)
                should_retry = status_code == 429 or (500 <= status_code < 600)

                if should_retry:
                    logger.warning(
                        f"Transient error {status_code} for model '{self.model_id}' "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                    )

                    if attempt < self.max_retries:
                        # Exponential backoff: 0s, 2s, 4s (for max_retries=3)
                        # First retry is immediate, subsequent retries use 2^attempt seconds
                        wait_time = 0 if attempt == 0 else (2 ** attempt)
                        if wait_time > 0:
                            await asyncio.sleep(wait_time)
                else:
                    # Don't retry on client errors (400, 401, 403, 404, 422, etc.)
                    logger.error(
                        f"Non-retryable error {status_code} for model '{self.model_id}': {e}"
                    )
                    raise e

            except (httpx.RequestError, httpx.TimeoutException) as e:
                # Network errors and timeouts - retry these
                last_error = e
                logger.warning(
                    f"Network/timeout error for model '{self.model_id}' "
                    f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                )

                if attempt < self.max_retries:
                    # Exponential backoff: 0s, 2s, 4s (for max_retries=3)
                    # First retry is immediate, subsequent retries use 2^attempt seconds
                    wait_time = 0 if attempt == 0 else (2 ** attempt)
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)

        # All retries failed
        logger.error(f"All retry attempts failed for model '{self.model_id}'")
        if last_error is not None:
            raise last_error
        raise RuntimeError(
            f"Prediction request failed for model '{self.model_id}', "
            "but no error was captured."
        )

    async def get_prediction(self, prediction_id: str) -> Dict[str, Any]:
        """
        Get the status and output of a prediction.

        Args:
            prediction_id: ID of the prediction to retrieve

        Returns:
            Prediction status and output

        Raises:
            httpx.HTTPError: If API request fails
        """
        response = await self.client.get(f"/predictions/{prediction_id}")
        response.raise_for_status()
        return response.json()

    async def cancel_prediction(self, prediction_id: str) -> Dict[str, Any]:
        """
        Cancel a running prediction.

        Args:
            prediction_id: ID of the prediction to cancel

        Returns:
            Cancellation response

        Raises:
            httpx.HTTPError: If API request fails
        """
        logger.info(f"Canceling prediction {prediction_id} for model '{self.model_id}'")
        response = await self.client.post(f"/predictions/{prediction_id}/cancel")
        response.raise_for_status()
        return response.json()

    async def stream_prediction(
        self,
        input_data: Dict[str, Any],
        version: Optional[str] = None,
        max_stream_seconds: Optional[float] = None
    ) -> AsyncIterator[Any]:
        """
        Stream prediction output incrementally via polling (NOT true SSE streaming).

        ⚠️ IMPORTANT: This is NOT real-time token-by-token streaming. Replicate's API
        is polling-based, so this method polls every 0.5 seconds and yields incremental
        output. For true SSE streaming, use providers like vLLM or OpenAI.

        The polling implementation:
        1. Creates a prediction
        2. Polls status every 0.5 seconds
        3. Yields new output when detected
        4. Continues until prediction succeeds/fails or timeout

        Args:
            input_data: Input parameters for the model
            version: Optional specific model version to use
            max_stream_seconds: Maximum time to wait for prediction (default: 600 seconds)

        Yields:
            Chunks of model output as they're generated (type depends on model)

        Raises:
            httpx.HTTPError: If API request fails
            asyncio.TimeoutError: If prediction exceeds max_stream_seconds
            RuntimeError: If prediction fails with error

        Note:
            This method is deprecated for OpenAI-compatible endpoints. Use the
            polling mechanism directly or switch to a provider with native streaming.
        """
        # Create prediction (polling-based incremental output)
        prediction = await self.predict(input_data, version=version, stream=False)
        prediction_id = prediction["id"]

        logger.debug(f"Streaming prediction {prediction_id} for model '{self.model_id}'")

        # Track last output to avoid duplicates
        last_output = None

        # Set timeout
        if max_stream_seconds is None:
            max_stream_seconds = DEFAULT_MAX_STREAM_SECONDS

        # Poll for updates with timeout
        start_time = time.monotonic()
        try:
            while True:
                # Check if we've exceeded the timeout
                elapsed = time.monotonic() - start_time
                if elapsed > max_stream_seconds:
                    raise asyncio.TimeoutError(f"Prediction exceeded maximum stream time of {max_stream_seconds}s")

                status = await self.get_prediction(prediction_id)
                current_output = status.get("output", "")

                if status["status"] == "succeeded":
                    # Yield only new output
                    if current_output and current_output != last_output:
                        yield current_output
                    break

                elif status["status"] == "failed":
                    error_msg = status.get("error", "Unknown error")
                    logger.error(f"Prediction {prediction_id} failed: {error_msg}")
                    raise RuntimeError(f"Prediction failed: {error_msg}")

                elif status["status"] in ["canceled", "cancelled"]:
                    # Prediction was canceled - stop streaming immediately
                    logger.info(f"Prediction {prediction_id} was canceled")
                    break

                elif status["status"] in ["starting", "processing"]:
                    # Only yield if output has changed
                    if current_output and current_output != last_output:
                        yield current_output
                        last_output = current_output

                    # Wait before next poll
                    await asyncio.sleep(0.5)

                else:
                    logger.warning(f"Unknown prediction status: {status['status']}")
                    await asyncio.sleep(0.5)
        except asyncio.TimeoutError:
            logger.error(f"Prediction {prediction_id} exceeded max stream time of {max_stream_seconds}s")
            # Attempt to cancel the prediction
            try:
                await self.cancel_prediction(prediction_id)
            except Exception as e:
                logger.warning(f"Failed to cancel prediction {prediction_id}: {e}")
            raise

    async def list_predictions(
        self,
        cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List all predictions for your Replicate account (not filtered by model).

        Note: This returns account-wide predictions, not just predictions for this model instance.

        Args:
            cursor: Pagination cursor from previous response

        Returns:
            List of predictions with pagination info

        Raises:
            httpx.HTTPError: If API request fails
        """
        params = {}
        if cursor:
            params["cursor"] = cursor

        response = await self.client.get("/predictions", params=params)
        response.raise_for_status()
        return response.json()

    async def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the model.

        Returns:
            Model metadata including versions, schema, and description

        Raises:
            httpx.HTTPError: If API request fails
        """
        # Parse model owner and name from model string
        if "/" not in self.model_name:
            raise ValueError(f"Invalid model format: '{self.model_name}'. Expected 'owner/model-name' format")

        parts = self.model_name.split("/")
        if len(parts) != 2:
            raise ValueError(
                f"Invalid model format: '{self.model_name}'. "
                f"Expected exactly one slash in 'owner/model-name' format, got {len(parts)-1} slashes"
            )

        owner, name = parts
        if not owner or not name:
            raise ValueError(
                f"Invalid model format: '{self.model_name}'. "
                f"Both owner and model-name must be non-empty"
            )

        response = await self.client.get(f"/models/{owner}/{name}")
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> bool:
        """
        Check if the Replicate API is accessible and the model is available.

        ⚠️ LIMITATION: This health check only verifies that:
        1. The Replicate API is reachable
        2. The model metadata can be retrieved (get_model_info succeeds)

        It does NOT verify:
        - Whether your API key has inference permissions for this model
        - Whether the model is currently available for predictions
        - Whether you have sufficient credits/quota

        A passing health check means the model exists and is publicly accessible,
        but predictions may still fail if you lack inference permissions or quota.

        For production deployments, consider implementing a warmup prediction
        (create + cancel) to fully validate credentials and permissions.

        Returns:
            True if API is accessible and model exists, False otherwise
        """
        try:
            await self.get_model_info()
            logger.debug(f"Health check passed for Replicate model '{self.model_id}'")
            return True
        except Exception as e:
            logger.warning(f"Health check failed for Replicate model '{self.model_id}': {e}")
            return False

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        await self.client.aclose()
        logger.info(f"Closed Replicate client for model '{self.model_id}'")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global registry of active Replicate clients
_replicate_clients: Dict[str, ReplicateClient] = {}
# Thread-safety lock for registry operations
_registry_lock = threading.RLock()


async def initialize_replicate_models(replicate_models: Dict[str, Dict[str, Any]]) -> Dict[str, ReplicateClient]:
    """
    Initialize all Replicate models from configuration.

    Args:
        replicate_models: Dictionary of model configurations from config file

    Returns:
        Dictionary mapping model IDs to initialized ReplicateClient instances

    Example:
        >>> config = {
        ...     "llama-2-70b": {
        ...         "model": "meta/llama-2-70b-chat",
        ...         "api_key": "r8_...",
        ...         "default_params": {"temperature": 0.7}
        ...     }
        ... }
        >>> clients = await initialize_replicate_models(config)
    """
    global _replicate_clients

    clients = {}

    for model_id, config in replicate_models.items():
        client = None
        try:
            client = ReplicateClient(model_id, config)

            # Run health check
            if await client.health_check():
                clients[model_id] = client
                # Thread-safe registry update
                with _registry_lock:
                    _replicate_clients[model_id] = client
                logger.info(f"Successfully initialized Replicate model '{model_id}'")
            else:
                logger.error(f"Health check failed for Replicate model '{model_id}'")
                await client.close()
                client = None  # Prevent double-close in finally

        except Exception as e:
            logger.error(f"Failed to initialize Replicate model '{model_id}': {e}")
        finally:
            # Ensure client is closed if initialization or health check failed with exception
            if client is not None and model_id not in clients:
                try:
                    await client.close()
                except Exception as close_error:
                    logger.warning(f"Error closing Replicate client '{model_id}': {close_error}")

    logger.info(f"Initialized {len(clients)} Replicate model(s)")
    return clients


async def stop_all_replicate_models() -> None:
    """
    Stop all Replicate clients and cleanup resources.

    This function closes all active HTTP clients but does not cancel
    running predictions (they will continue on Replicate's servers).
    """
    global _replicate_clients

    # Thread-safe snapshot creation
    with _registry_lock:
        clients_count = len(_replicate_clients)
        # Create snapshot to avoid RuntimeError: dictionary changed size during iteration
        # await client.close() yields control, allowing concurrent modifications
        clients_snapshot = list(_replicate_clients.items())

    logger.info(f"Stopping {clients_count} Replicate client(s)")

    for model_id, client in clients_snapshot:
        try:
            await client.close()
            logger.info(f"Stopped Replicate client for model '{model_id}'")
        except Exception as e:
            logger.error(f"Error stopping Replicate client '{model_id}': {e}")

    # Thread-safe registry clear
    with _registry_lock:
        _replicate_clients.clear()
    logger.info("All Replicate clients stopped")


def get_replicate_client(model_id: str) -> Optional[ReplicateClient]:
    """
    Get an active Replicate client by model ID.

    Args:
        model_id: The model identifier

    Returns:
        ReplicateClient instance or None if not found
    """
    # Thread-safe registry read
    with _registry_lock:
        return _replicate_clients.get(model_id)


def list_replicate_models() -> List[str]:
    """
    List all active Replicate model IDs.

    Returns:
        List of model identifiers
    """
    # Thread-safe registry read
    with _registry_lock:
        return list(_replicate_clients.keys())
