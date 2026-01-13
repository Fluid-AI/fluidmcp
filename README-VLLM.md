# vLLM Integration with FluidMCP

vLLM integration for FluidMCP using **OpenAI-compatible API endpoints**, not MCP JSON-RPC.

---

## ⚠️ Architecture Change

**Previous approach** (Deprecated): Custom MCP wrapper with JSON-RPC
**Current approach** (Recommended): Native vLLM OpenAI server with HTTP proxy

---

## Quick Start

### Prerequisites

- Python 3.9+ (vLLM supports Python 3.9-3.12)
- CUDA-capable GPU (strongly recommended)
- vLLM installed: `pip install vllm>=0.6.0`

### Installation

```bash
pip install vllm>=0.6.0
```

For gated models (Llama, Mistral, etc.):
```bash
export HUGGING_FACE_HUB_TOKEN="your_token_here"
```

### Running with FluidMCP

```bash
fluidmcp run examples/vllm-config.json --file --start-server
```

### Testing

**OpenAI-compatible endpoint**:
```bash
curl -X POST http://localhost:8099/vllm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "facebook/opt-125m",
    "messages": [
      {"role": "user", "content": "What is machine learning?"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

---

## Configuration

### New Structure (`llmModels` section)

```json
{
  "llmModels": {
    "vllm": {
      "command": "vllm",
      "args": [
        "serve",
        "facebook/opt-125m",
        "--port", "8001",
        "--host", "0.0.0.0",
        "--tensor-parallel-size", "1",
        "--gpu-memory-utilization", "0.9",
        "--max-model-len", "2048",
        "--dtype", "float16"
      ],
      "env": {},
      "endpoints": {
        "base_url": "http://localhost:8001/v1"
      }
    }
  }
}
```

### vLLM CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--port` | Port for vLLM server | `8001` |
| `--host` | Host to bind to | `0.0.0.0` |
| `--tensor-parallel-size` | Number of GPUs | `1` |
| `--gpu-memory-utilization` | GPU memory ratio (0.0-1.0) | `0.9` |
| `--max-model-len` | Maximum context length | Model default |
| `--dtype` | Data type: float16, bfloat16, float32 | `float16` |

---

## API Reference

### OpenAI-Compatible Endpoints

FluidMCP proxies requests to vLLM's native OpenAI server:

#### `POST /{model_id}/v1/chat/completions`

**Request**:
```json
{
  "model": "facebook/opt-125m",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Explain quantum computing"}
  ],
  "temperature": 0.7,
  "max_tokens": 200,
  "top_p": 1.0
}
```

**Response**:
```json
{
  "id": "cmpl-...",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "facebook/opt-125m",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Quantum computing is..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 50,
    "total_tokens": 70
  }
}
```

#### `POST /{model_id}/v1/completions`

**Request**:
```json
{
  "model": "facebook/opt-125m",
  "prompt": "Once upon a time",
  "max_tokens": 100,
  "temperature": 0.8
}
```

#### `GET /{model_id}/v1/models`

List available models from vLLM server.

---

## Examples

### Basic Chat Completion

```bash
curl -X POST http://localhost:8099/vllm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "facebook/opt-125m",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### With System Prompt

```bash
curl -X POST http://localhost:8099/vllm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "facebook/opt-125m",
    "messages": [
      {"role": "system", "content": "You are a coding assistant."},
      {"role": "user", "content": "How do I sort a list in Python?"}
    ],
    "temperature": 0.3,
    "max_tokens": 200
  }'
```

### Using OpenAI Python SDK

```python
from openai import OpenAI

# Point to FluidMCP gateway
client = OpenAI(
    base_url="http://localhost:8099/vllm/v1",
    api_key="dummy"  # Not used, but required by SDK
)

response = client.chat.completions.create(
    model="facebook/opt-125m",
    messages=[
        {"role": "user", "content": "What is Python?"}
    ],
    max_tokens=100
)

print(response.choices[0].message.content)
```

---

## Architecture

### How It Works

```
Client Request (OpenAI format)
    ↓
