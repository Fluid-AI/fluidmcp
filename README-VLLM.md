# vLLM MCP Server

A native MCP (Model Context Protocol) server that exposes vLLM's high-performance LLM inference capabilities through stdin/stdout JSON-RPC protocol.

## Overview

The vLLM MCP server runs vLLM directly in-process and communicates via the MCP protocol, allowing FluidMCP to orchestrate LLM inference alongside other MCP tools. This provides:

- **High Performance**: vLLM's optimized inference engine with GPU acceleration
- **Native MCP Integration**: Pure stdin/stdout JSON-RPC protocol
- **Multi-turn Conversations**: Session-based conversation history management
- **Production Ready**: Comprehensive error handling, logging, and graceful shutdown

## Quick Start

### Prerequisites

- Python 3.9 or higher
- CUDA-capable GPU (optional but strongly recommended)
- vLLM package installed: `pip install vllm>=0.6.0`

### Installation

1. Install vLLM:
```bash
pip install vllm>=0.6.0
```

2. For gated models (Llama, Mistral, etc.), set your HuggingFace token:
```bash
export HUGGING_FACE_HUB_TOKEN="your_token_here"
```

### Running with FluidMCP

1. Use the provided configuration:
```bash
fluidmcp run examples/vllm-config.json --file --start-server
```

2. The server will start on `http://localhost:8099`

3. Access the Swagger UI at `http://localhost:8099/docs`

### Testing the Server

Test via FluidMCP's unified gateway:
```bash
curl -X POST http://localhost:8099/vllm/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "chat_completion",
      "arguments": {
        "messages": [
          {"role": "user", "content": "What is machine learning?"}
        ],
        "max_tokens": 100
      }
    }
  }'
```

## Configuration

All configuration is done via environment variables in the config file.

### Model Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `VLLM_MODEL_NAME` | HuggingFace model name | `facebook/opt-125m` |
| `VLLM_TENSOR_PARALLEL_SIZE` | Number of GPUs for tensor parallelism | `1` |
| `VLLM_GPU_MEMORY_UTILIZATION` | GPU memory ratio (0.0-1.0) | `0.9` |
| `VLLM_MAX_MODEL_LEN` | Maximum context length | Model's default |
| `VLLM_DTYPE` | Data type: float16, bfloat16, float32 | `float16` |
| `HUGGING_FACE_HUB_TOKEN` | Token for gated models | (empty) |

### Sampling Defaults

| Variable | Description | Default |
|----------|-------------|---------|
| `VLLM_DEFAULT_TEMPERATURE` | Default temperature | `0.7` |
| `VLLM_DEFAULT_MAX_TOKENS` | Default max tokens | `512` |
| `VLLM_DEFAULT_TOP_P` | Default nucleus sampling | `1.0` |
| `VLLM_DEFAULT_TOP_K` | Default top-k sampling | `-1` (disabled) |

### Session Management

| Variable | Description | Default |
|----------|-------------|---------|
| `VLLM_MAX_SESSIONS` | Maximum concurrent sessions | `100` |
| `VLLM_MAX_SESSION_MESSAGES` | Max messages per session before truncation | `50` |

### Logging

| Variable | Description | Default |
|----------|-------------|---------|
| `VLLM_LOG_LEVEL` | Log level: DEBUG, INFO, WARNING, ERROR | `INFO` |

## Supported Models

The vLLM MCP server works with any HuggingFace model supported by vLLM:

### Chat Models (Auto-detected)
- **LLaMA**: `meta-llama/Llama-2-7b-chat-hf`, `meta-llama/Meta-Llama-3-8B-Instruct`
- **Mistral**: `mistralai/Mistral-7B-Instruct-v0.2`
- **Gemma**: `google/gemma-7b-it`
- **Phi-3**: `microsoft/Phi-3-mini-4k-instruct`

The server automatically detects and uses the model's chat template via `tokenizer.apply_chat_template()`.

### Base Models
- **OPT**: `facebook/opt-125m`, `facebook/opt-1.3b`
- **GPT-2**: `gpt2`, `gpt2-medium`

Base models use naive prompt concatenation.

## API Reference

### MCP Tools

#### 1. `chat_completion`

Generate text completions using vLLM.

**Parameters:**
- `messages` (required): Array of message objects with `role` and `content`
  - `role`: "system", "user", or "assistant"
  - `content`: Message text
