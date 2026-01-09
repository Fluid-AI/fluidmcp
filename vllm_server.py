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

# ---------------------------
# Module-level constants
# ---------------------------
MAX_MESSAGES = int(os.environ.get("VLLM_MAX_MESSAGES", 100))
MAX_CONTENT_LENGTH = int(os.environ.get("VLLM_MAX_CONTENT_LENGTH", 10000))
MAX_TOTAL_CONTENT = int(os.environ.get("VLLM_MAX_TOTAL_CONTENT", 100000))
MAX_TOKENS_LIMIT = int(os.environ.get("VLLM_MAX_TOKENS_LIMIT", 16384))

# Valid data types and log levels
VALID_DTYPES = {"float16", "bfloat16", "float32"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# ---------------------------
# Logging setup
# ---------------------------
env_log_level = os.environ.get("VLLM_LOG_LEVEL", "INFO").upper()
if env_log_level not in VALID_LOG_LEVELS:
    env_log_level = "INFO"
log_level = getattr(logging, env_log_level)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("vllm-mcp-server")

# ---------------------------
# Global vLLM engine
# ---------------------------
llm_engine: Optional[LLM] = None

# ---------------------------
# Initialization
# ---------------------------
def initialize_vllm():
    """Initialize vLLM engine with environment configuration"""
    global llm_engine

    model_name = os.environ.get("VLLM_MODEL_NAME", "facebook/opt-125m")
    dtype = os.environ.get("VLLM_DTYPE", "float16")
    max_model_len = os.environ.get("VLLM_MAX_MODEL_LEN")

    # Validate dtype
    if dtype not in VALID_DTYPES:
        logger.error(f"Invalid VLLM_DTYPE='{dtype}', must be one of {sorted(VALID_DTYPES)}")
        sys.exit(1)

    # Parse tensor_parallel_size
    try:
        tensor_parallel_size = int(os.environ.get("VLLM_TENSOR_PARALLEL_SIZE", "1"))
        if tensor_parallel_size < 1:
            raise ValueError()
    except ValueError:
        logger.error("Invalid VLLM_TENSOR_PARALLEL_SIZE, must be integer >=1")
        sys.exit(1)

    # Parse GPU memory utilization
    try:
        gpu_memory_utilization = float(os.environ.get("VLLM_GPU_MEMORY_UTILIZATION", "0.9"))
        if not (0.0 < gpu_memory_utilization <= 1.0):
            raise ValueError()
    except ValueError:
        logger.error("Invalid VLLM_GPU_MEMORY_UTILIZATION, must be float in (0.0, 1.0]")
        sys.exit(1)

    # Parse max_model_len
    max_model_len_int = None
    if max_model_len:
        try:
            max_model_len_int = int(max_model_len)
            if max_model_len_int <= 0:
                raise ValueError()
        except ValueError:
            logger.error("Invalid VLLM_MAX_MODEL_LEN, must be integer >0")
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

# ---------------------------
# MCP handlers
# ---------------------------
def handle_initialize(request_id: Any) -> Dict[str, Any]:
    """MCP initialize request"""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "vllm-mcp-server", "version": "1.0.0"},
        },
    }

def handle_tools_list(request_id: Any) -> Dict[str, Any]:
    """MCP tools/list request"""
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
                                        "content": {"type": "string"},
                                    },
                                    "required": ["role", "content"],
                                },
                            },
                            "temperature": {"type": "number", "default": 0.7, "minimum": 0.0, "maximum": 2.0},
                            "max_tokens": {"type": "integer", "default": 512, "minimum": 1, "maximum": MAX_TOKENS_LIMIT},
                            "top_p": {"type": "number", "default": 1.0, "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["messages"],
                    },
                }
            ]
        },
    }

# ---------------------------
# Validation helpers
# ---------------------------
def validate_messages(messages: Any) -> None:
    """Validate message array and content lengths"""
    if messages is None:
        raise ValueError("Missing 'messages' argument")
    if not isinstance(messages, list) or len(messages) == 0:
        raise ValueError("'messages' must be a non-empty array")
    if len(messages) > MAX_MESSAGES:
        raise ValueError(f"'messages' array too large (max {MAX_MESSAGES})")

    total_content_length = 0
    allowed_roles = {"system", "user", "assistant"}

    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ValueError(f"'messages[{idx}]' must be an object")
        role = msg.get("role")
        content = msg.get("content")
        if role not in allowed_roles:
            raise ValueError(f"'messages[{idx}].role' must be one of {sorted(allowed_roles)}")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"'messages[{idx}].content' must be non-empty string")
        if len(content) > MAX_CONTENT_LENGTH:
            raise ValueError(f"'messages[{idx}].content too long (max {MAX_CONTENT_LENGTH})")

        total_content_length += len(content)

    if total_content_length > MAX_TOTAL_CONTENT:
        raise ValueError(f"Total content length too large (max {MAX_TOTAL_CONTENT}, got {total_content_length})")

