#!/usr/bin/env python3
"""
vLLM MCP Server - Exposes vLLM inference as MCP tools
Communicates via stdin/stdout JSON-RPC protocol
"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional
from vllm import LLM, SamplingParams

# Configure logging to stderr (stdout is reserved for MCP protocol)
env_log_level = os.environ.get("VLLM_LOG_LEVEL", "INFO").upper()
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
if env_log_level not in VALID_LOG_LEVELS:
    env_log_level = "INFO"
log_level = getattr(logging, env_log_level)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("vllm-mcp-server")

# Global vLLM engine
llm_engine: Optional[LLM] = None

def initialize_vllm():
    """Initialize vLLM engine with configuration from environment variables"""
    global llm_engine

    model_name = os.environ.get("VLLM_MODEL_NAME", "facebook/opt-125m")
    dtype = os.environ.get("VLLM_DTYPE", "float16")
    max_model_len = os.environ.get("VLLM_MAX_MODEL_LEN")

    try:
        tensor_parallel_size = int(os.environ.get("VLLM_TENSOR_PARALLEL_SIZE", "1"))
        gpu_memory_utilization = float(os.environ.get("VLLM_GPU_MEMORY_UTILIZATION", "0.9"))
        max_model_len_int = int(max_model_len) if max_model_len else None
    except ValueError as e:
        logger.error(f"Invalid environment variable value: {e}")
        sys.exit(1)

    logger.info(f"Initializing vLLM with model: {model_name}")
    logger.info(f"Tensor parallel size: {tensor_parallel_size}")
    logger.info(f"GPU memory utilization: {gpu_memory_utilization}")

    try:
        llm_config = {
            "model": model_name,
            "tensor_parallel_size": tensor_parallel_size,
            "gpu_memory_utilization": gpu_memory_utilization,
            "dtype": dtype,
        }

        if max_model_len_int:
            llm_config["max_model_len"] = max_model_len_int

        llm_engine = LLM(**llm_config)
        logger.info("vLLM engine initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize vLLM: {e}", exc_info=True)
        sys.exit(1)

def handle_initialize(request_id: Any) -> Dict[str, Any]:
    """Handle MCP initialize request"""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "vllm-mcp-server",
                "version": "1.0.0"
            }
        }
    }

def handle_tools_list(request_id: Any) -> Dict[str, Any]:
    """Handle MCP tools/list request"""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "chat_completion",
                    "description": "Generate chat completions using vLLM",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "messages": {
                                "type": "array",
                                "description": "Array of chat messages with role and content",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                        "content": {"type": "string"}
                                    },
                                    "required": ["role", "content"]
                                }
                            },
                            "temperature": {
                                "type": "number",
                                "description": "Sampling temperature (0.0-2.0)",
                                "default": 0.7,
                                "minimum": 0.0,
                                "maximum": 2.0
                            },
                            "max_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens to generate",
                                "default": 512,
                                "minimum": 1
                            },
                            "top_p": {
                                "type": "number",
                                "description": "Nucleus sampling parameter (0.0-1.0)",
                                "default": 1.0,
                                "minimum": 0.0,
                                "maximum": 1.0
                            }
                        },
                        "required": ["messages"]
                    }
                }
            ]
        }
    }

def validate_messages(messages: Any) -> None:
    """Validate messages array structure"""
    MAX_MESSAGES = 100  # Prevent DoS with extremely large arrays
    MAX_CONTENT_LENGTH = 10000  # Prevent memory exhaustion

    if messages is None:
        raise ValueError("Missing required 'messages' argument")
    if not isinstance(messages, list) or len(messages) == 0:
        raise ValueError("'messages' must be a non-empty array")
    if len(messages) > MAX_MESSAGES:
        raise ValueError(f"'messages' array too large (max {MAX_MESSAGES}, got {len(messages)})")

    allowed_roles = {"system", "user", "assistant"}
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ValueError(f"'messages[{idx}]' must be an object with 'role' and 'content' fields")
        role = msg.get("role")
        content = msg.get("content")
        if not isinstance(role, str) or role not in allowed_roles:
            raise ValueError(f"'messages[{idx}].role' must be one of {sorted(allowed_roles)}")
        if not isinstance(content, str):
            raise ValueError(f"'messages[{idx}].content' must be a string")
        if not content.strip():
            raise ValueError(f"'messages[{idx}].content' must not be empty")
        if len(content) > MAX_CONTENT_LENGTH:
            raise ValueError(f"'messages[{idx}].content' too long (max {MAX_CONTENT_LENGTH} chars)")

def validate_sampling_params(temperature: Any, max_tokens: Any, top_p: Any) -> tuple:
    """Validate sampling parameters are within acceptable ranges

    Returns: (temperature, max_tokens, top_p) as validated numeric types
    """
    MAX_TOKENS_LIMIT = 16384  # Reasonable upper bound for most models

    # Type validation
    try:
        temperature_f = float(temperature)
        max_tokens_i = int(max_tokens)
        top_p_f = float(top_p)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid parameter types: {e}")

    # Range validation
    if not (0.0 <= temperature_f <= 2.0):
        raise ValueError(f"temperature must be between 0.0 and 2.0, got {temperature_f}")
    if max_tokens_i < 1:
        raise ValueError(f"max_tokens must be at least 1, got {max_tokens_i}")
    if max_tokens_i > MAX_TOKENS_LIMIT:
        raise ValueError(f"max_tokens too large (max {MAX_TOKENS_LIMIT}, got {max_tokens_i})")
    if not (0.0 <= top_p_f <= 1.0):
        raise ValueError(f"top_p must be between 0.0 and 1.0, got {top_p_f}")

    return (temperature_f, max_tokens_i, top_p_f)

def handle_chat_completion(request_id: Any, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle chat completion tool call using vLLM"""
    # Check engine is initialized
    if llm_engine is None:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": "vLLM engine not initialized"
            }
        }

    try:
        messages = arguments.get("messages")
        validate_messages(messages)

        temperature = arguments.get("temperature", 0.7)
        max_tokens = arguments.get("max_tokens", 512)
        top_p = arguments.get("top_p", 1.0)

        # Validate and get properly typed values
        temperature, max_tokens, top_p = validate_sampling_params(temperature, max_tokens, top_p)

        # Simple prompt formatting (naive concatenation) - safe after validation
        prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])

        logger.info(f"Generating completion with {len(messages)} messages")

        # Create sampling parameters
        sampling_params = SamplingParams(
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )

        # Generate with vLLM
        outputs = llm_engine.generate([prompt], sampling_params)

        # Validate outputs exist
        if not outputs or not outputs[0].outputs:
            logger.error("vLLM returned no outputs")
            raise ValueError("No outputs generated from model")

        generated_text = outputs[0].outputs[0].text

        logger.info(f"Generated {len(generated_text)} characters")

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": generated_text}]
            }
        }

    except ValueError as e:
        # Validation errors
        logger.error(f"Validation error: {e}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32602,
                "message": f"Invalid params: {str(e)}"
            }
        }
    except Exception as e:
        logger.error(f"Error in chat completion: {e}", exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": f"Error: {str(e)}"
            }
        }