FluidMCP Gateway (port 8099)
    ↓
POST /vllm/v1/chat/completions
    ↓
HTTP Proxy (httpx)
    ↓
vLLM Native Server (port 8001)
    ↓
/v1/chat/completions
    ↓
Response (OpenAI format)
```

### Key Design Decisions

1. **OpenAI Protocol**: Uses industry-standard OpenAI API, not custom JSON-RPC
2. **Native vLLM Server**: Runs `vllm serve` command, no custom wrapper
3. **HTTP Proxy**: Simple httpx forwarding, ~70 lines of code
4. **Separate Section**: `llmModels` vs `mcpServers` for semantic clarity

---

## Why This Approach?

### ✅ Benefits

| Feature | Old (MCP wrapper) | New (OpenAI proxy) |
|---------|-------------------|-------------------|
| **Protocol** | Custom JSON-RPC | OpenAI standard |
| **Streaming** | ❌ No | ✅ Yes (native SSE) |
| **SDK Support** | ❌ None | ✅ All OpenAI SDKs |
| **Glue Code** | 400 lines | 70 lines |
| **Maintenance** | Custom protocol | Zero (uses vLLM native) |
| **Ecosystem** | Isolated | LangChain, LiteLLM, etc. |

### 🎯 Alignment with Industry

- **OpenAI SDK**: Works out of box
- **LangChain**: Full compatibility
- **LiteLLM**: Unified interface
- **Any tool expecting OpenAI API**: Just works

---

## Troubleshooting

### Model Loading Fails

**Error**: `Failed to start LLM model 'vllm'`

**Solutions**:
1. Check GPU availability: `nvidia-smi`
2. Verify vLLM installation: `python -c "import vllm; print(vllm.__version__)"`
3. For gated models, set `HUGGING_FACE_HUB_TOKEN`
4. Check vLLM logs in stderr

### Server Not Responding

**Issue**: Requests timeout or return 502

**Solutions**:
1. Wait for model loading (30s-10min depending on model size)
2. Check vLLM process is running: `ps aux | grep vllm`
3. Verify port 8001 is not blocked: `curl http://localhost:8001/v1/models`
4. Check FluidMCP logs for proxy errors

### CPU Mode Performance

vLLM is designed for GPUs. CPU mode is extremely slow.

**Solution**: Use a GPU-enabled environment or consider Ollama for CPU inference.

---

## Performance Tips

1. **Use GPU**: vLLM requires GPU for production performance
2. **Adjust Memory**: Tune `--gpu-memory-utilization` (0.7-0.95)
3. **Model Size**: Smaller models (125M-1.3B) faster for testing
4. **Context Length**: Reduce `--max-model-len` if you don't need long contexts
5. **Batch Size**: vLLM automatically batches concurrent requests

---

## Migration from Old Approach

### Old Config (Deprecated)

```json
{
  "mcpServers": {
    "vllm": {
      "command": "python",
      "args": ["vllm_server.py"],
      "env": {
        "VLLM_MODEL_NAME": "facebook/opt-125m"
      }
    }
  }
}
```

### New Config (Current)

```json
{
  "llmModels": {
    "vllm": {
      "command": "vllm",
      "args": ["serve", "facebook/opt-125m", "--port", "8001"],
      "env": {},
      "endpoints": {
        "base_url": "http://localhost:8001/v1"
      }
    }
  }
}
```

### API Change

**Old** (JSON-RPC):
```bash
POST /vllm/mcp
{"jsonrpc": "2.0", "method": "tools/call", "params": {...}}
```

**New** (OpenAI):
```bash
POST /vllm/v1/chat/completions
{"model": "...", "messages": [...]}
```

---

## Contributing

This is the recommended architecture for LLM integration in FluidMCP. Future LLM integrations (Ollama, LM Studio, etc.) should follow this same pattern.

---

## Support

- **GitHub Issues**: https://github.com/fluidai/fluidmcp/issues
- **Documentation**: This README
- **vLLM Docs**: https://docs.vllm.ai
