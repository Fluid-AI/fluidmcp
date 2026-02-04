"""
OpenAI-to-Replicate Adapter for FluidMCP.

Converts OpenAI's chat completions format to Replicate's prediction model
and vice versa, enabling unified API access across providers.
"""

import time
import asyncio
import json
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
    
    # Convert OpenAI request to Replicate input
    replicate_input = openai_to_replicate_input(openai_request)
    logger.debug(f"Converted OpenAI request to Replicate input for '{model_id}'")
    
    # Create prediction
    try:
        prediction = await client.predict(input_data=replicate_input)
        prediction_id = prediction.get("id")
        logger.info(f"Created Replicate prediction {prediction_id} for model '{model_id}'")
    except Exception as e:
        logger.error(f"Failed to create Replicate prediction for '{model_id}': {e}")
        raise HTTPException(500, f"Failed to create prediction: {str(e)}")
    
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
        except Exception as e:
            logger.error(f"Error polling prediction {prediction_id}: {e}")
            raise HTTPException(500, f"Error checking prediction status: {str(e)}")


async def replicate_chat_completion_stream(
    model_id: str,
    openai_request: Dict[str, Any],
    timeout: int = 300
):
    """
    Stream chat completion from Replicate in OpenAI SSE format.

    Since Replicate doesn't support true streaming, this polls the prediction
    and yields SSE chunks as the output becomes available.

    Args:
        model_id: The FluidMCP model identifier
        openai_request: OpenAI-format chat completion request
        timeout: Maximum seconds to wait for completion

    Yields:
        SSE-formatted chunks in OpenAI streaming format

    Example SSE output:
        data: {"id":"chatcmpl-123","choices":[{"delta":{"content":"Hello"}}]}

        data: {"id":"chatcmpl-123","choices":[{"delta":{"content":" world"}}]}

        data: [DONE]
    """
    from fastapi import HTTPException

    # Get Replicate client for this model
    client = get_replicate_client(model_id)

    # Convert OpenAI request to Replicate input
    replicate_input = openai_to_replicate_input(openai_request)
    logger.debug(f"Starting streaming prediction for '{model_id}'")

    # Create prediction
    try:
        prediction = await client.predict(input_data=replicate_input)
        prediction_id = prediction.get("id")
        logger.info(f"Created streaming prediction {prediction_id} for model '{model_id}'")
    except Exception as e:
        logger.error(f"Failed to create streaming prediction for '{model_id}': {e}")
        # Yield error as SSE
        error_chunk = {
            "error": {
                "message": f"Failed to create prediction: {str(e)}",
                "type": "prediction_error",
                "code": "prediction_creation_failed"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        return

    # Generate unique chat completion ID
    import uuid
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created_timestamp = int(time.time())

    # Track last output length for delta calculation
    last_output_length = 0

    # Poll until prediction completes
    start_time = time.time()
    poll_interval = 0.5  # Faster polling for streaming (500ms)
    max_poll_interval = 2.0  # Cap at 2 seconds for streaming

    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"Streaming prediction {prediction_id} timed out")
                error_chunk = {
                    "error": {
                        "message": f"Prediction timed out after {timeout} seconds",
                        "type": "timeout",
                        "code": "prediction_timeout"
                    }
                }
                yield f"data: {json.dumps(error_chunk)}\n\n"
                return

            # Get prediction status
            try:
                status_result = await client.get_prediction(prediction_id)
                status = status_result.get("status")
                output = status_result.get("output", "")

                # Handle different statuses
                if status == "succeeded":
                    # Send final delta if there's remaining output
                    if isinstance(output, str) and len(output) > last_output_length:
                        delta_content = output[last_output_length:]
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_timestamp,
                            "model": model_id,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": delta_content},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"

                    # Send final chunk with finish_reason
                    final_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_timestamp,
                        "model": model_id,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                    logger.info(f"Streaming prediction {prediction_id} completed")
                    return

                elif status == "failed":
                    error = status_result.get("error", "Unknown error")
                    logger.error(f"Streaming prediction {prediction_id} failed: {error}")
                    error_chunk = {
                        "error": {
                            "message": f"Prediction failed: {error}",
                            "type": "prediction_error",
                            "code": "prediction_failed"
                        }
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n"
                    return

                elif status == "canceled":
                    logger.warning(f"Streaming prediction {prediction_id} was canceled")
                    error_chunk = {
                        "error": {
                            "message": "Prediction was canceled",
                            "type": "prediction_error",
                            "code": "prediction_canceled"
                        }
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n"
                    return

                # Still processing - check if there's new output to stream
                if isinstance(output, str) and len(output) > last_output_length:
                    delta_content = output[last_output_length:]
                    last_output_length = len(output)

                    # Yield delta chunk
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_timestamp,
                        "model": model_id,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": delta_content},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    logger.debug(f"Streamed {len(delta_content)} chars from prediction {prediction_id}")

                # Wait before next poll
                await asyncio.sleep(poll_interval)

                # Exponential backoff for polling interval (but faster than non-streaming)
                poll_interval = min(poll_interval * 1.3, max_poll_interval)

            except Exception as e:
                logger.error(f"Error polling streaming prediction {prediction_id}: {e}")
                error_chunk = {
                    "error": {
                        "message": f"Error checking prediction status: {str(e)}",
                        "type": "polling_error",
                        "code": "status_check_failed"
                    }
                }
                yield f"data: {json.dumps(error_chunk)}\n\n"
                return

    except Exception as e:
        logger.error(f"Unexpected error in streaming prediction {prediction_id}: {e}")
        error_chunk = {
            "error": {
                "message": f"Unexpected error: {str(e)}",
                "type": "server_error",
                "code": "internal_error"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