def handle_tools_call(request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP tools/call request"""
    tool_name = params.get("name")

    if tool_name is None:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32602,
                "message": "Missing required 'name' parameter"
            }
        }

    arguments = params.get("arguments", {})

    if tool_name == "chat_completion":
        return handle_chat_completion(request_id, arguments)
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32602,
                "message": f"Unknown tool: {tool_name}"
            }
        }

def process_request(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process a single MCP JSON-RPC request

    Returns None for notifications (no response needed),
    otherwise returns response dict
    """
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params", {})

    # Handle notifications (no response expected)
    if method == "notifications/initialized":
        logger.debug("Received initialized notification")
        return None

    # Handle regular requests
    if method == "initialize":
        return handle_initialize(request_id)
    elif method == "tools/list":
        return handle_tools_list(request_id)
    elif method == "tools/call":
        return handle_tools_call(request_id, params)
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }

def main():
    """Main MCP server loop - read from stdin, write to stdout"""
    logger.info("Starting vLLM MCP Server")

    # Initialize vLLM engine
    initialize_vllm()

    logger.info("Ready to accept MCP requests")

    # MCP protocol loop
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            request_id = None
            try:
                request = json.loads(line)

                # Validate request is a JSON object (dict)
                if not isinstance(request, dict):
                    logger.error(f"Invalid Request: expected JSON object, got {type(request).__name__}")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32600,
                            "message": "Invalid Request"
                        }
                    }
                    print(json.dumps(error_response), flush=True)
                    continue

                request_id = request.get("id")
                logger.debug(f"Received request: {request.get('method')}")

                response = process_request(request)

                # Write response to stdout only if not a notification
                if response is not None:
                    print(json.dumps(response), flush=True)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error"
                    }
                }
                print(json.dumps(error_response), flush=True)

            except Exception as e:
                logger.error(f"Error processing request: {e}", exc_info=True)
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                }
                print(json.dumps(error_response), flush=True)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
