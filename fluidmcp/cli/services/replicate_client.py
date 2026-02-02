"""
Replicate Model Client for FluidMCP.

This module provides HTTP-based inference support for Replicate models,
enabling users to run AI models via Replicate's cloud API without local GPU requirements.

Includes error handling, retry logic, and streaming support.
"""

import os
import re
import httpx
import asyncio
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
            # Only check for our supported patterns to avoid false positives
            if re.search(r'\$\{[^}]+\}|\$[A-Z_][A-Z0-9_]*', api_key_raw):
                if api_key_expanded == api_key_raw:
                    raise ValueError(
                        f"Replicate model '{model_id}' has unresolved environment variable "
                        f"in 'api_key': {api_key_raw!r}. Make sure the environment variable is set."
                    )
            self.api_key = api_key_expanded
        else:
            self.api_key = api_key_raw
        self.base_url = config.get("endpoints", {}).get("base_url", REPLICATE_API_BASE)
        self.default_params = config.get("default_params", {})
        self.timeout = config.get("timeout", DEFAULT_TIMEOUT)
        self.max_retries = config.get("max_retries", DEFAULT_MAX_RETRIES)

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

                logger.info(f"Prediction created for model '{self.model_id}': {result.get('id')} (status: {result.get('status')})")
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
                        # Exponential backoff: 0s, 2s, 4s (0 on first retry, then 2^attempt)
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
                    # Exponential backoff: 0s, 2s, 4s (0 on first retry, then 2^attempt)
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
        Stream prediction output as it's generated.

        Args:
            input_data: Input parameters for the model
            version: Optional specific model version to use
            max_stream_seconds: Maximum time to wait for prediction (default: 600 seconds)

        Yields:
            Chunks of model output as they're generated (type depends on model)

        Raises:
            httpx.HTTPError: If API request fails
            asyncio.TimeoutError: If prediction exceeds max_stream_seconds
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

        # Poll for updates with timeout (compatible with Python 3.6+)
        start_time = asyncio.get_event_loop().time()
        try:
            while True:
                # Check if we've exceeded the timeout
                elapsed = asyncio.get_event_loop().time() - start_time
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
        if "/" in self.model_name:
            owner, name = self.model_name.split("/", 1)
            response = await self.client.get(f"/models/{owner}/{name}")
            response.raise_for_status()
            return response.json()
        else:
            raise ValueError(f"Invalid model format: {self.model_name}. Expected 'owner/model-name'")

    async def health_check(self) -> bool:
        """
        Check if the Replicate API is accessible and the model is available.

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
        try:
            client = ReplicateClient(model_id, config)

            # Run health check
            if await client.health_check():
                clients[model_id] = client
                _replicate_clients[model_id] = client
                logger.info(f"Successfully initialized Replicate model '{model_id}'")
            else:
                logger.error(f"Health check failed for Replicate model '{model_id}'")
                await client.close()

        except Exception as e:
            logger.error(f"Failed to initialize Replicate model '{model_id}': {e}")

    logger.info(f"Initialized {len(clients)} Replicate model(s)")
    return clients


async def stop_all_replicate_models() -> None:
    """
    Stop all Replicate clients and cleanup resources.

    This function closes all active HTTP clients but does not cancel
    running predictions (they will continue on Replicate's servers).
    """
    global _replicate_clients

    logger.info(f"Stopping {len(_replicate_clients)} Replicate client(s)")

    # Create snapshot to avoid RuntimeError: dictionary changed size during iteration
    # await client.close() yields control, allowing concurrent modifications
    clients_snapshot = list(_replicate_clients.items())

    for model_id, client in clients_snapshot:
        try:
            await client.close()
            logger.info(f"Stopped Replicate client for model '{model_id}'")
        except Exception as e:
            logger.error(f"Error stopping Replicate client '{model_id}': {e}")

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
    return _replicate_clients.get(model_id)


def list_replicate_models() -> List[str]:
    """
    List all active Replicate model IDs.

    Returns:
        List of model identifiers
    """
    return list(_replicate_clients.keys())
