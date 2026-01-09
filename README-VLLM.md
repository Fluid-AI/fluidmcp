# vLLM MCP Server

A native MCP (Model Context Protocol) server that exposes vLLM's high-performance LLM inference capabilities through stdin/stdout JSON-RPC protocol.

## Overview

The vLLM MCP server runs vLLM directly in-process and communicates via the MCP protocol, allowing FluidMCP to orchestrate LLM inference alongside other MCP tools.

**This is a minimal initial implementation (PR #1)** focused on core functionality. Additional features like session management, chat templates, and advanced error handling will be added in subsequent PRs.

## Quick Start

### Prerequisites

- Python 3.8 or higher (vLLM supports Python 3.8-3.11)
- CUDA-capable GPU (optional but strongly recommended)
- vLLM package installed: `pip install vllm>=0.6.0`

### Installation

```bash
pip install vllm>=0.6.0
```

For gated models (Llama, Mistral, etc.), set your Hugging Face token:
```bash
export HUGGING_FACE_HUB_TOKEN="your_token_here"
```

### Running with FluidMCP

```bash
fluidmcp run examples/vllm-config.json --file --start-server
```

The server will start on `http://localhost:8099`. Access the Swagger UI at `http://localhost:8099/docs`.

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

Configuration is done via environment variables in the config file.

### Model Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `VLLM_MODEL_NAME` | Hugging Face model name | `facebook/opt-125m` |
| `VLLM_TENSOR_PARALLEL_SIZE` | Number of GPUs for tensor parallelism | `1` |
| `VLLM_GPU_MEMORY_UTILIZATION` | GPU memory ratio (0.0-1.0) | `0.9` |
| `VLLM_MAX_MODEL_LEN` | Maximum context length | Model's default |
| `VLLM_DTYPE` | Data type: float16, bfloat16, float32 | `float16` |

### Logging

| Variable | Description | Default |
|----------|-------------|---------|
| `VLLM_LOG_LEVEL` | Log level: DEBUG, INFO, WARNING, ERROR | `INFO` |

## API Reference

### MCP Tools

#### `chat_completion`

Generate text completions using vLLM.

**Parameters:**
- `messages` (required): Array of message objects with `role` and `content`
  - `role`: "system", "user", or "assistant"
  - `content`: Message text (stripped of leading/trailing whitespace, must be non-empty)
- `temperature` (optional): Sampling temperature (0.0 < temperature ≤ 2.0), default: 0.7. Must be greater than 0.0 to avoid division by zero in sampling.
- `max_tokens` (optional): Maximum tokens to generate, default: 512
- `top_p` (optional): Nucleus sampling parameter (0.0-1.0), default: 1.0

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
        {"role": "user", "content": "Explain quantum computing in simple terms"}
      ],
      "temperature": 0.7,
      "max_tokens": 200
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Quantum computing is..."
      }
    ]
  }
}
```

## Prompt Formatting

**Current implementation uses naive concatenation:**
```
role: content
role: content
```

This works for base models like OPT and GPT-2. For chat-tuned models (Llama, Mistral, etc.), automatic chat template detection will be added in a future PR.

**Security Note**: The naive concatenation approach does NOT prevent prompt injection attacks. If you're exposing this server to untrusted user input in production, implement proper input validation and consider using model-specific chat templates via `tokenizer.apply_chat_template()`.

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

### With System Prompt

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
          {"role": "system", "content": "You are a helpful coding assistant."},
          {"role": "user", "content": "How do I sort a list in Python?"}
        ],
        "temperature": 0.3,
        "max_tokens": 200
      }
    }
  }'
```

### Custom Sampling Parameters

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
          {"role": "user", "content": "Write a creative story"}
        ],
        "temperature": 0.9,
        "top_p": 0.95,
        "max_tokens": 300
      }
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
3. **Sequential Processing**: One request at a time for simplicity
4. **Minimal Core**: Focus on getting basic functionality working first

## Troubleshooting

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

**Solution:** Use a GPU-enabled environment.

### Server Not Responding

**Check logs:**
```bash
# Logs go to stderr when running via FluidMCP
# Check FluidMCP gateway logs for vLLM server output
```

**Common issues:**
1. **Model still loading** - Large models can take 30s-10min to initialize depending on model size and hardware. Look for "Ready to accept MCP requests" in logs to confirm startup is complete.
2. **Long-running request blocking queue** - Sequential processing means one slow request blocks all others.
3. **Server crashed** - Check logs for errors during initialization or request processing.

**Note on Startup**: vLLM initialization is synchronous and blocking. There is no explicit health check endpoint. Monitor stderr logs for "Ready to accept MCP requests" to confirm the server is fully initialized.

## Current Limitations

**This is v1.0 (PR #1) - minimal core functionality:**

- ❌ **No Sessions**: Each request is independent, no conversation history
- ❌ **No Chat Templates**: Uses naive prompt concatenation (works for base models only)
- ❌ **No Advanced Error Handling**: Basic error messages only
- ❌ **No Parallel Requests**: Sequential processing only
- ❌ **No Model Introspection**: No model_info tool yet

## Planned Features (Future PRs)

- **PR #2**: Automatic chat template detection for chat-tuned models
- **PR #3**: Session management with conversation history
- **PR #4**: Advanced features (warm-up, model_info tool, CUDA OOM detection, graceful shutdown)
- **PR #5**: Documentation and examples

## Performance Tips

1. **Use GPU**: vLLM requires GPU for good performance
2. **Adjust Memory**: Tune `VLLM_GPU_MEMORY_UTILIZATION` based on model size
3. **Model Choice**: Smaller models (125M-1.3B) are faster for testing
4. **Context Length**: Reduce `VLLM_MAX_MODEL_LEN` if you don't need long contexts

## Contributing

Contributions are welcome! This is a minimal initial implementation - see "Planned Features" section for what's coming next.

## License

This project is licensed under the same terms as FluidMCP. See the LICENSE file in the repository root.

## Support

For issues and questions:
- GitHub Issues: Please open an issue in the FluidMCP repository
- Documentation: This README
- FluidMCP Docs: See the main FluidMCP documentation