def validate_sampling_params(temperature: Any, max_tokens: Any, top_p: Any) -> tuple:
    """Validate temperature, max_tokens, top_p"""
    try:
        temperature_f = float(temperature)
        max_tokens_i = int(max_tokens)
        top_p_f = float(top_p)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid parameter types: {e}")

    if not (0.0 <= temperature_f <= 2.0):
        raise ValueError(f"temperature must be between 0.0 and 2.0 inclusive")
    if not (1 <= max_tokens_i <= MAX_TOKENS_LIMIT):
        raise ValueError(f"max_tokens must be 1-{MAX_TOKENS_LIMIT}")
    if not (0.0 <= top_p_f <= 1.0):
        raise ValueError("top_p must be between 0.0 and 1.0")

    return temperature_f, max_tokens_i, top_p_f

# ---------------------------
# Tool handlers
# ---------------------------
def handle_chat_completion(request_id: Any, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle chat_completion tool"""
    if llm_engine is None:
        logger.critical("vLLM engine is None in handle_chat_completion")
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": "Internal server error: vLLM engine not initialized"}}

    try:
        messages = arguments.get("messages")
        validate_messages(messages)

        temperature = arguments.get("temperature", 0.7)
        max_tokens = arguments.get("max_tokens", 512)
        top_p = arguments.get("top_p", 1.0)
        temperature, max_tokens, top_p = validate_sampling_params(temperature, max_tokens, top_p)

        # Build prompt
        prompt_lines = []
        idx = None
        try:
            for idx, msg in enumerate(messages):
                prompt_lines.append(f"{msg['role']}: {msg['content']}")
            prompt = "\n".join(prompt_lines)
        except KeyError as e:
            missing_key = e.args[0] if e.args else "unknown"
            raise ValueError(f"Message at index {idx} missing field '{missing_key}'")

        logger.info(f"Generating completion with {len(messages)} messages")

        sampling_params = SamplingParams(temperature=temperature, max_tokens=max_tokens, top_p=top_p)
        outputs = llm_engine.generate([prompt], sampling_params)

        if not outputs or not outputs[0].outputs:
            logger.error("vLLM returned no outputs")
            raise ValueError("No outputs generated from model")

        generated_text = outputs[0].outputs[0].text
        logger.info(f"Generated {len(generated_text)} code points (string length, not tokens)")

        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": generated_text}]}}
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": f"Invalid params: {e}"}}
    except Exception as e:
        logger.error(f"Unexpected error in chat completion: {e}", exc_info=True)
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": "Unexpected error during chat completion"}}

def handle_tools_call(request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP tools/call"""
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid params: expected object"}}

    tool_name = params.get("name")
    if not tool_name:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Missing 'name' parameter"}}

    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid arguments: expected object"}}

    if tool_name == "chat_completion":
        return handle_chat_completion(request_id, arguments)
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}}

def process_request(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process a single MCP JSON-RPC request"""
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params", {})

    # Notifications do not require response
    if method == "notifications/initialized":
        logger.debug("Received initialized notification")
        return None

    if method == "initialize":
        return handle_initialize(request_id)
    elif method == "tools/list":
        return handle_tools_list(request_id)
    elif method == "tools/call":
        return handle_tools_call(request_id, params)
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

# ---------------------------
# Main MCP loop
# ---------------------------
def main():
    """Main MCP loop. Sequential only. Batch requests not supported."""
    logger.info("Starting vLLM MCP Server")
    initialize_vllm()
    logger.info("Ready to accept MCP requests")

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            request_id = None
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    logger.error(f"Invalid Request: expected JSON object, got {type(request).__name__}")
                    print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}), flush=True)
                    continue

                request_id = request.get("id")
                logger.debug(f"Received request: {request.get('method')}")
                response = process_request(request)

                if response is not None:
                    print(json.dumps(response), flush=True)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}), flush=True)

            except Exception as e:
                logger.error(f"Error processing request: {e}", exc_info=True)
                print(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": "Internal error"}}), flush=True)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