- `session_id` (optional): Session ID for conversation history
- `temperature` (optional): Sampling temperature (0.0-2.0)
- `max_tokens` (optional): Maximum tokens to generate
- `top_p` (optional): Nucleus sampling parameter (0.0-1.0)
- `top_k` (optional): Top-k sampling parameter
- `seed` (optional): Random seed for deterministic generation

**Example:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "chat_completion",
    "arguments": {
      "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing."}
      ],
      "temperature": 0.7,
      "max_tokens": 200,
      "session_id": "conv-123"
    }
  }
}
```

#### 2. `model_info`

Get information about the loaded model and server configuration.

**Parameters:** None

**Example:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "model_info",
    "arguments": {}
  }
}
```

**Response:**
```json
{
  "model_name": "facebook/opt-125m",
  "dtype": "float16",
  "max_model_len": 2048,
  "tensor_parallel_size": "1",
  "gpu_memory_utilization": "0.9",
  "server_state": "ready",
  "active_sessions": 3,
  "max_sessions": 100,
  "max_session_messages": 50,
  "default_temperature": 0.7,
  "default_max_tokens": 512
}
```

## Features

### 1. Session-Based Conversations

Use `session_id` to maintain conversation history across requests:

```bash
# First message
curl -X POST http://localhost:8099/vllm/mcp -d '{
  "method": "tools/call",
  "params": {
    "name": "chat_completion",
    "arguments": {
      "session_id": "user-123",
      "messages": [{"role": "user", "content": "My name is Alice"}]
    }
  }
}'

# Second message (remembers context)
curl -X POST http://localhost:8099/vllm/mcp -d '{
  "method": "tools/call",
  "params": {
    "name": "chat_completion",
    "arguments": {
      "session_id": "user-123",
      "messages": [{"role": "user", "content": "What is my name?"}]
    }
  }
}'
```

**Session Limits:**
- Maximum 100 concurrent sessions (configurable via `VLLM_MAX_SESSIONS`)
- Maximum 50 messages per session (configurable via `VLLM_MAX_SESSION_MESSAGES`)
- Oldest sessions removed when limit reached (FIFO)
- Conversations truncated to last N messages when message limit reached

### 2. Automatic Chat Template Detection

The server automatically detects if your model has a chat template and uses it:

- **Chat Models**: Uses `tokenizer.apply_chat_template()` for proper formatting
- **Base Models**: Falls back to naive concatenation

This works out-of-the-box with LLaMA, Mistral, Gemma, Phi-3, and other chat-tuned models.

### 3. Deterministic Generation

Use the `seed` parameter for reproducible outputs:

```json
{
  "messages": [{"role": "user", "content": "Tell me a joke"}],
  "seed": 42
}
```

Same seed + same input = same output (useful for testing).

### 4. Error Handling

The server provides detailed error messages:

- **CUDA OOM**: Actionable suggestions to reduce memory usage
- **Parse Errors**: Invalid JSON detection
- **Method Not Found**: Unknown MCP methods
- **vLLM Errors**: Detailed inference error messages

### 5. Graceful Shutdown

The server handles SIGTERM and SIGINT gracefully, logging shutdown and cleaning up resources.

## Troubleshooting

### CUDA Out of Memory

**Error:**
```
CUDA out of memory. Try: 1) Reduce VLLM_GPU_MEMORY_UTILIZATION (current: 0.9), ...
```

**Solutions:**
1. Reduce `VLLM_GPU_MEMORY_UTILIZATION` (try `0.7` or `0.5`)
2. Use smaller `max_tokens` in requests
3. Reduce `VLLM_MAX_MODEL_LEN` in config
4. Use a smaller model

### Model Loading Fails

**Error:**
```
Failed to initialize vLLM: <error details>
```

**Solutions:**
1. Check if you have a CUDA-capable GPU: `nvidia-smi`
2. Verify vLLM installation: `python -c "import vllm; print(vllm.__version__)"`
3. For gated models, set `HUGGING_FACE_HUB_TOKEN`
4. Check available GPU memory: `nvidia-smi`

### Slow Inference (CPU Mode)

vLLM is designed for GPU inference. CPU mode is extremely slow and may not work properly.

**Solution:** Use a GPU-enabled environment or switch to a CPU-optimized model.

### Server Not Responding

**Check logs:**
```bash
# Logs go to stderr when running via FluidMCP
# Check FluidMCP gateway logs for vLLM server output
```

**Common issues:**
1. Model still loading (can take 30s-10min depending on model size)
2. Long-running request blocking queue (sequential processing by design)
3. Server crashed (check logs for errors)

### Port Already in Use

If port 8099 is already in use:

