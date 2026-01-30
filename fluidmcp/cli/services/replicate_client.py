"""
Replicate Model Client for FluidMCP.

This module provides HTTP-based inference support for Replicate models,
enabling users to run AI models via Replicate's cloud API without local GPU requirements.

Includes error handling, retry logic, and streaming support.
"""

import httpx
import asyncio
from typing import Dict, Any, Optional, AsyncIterator, List
from loguru import logger

# Constants
DEFAULT_TIMEOUT = 60.0  # Default timeout for API requests (seconds)
DEFAULT_MAX_RETRIES = 3  # Default maximum retry attempts for failed requests
REPLICATE_API_BASE = "https://api.replicate.com/v1"


class ReplicateClient:
    """
    Client for interacting with Replicate's inference API.

    Handles model predictions, streaming responses, and error recovery for
    Replicate-hosted models.

    Attributes:
        model_id: Replicate model identifier (e.g., "meta/llama-2-70b-chat")
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
        self.api_key = config["api_key"]
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
            "version": version or self.model_name,
            "input": merged_input
        }

        if webhook:
            payload["webhook"] = webhook
        if stream:
            payload["stream"] = True

        logger.debug(f"Creating prediction for model '{self.model_id}' with input keys: {list(merged_input.keys())}")

        # Retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = await self.client.post("/predictions", json=payload)
                response.raise_for_status()
                result = response.json()

                logger.info(f"Prediction created for model '{self.model_id}': {result.get('id')} (status: {result.get('status')})")
                return result

            except httpx.HTTPError as e:
                last_error = e
                logger.warning(
                    f"Prediction request failed for model '{self.model_id}' "
                    f"(attempt {attempt + 1}/{self.max_retries}): {e}"
                )

                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)

        # All retries failed
        logger.error(f"All retry attempts failed for model '{self.model_id}'")
        raise last_error

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
        version: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Stream prediction output as it's generated.

        Args:
            input_data: Input parameters for the model
            version: Optional specific model version to use

        Yields:
            Chunks of model output as they're generated

        Raises:
            httpx.HTTPError: If API request fails
        """
        # Create prediction with streaming enabled
        prediction = await self.predict(input_data, version=version, stream=True)
        prediction_id = prediction["id"]

        logger.debug(f"Streaming prediction {prediction_id} for model '{self.model_id}'")

        # Poll for updates
        while True:
            status = await self.get_prediction(prediction_id)

            if status["status"] == "succeeded":
                # Yield final output
                output = status.get("output", "")
                if output:
                    yield output
                break

            elif status["status"] == "failed":
                error_msg = status.get("error", "Unknown error")
                logger.error(f"Prediction {prediction_id} failed: {error_msg}")
                raise Exception(f"Prediction failed: {error_msg}")

            elif status["status"] in ["starting", "processing"]:
                # Check for partial output
                output = status.get("output", "")
                if output:
                    yield output

                # Wait before next poll
                await asyncio.sleep(0.5)

            else:
                logger.warning(f"Unknown prediction status: {status['status']}")
                await asyncio.sleep(0.5)

    async def list_predictions(
        self,
        cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List predictions for this model.

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

    async def close(self):
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


async def stop_all_replicate_models():
    """
    Stop all Replicate clients and cleanup resources.

    This function closes all active HTTP clients but does not cancel
    running predictions (they will continue on Replicate's servers).
    """
    global _replicate_clients

    logger.info(f"Stopping {len(_replicate_clients)} Replicate client(s)")

    for model_id, client in _replicate_clients.items():
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
