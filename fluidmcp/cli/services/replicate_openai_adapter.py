"""
OpenAI-to-Replicate Adapter for FluidMCP.

Converts OpenAI's chat completions format to Replicate's prediction model
and vice versa, enabling unified API access across providers.
"""

import time
import asyncio
import httpx
from typing import Dict, Any, List
from loguru import logger

from .replicate_client import get_replicate_client


def openai_messages_to_prompt(messages: List[Dict[str, str]]) -> str:
    """
    Convert OpenAI chat messages format to a single prompt string.

    Args:
        messages: List of message dicts with 'role' and 'content'

    Returns:
        Formatted prompt string

    Example:
        [{"role": "user", "content": "Hello"}]
        → "Hello"

        [{"role": "system", "content": "You are helpful"},
         {"role": "user", "content": "Hi"}]
        → "System: You are helpful\nUser: Hi"
    """
    if not messages:
        return ""

    # Simple case: single user message
    if len(messages) == 1 and messages[0].get("role") == "user":
        return messages[0].get("content", "")

    # Multiple messages: format with roles
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        if role.lower() == "system":
            prompt_parts.append(f"System: {content}")
        elif role.lower() == "assistant":
            prompt_parts.append(f"Assistant: {content}")
        else:  # user
            prompt_parts.append(f"User: {content}")

    return "\n".join(prompt_parts)


def openai_to_replicate_input(openai_request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert OpenAI chat request to Replicate prediction input.

    Args:
        openai_request: OpenAI-format request with messages, temperature, etc.

    Returns:
        Replicate-format input dict
    """
    messages = openai_request.get("messages", [])
    prompt = openai_messages_to_prompt(messages)

    # Map OpenAI parameters to Replicate input
    replicate_input = {
        "prompt": prompt,
    }

    # Optional parameters
    if "temperature" in openai_request:
        replicate_input["temperature"] = openai_request["temperature"]

    if "max_tokens" in openai_request:
        replicate_input["max_tokens"] = openai_request["max_tokens"]
    elif "max_completion_tokens" in openai_request:  # OpenAI sometimes uses this
        replicate_input["max_tokens"] = openai_request["max_completion_tokens"]

    if "top_p" in openai_request:
        replicate_input["top_p"] = openai_request["top_p"]

    if "stop" in openai_request:
        replicate_input["stop_sequences"] = openai_request["stop"]

    return replicate_input


def replicate_output_to_openai_response(
    prediction: Dict[str, Any],
    model_id: str,
    openai_request: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Convert Replicate prediction output to OpenAI chat completion format.

    Args:
        prediction: Replicate prediction response
        model_id: Model identifier
        openai_request: Original OpenAI request (for context)

    Returns:
        OpenAI-format chat completion response
    """
    output = prediction.get("output", [])

    # Replicate output is usually a list of strings, join them
    if isinstance(output, list):
        content = "".join(str(item) for item in output)
    else:
        content = str(output)

    # Determine finish reason
    status = prediction.get("status", "succeeded")
    if status == "succeeded":
        finish_reason = "stop"
    elif status == "canceled":
        finish_reason = "stop"  # Cancellation doesn't mean token limit hit
    else:
        finish_reason = "stop"

    # Build OpenAI response
    response = {
        "id": f"chatcmpl-{prediction.get('id', 'unknown')}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content.strip()
            },
            "finish_reason": finish_reason
        }],
        "usage": {
            "prompt_tokens": 0,  # Replicate doesn't provide token counts
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }

    return response


async def replicate_chat_completion(
    model_id: str,
    openai_request: Dict[str, Any],
    timeout: int = 300
) -> Dict[str, Any]:
    """
    Execute OpenAI chat completion request using Replicate backend.

    This is the main adapter function that:
    1. Converts OpenAI format → Replicate input
    2. Creates Replicate prediction
    3. Polls until complete
    4. Converts Replicate output → OpenAI format

    Args:
        model_id: Model identifier from FluidMCP config
        openai_request: OpenAI-format chat request
        timeout: Maximum time to wait for completion (seconds)

    Returns:
        OpenAI-format chat completion response

    Raises:
        HTTPException: If model not found or prediction fails
    """
    from fastapi import HTTPException

    # Get Replicate client for this model
    client = get_replicate_client(model_id)
    if not client:
        raise HTTPException(404, f"Model '{model_id}' not found or not a Replicate model")

    # Check if streaming is requested
    if openai_request.get("stream", False):
        raise HTTPException(
            501,
            "Streaming is not supported for Replicate models. Set 'stream': false or omit it."
        )

    # Convert OpenAI request to Replicate input
    replicate_input = openai_to_replicate_input(openai_request)
    logger.debug(f"Converted OpenAI request to Replicate input for '{model_id}'")

    # Create prediction
    try:
        prediction = await client.predict(input_data=replicate_input)
        prediction_id = prediction.get("id")
        logger.info(f"Created Replicate prediction {prediction_id} for model '{model_id}'")
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else 502
        upstream_request_id = (
            e.response.headers.get("x-request-id")
            if e.response is not None
            else None
        )
        log_msg = f"Replicate upstream HTTP error {status_code}"
        if upstream_request_id:
            log_msg += f" (request_id={upstream_request_id})"
        logger.error(f"{log_msg}: {e}")
        message = "Replicate upstream error"
        if upstream_request_id:
            message += f" (request_id={upstream_request_id})"
        raise HTTPException(status_code, message)
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to Replicate upstream service: {e}")
        raise HTTPException(502, "Failed to connect to Replicate upstream service")
    except Exception as e:
        logger.error(f"Failed to create Replicate prediction for '{model_id}': {e}")
        raise HTTPException(500, "Failed to create prediction")

    # Poll until prediction completes (with timeout)
    start_time = time.time()
    poll_interval = 1.0  # Start with 1 second
    max_poll_interval = 5.0  # Cap at 5 seconds

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            logger.warning(f"Prediction {prediction_id} timed out after {timeout}s")
            raise HTTPException(504, f"Prediction timed out after {timeout} seconds")

        # Get prediction status
        try:
            status_result = await client.get_prediction(prediction_id)
            status = status_result.get("status")

            if status == "succeeded":
                logger.info(f"Prediction {prediction_id} completed successfully")
                # Convert to OpenAI format and return
                return replicate_output_to_openai_response(status_result, model_id, openai_request)

            elif status == "failed":
                error = status_result.get("error", "Unknown error")
                logger.error(f"Prediction {prediction_id} failed: {error}")
                raise HTTPException(500, f"Prediction failed: {error}")

            elif status == "canceled":
                logger.warning(f"Prediction {prediction_id} was canceled")
                raise HTTPException(499, "Prediction was canceled")

            # Still processing, wait before next poll
            await asyncio.sleep(poll_interval)

            # Exponential backoff for polling interval
            poll_interval = min(poll_interval * 1.5, max_poll_interval)

        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else 502
            upstream_request_id = (
                e.response.headers.get("x-request-id")
                if e.response is not None
                else None
            )
            log_msg = f"Replicate upstream HTTP error {status_code} while polling {prediction_id}"
            if upstream_request_id:
                log_msg += f" (request_id={upstream_request_id})"
            logger.error(f"{log_msg}: {e}")
            message = "Error checking prediction status"
            if upstream_request_id:
                message += f" (request_id={upstream_request_id})"
            raise HTTPException(status_code, message)
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Replicate while polling {prediction_id}: {e}")
            raise HTTPException(502, "Failed to connect to Replicate upstream service")
        except Exception as e:
            logger.error(f"Error polling prediction {prediction_id}: {e}")
            raise HTTPException(500, "Error checking prediction status")