```bash
# Find process using port
lsof -i :8099

# Kill process
kill -9 <PID>
```

## Architecture

### How It Works

```
FluidMCP Gateway
       ↓
subprocess.Popen(["python", "vllm_server.py"])
       ↓
   stdin/stdout JSON-RPC
       ↓
vLLM MCP Server (vllm_server.py)
       ↓
  vLLM Python API (LLM, SamplingParams)
       ↓
    GPU Inference
```

### Key Design Decisions

1. **Native MCP Protocol**: Uses stdin/stdout JSON-RPC (no HTTP layer in vLLM server)
2. **Direct vLLM Integration**: Runs vLLM Python API in-process
3. **Sequential Processing**: One request at a time for simplicity and safety
4. **In-Memory Sessions**: No persistence across server restarts

### Concurrency Behavior

The vLLM MCP server processes **one request at a time** (sequential processing).

**Implications:**
- Long-running requests block subsequent requests
- Multiple clients share the same request queue

**Workaround:** Run multiple vLLM server instances:
```json
{
  "mcpServers": {
    "vllm-1": {
      "command": "python",
      "args": ["vllm_server.py"],
      "env": {"VLLM_MODEL_NAME": "facebook/opt-125m"}
    },
    "vllm-2": {
      "command": "python",
      "args": ["vllm_server.py"],
      "env": {"VLLM_MODEL_NAME": "facebook/opt-125m"}
    }
  }
}
```

## Limitations (v1.0)

- ❌ **No Streaming**: stdin/stdout MCP cannot stream tokens
- ❌ **No Parallel Requests**: Sequential processing only
- ❌ **No Session Persistence**: Sessions cleared on server restart
- ❌ **Single Model**: One model per server instance

## Examples

### Basic Chat Completion

```bash
curl -X POST http://localhost:8099/vllm/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "chat_completion",
      "arguments": {
        "messages": [
          {"role": "user", "content": "What is Python?"}
        ],
        "max_tokens": 100
      }
    }
  }'
```

### Multi-turn Conversation

```bash
# First turn
curl -X POST http://localhost:8099/vllm/mcp -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "chat_completion",
    "arguments": {
      "session_id": "conv-001",
      "messages": [
        {"role": "user", "content": "I need help with Python decorators"}
      ],
      "max_tokens": 150
    }
  }
}'

# Second turn (remembers context)
curl -X POST http://localhost:8099/vllm/mcp -d '{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "chat_completion",
    "arguments": {
      "session_id": "conv-001",
      "messages": [
        {"role": "user", "content": "Can you show an example?"}
      ],
      "max_tokens": 200
    }
  }
}'
```

### System Prompt

```bash
curl -X POST http://localhost:8099/vllm/mcp -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "chat_completion",
    "arguments": {
      "messages": [
        {"role": "system", "content": "You are a helpful coding assistant. Always provide code examples."},
        {"role": "user", "content": "How do I sort a list in Python?"}
      ],
      "temperature": 0.3,
      "max_tokens": 200
    }
  }
}'
```

### Get Model Information

```bash
curl -X POST http://localhost:8099/vllm/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "model_info",
      "arguments": {}
    }
  }'
```

## Development

### Direct Testing (Without FluidMCP)

Test the MCP server directly via stdin/stdout:

```bash
# Test initialize
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python vllm_server.py

# Test tools/list
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python vllm_server.py

# Test chat completion
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"chat_completion","arguments":{"messages":[{"role":"user","content":"Hello"}],"max_tokens":50}}}' | python vllm_server.py
```

### Debugging

Enable DEBUG logging:
```json
{
  "env": {
    "VLLM_LOG_LEVEL": "DEBUG"
  }
}
```

Logs go to stderr (stdout is reserved for MCP protocol).

## Performance Tips

1. **Use GPU**: vLLM requires GPU for good performance
2. **Adjust Memory**: Tune `VLLM_GPU_MEMORY_UTILIZATION` based on model size
3. **Batch Size**: vLLM automatically batches concurrent requests (within single server instance)
4. **Model Choice**: Smaller models (1-7B) are faster and use less memory
5. **Context Length**: Reduce `VLLM_MAX_MODEL_LEN` if you don't need long contexts

## Contributing

Contributions are welcome! Please ensure:

1. Code follows existing style and conventions
2. All features are documented
3. Error messages are clear and actionable
4. Logging is appropriate (stderr only)

## License

[Your license here]

## Support

For issues and questions:
- GitHub Issues: [Your repo URL]
- Documentation: This README
- FluidMCP Docs: [FluidMCP documentation]
