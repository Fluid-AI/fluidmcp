"""
Ultra-thin adapter for vLLM Omni multimodal capabilities.

This module provides capability validation and delegation for:
- Image generation (text-to-image)
- Video generation (text-to-video)
- Image animation (image-to-video)

All actual API calls are delegated to replicate_client.py.
"""

from typing import Dict, Any
from fastapi import HTTPException
from loguru import logger


def assert_capability(model_config: Dict[str, Any], model_id: str, required: str) -> None:
    """
    Validate that a model supports a required capability.

    Args:
        model_config: Model configuration dict
        model_id: Model identifier (for error messages)
        required: Required capability string (e.g., "text-to-image")

    Raises:
        HTTPException: 400 if model doesn't support the capability
    """
    capabilities = model_config.get("capabilities", [])

    if required not in capabilities:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model_id}' does not support '{required}' capability. "
                   f"Supported capabilities: {capabilities or 'none specified'}"
        )

    logger.debug(f"Capability validation passed: '{model_id}' supports '{required}'")


async def generate_image(
    model_id: str,
    model_config: Dict[str, Any],
    payload: Dict[str, Any],
    replicate_client
) -> Dict[str, Any]:
    """
    Generate image from text prompt (text-to-image).

    Args:
        model_id: Model identifier
        model_config: Model configuration
        payload: Request payload with prompt and parameters
        replicate_client: ReplicateClient instance

    Returns:
        Prediction response with prediction_id and status

    Raises:
        HTTPException: 400 if model doesn't support text-to-image
    """
    assert_capability(model_config, model_id, "text-to-image")
    logger.info(f"Starting image generation for model '{model_id}'")
    return await replicate_client.predict(payload)


async def generate_video(
    model_id: str,
    model_config: Dict[str, Any],
    payload: Dict[str, Any],
    replicate_client
) -> Dict[str, Any]:
    """
    Generate video from text prompt (text-to-video).

    Args:
        model_id: Model identifier
        model_config: Model configuration
        payload: Request payload with prompt and parameters
        replicate_client: ReplicateClient instance

    Returns:
        Prediction response with prediction_id and status

    Raises:
        HTTPException: 400 if model doesn't support text-to-video
    """
    assert_capability(model_config, model_id, "text-to-video")
    logger.info(f"Starting video generation for model '{model_id}'")
    return await replicate_client.predict(payload)


async def animate_image(
    model_id: str,
    model_config: Dict[str, Any],
    payload: Dict[str, Any],
    replicate_client
) -> Dict[str, Any]:
    """
    Animate image into video (image-to-video).

    Args:
        model_id: Model identifier
        model_config: Model configuration
        payload: Request payload with image_url and parameters
        replicate_client: ReplicateClient instance

    Returns:
        Prediction response with prediction_id and status

    Raises:
        HTTPException: 400 if model doesn't support image-to-video
    """
    assert_capability(model_config, model_id, "image-to-video")
    logger.info(f"Starting image animation for model '{model_id}'")
    return await replicate_client.predict(payload)


async def get_generation_status(
    prediction_id: str,
    replicate_client
) -> Dict[str, Any]:
    """
    Check status of async generation (image/video).

    Args:
        prediction_id: Replicate prediction ID
        replicate_client: ReplicateClient instance

    Returns:
        Prediction status with output URLs when complete
    """
    logger.debug(f"Checking generation status for prediction '{prediction_id}'")
    return await replicate_client.get_prediction(prediction_id)
