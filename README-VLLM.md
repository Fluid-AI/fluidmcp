# vLLM Integration with FluidMCP

vLLM integration for FluidMCP using **OpenAI-compatible API endpoints**, not MCP JSON-RPC.

## ✨ Features

- **Streaming Support**: Real-time token generation using Server-Sent Events (SSE)
- **OpenAI-Compatible**: Drop-in replacement for OpenAI API
- **Multi-Model Support**: Run multiple LLM models simultaneously
- **Smart Port Detection**: Automatically infers endpoints from vLLM configuration
- **Process Management**: Automatic lifecycle management and health monitoring

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
curl -X POST http://localhost:8099/llm/v1/chat/completions \
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

### Multi-Model Configuration

**NEW**: Run multiple vLLM models simultaneously on the same FluidMCP instance.

```json
{
  "llmModels": {
    "vllm-opt": {
      "command": "vllm",
      "args": [
        "serve",
        "facebook/opt-125m",
        "--port", "8001",
        "--host", "0.0.0.0",
        "--tensor-parallel-size", "1",
        "--gpu-memory-utilization", "0.45",
        "--max-model-len", "2048",
        "--dtype", "float16"
      ],
      "env": {},
      "endpoints": {
        "base_url": "http://localhost:8001/v1"
      }
    },
    "vllm-gpt2": {
      "command": "vllm",
      "args": [
        "serve",
        "gpt2",
        "--port", "8002",
        "--host", "0.0.0.0",
        "--tensor-parallel-size", "1",
        "--gpu-memory-utilization", "0.45",
        "--max-model-len", "1024",
        "--dtype": "float16"
      ],
      "env": {},
      "endpoints": {
        "base_url": "http://localhost:8002/v1"
      }
    }
  }
}
```

**Key Points**:
- Each model runs on a separate port (8001, 8002, etc.)
- Adjust `--gpu-memory-utilization` so total doesn't exceed 1.0 (e.g., 0.45 + 0.45 = 0.9); exceeding 1.0 can lead to GPU out-of-memory errors
- Access via unified endpoint `/llm/v1/chat/completions` with model ID in request body
- Models run independently and can handle concurrent requests
- See `examples/vllm-multi-model-config.json` for complete example

**Usage**:
```bash
# Start multi-model setup
fluidmcp run examples/vllm-multi-model-config.json --file --start-server

# Query first model (specify model ID in request body)
curl -X POST http://localhost:8099/llm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "vllm-opt", "messages": [{"role": "user", "content": "Hello"}]}'

# Query second model (specify model ID in request body)
curl -X POST http://localhost:8099/llm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "vllm-gpt2", "messages": [{"role": "user", "content": "Hello"}]}'

# Check status of all models
curl http://localhost:8099/api/llm/status
```

---

## Advanced Configuration

**NEW in PR #4**: High-level configuration with validation, profiles, and production-safe defaults.

### High-Level Config Format

FluidMCP now supports a simplified, high-level configuration format that automatically generates vLLM CLI arguments and validates your configuration for common mistakes.

**Example**: [examples/vllm-advanced-config.json](examples/vllm-advanced-config.json)

**Note**: Replace `facebook/opt-125m` in examples below with your actual model name (e.g., `facebook/opt-125m`, `gpt2`, etc.).

```json
{
  "llmModels": {
    "vllm": {
      "model": "facebook/opt-125m",
      "port": 8001,
      "profile": "production",
      "config": {
        "gpu_memory_utilization": 0.9,
        "max_num_seqs": 64,
        "max_num_batched_tokens": 8192,
        "max_model_len": 4096,
        "dtype": "float16",
        "tensor_parallel_size": 1
      },
      "timeouts": {
        "startup": 300,
        "streaming": null,
        "non_streaming": 120
      },
      "env": {}
    }
  }
}
```

**Benefits**:
- ✅ Automatic validation before launch
- ✅ Clear error messages for invalid configs
- ✅ GPU memory validation across all models
- ✅ Port conflict detection
- ✅ Production-safe defaults via profiles
- ✅ Fully backward compatible with raw args format

### Configuration Profiles

Profiles provide production-tested defaults for common scenarios:

| Profile | Use Case | GPU Memory | Max Seqs | Batched Tokens | Model Len |
|---------|----------|------------|----------|----------------|-----------|
| **development** | Testing, small loads | 0.5 | 16 | 2048 | 2048 |
| **production** | Production workloads | 0.85 | 64 | 8192 | 4096 |
| **high-throughput** | Maximum concurrency | 0.88 | 128 | 16384 | 2048 |

**Usage**:
```json
{
  "llmModels": {
    "vllm": {
      "model": "facebook/opt-125m",
      "port": 8001,
      "profile": "production",
      "env": {}
    }
  }
}
```

All profile defaults can be overridden by specifying values in `"config"`.

**Example**: [examples/vllm-profile-development.json](examples/vllm-profile-development.json)

### GPU Memory Validation

FluidMCP automatically validates GPU memory allocation to prevent out-of-memory errors:

```json
{
  "llmModels": {
    "vllm-model-1": {
      "model": "facebook/opt-125m",
      "port": 8001,
      "config": {"gpu_memory_utilization": 0.45}
    },
    "vllm-model-2": {
      "model": "gpt2",
      "port": 8002,
      "config": {"gpu_memory_utilization": 0.45}
    }
  }
}
```

**Validation output**:
```
GPU Memory Allocation:
  - vllm-model-1: 0.45
  - vllm-model-2: 0.45
Total: 0.90 (OK)
```

**Validation Rules**:
- ❌ **FAIL**: Total GPU memory > 1.0
- ⚠️ **WARN**: Total GPU memory > 0.95 (close to limit)
- ✅ **PASS**: Total GPU memory ≤ 0.95

**Example**: [examples/vllm-multi-model-advanced.json](examples/vllm-multi-model-advanced.json)

### Timeout Configuration

Configure timeouts for different request types:

```json
{
  "timeouts": {
    "startup": 300,
    "streaming": null,
    "non_streaming": 120
  }
}
```

**Timeout Values**:
- `startup`: 300 - Seconds to wait for model loading
- `streaming`: null - Indefinite timeout (recommended for streaming)
- `non_streaming`: 120 - Seconds for non-streaming requests

**Important**:
- **Streaming requests** should use `null` (indefinite) because generation time is unpredictable
- **Non-streaming requests** can have bounded timeouts
- **Startup timeout** depends on model size (30s-10min)

### Config Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | HuggingFace model name or local path |
| `port` | integer | No | Port for vLLM server (default: 8001) |
| `profile` | string | No | Profile name (development/production/high-throughput) |
| `config` | object | No | vLLM configuration parameters |
| `config.gpu_memory_utilization` | float | No | GPU memory fraction (0.0-1.0) |
| `config.max_num_seqs` | integer | No | Max concurrent sequences |
| `config.max_num_batched_tokens` | integer | No | Max tokens in a batch |
| `config.max_model_len` | integer | No | Maximum context length |
| `config.dtype` | string | No | Data type (float16/bfloat16/float32/auto) |
| `config.tensor_parallel_size` | integer | No | Number of GPUs for tensor parallelism |
| `timeouts` | object | No | Timeout configuration |
| `env` | object | No | Environment variables |

### Validation Features

FluidMCP validates your configuration and provides clear error messages:

**Port Conflicts**:
```
❌ Port conflict: Models 'vllm-model-1' and 'vllm-model-2' both use port 8001
```

**GPU Memory Exceeded**:
```
❌ GPU memory allocation exceeds 1.0 (total: 1.20).
   This will cause out-of-memory errors.
   Breakdown: {'vllm-model-1': 0.6, 'vllm-model-2': 0.6}
```

**Invalid Values**:
```
❌ gpu_memory_utilization must be between 0.0 and 1.0, got 1.5
❌ dtype must be one of ['float16', 'bfloat16', 'float32', 'auto'], got 'invalid'
```

**Risky Configurations** (warnings):
```
⚠️ GPU memory allocation is 0.98 (very close to 1.0).
   Consider reducing to avoid potential OOM errors.
⚠️ max_model_len is very high (65536).
   This may cause memory issues or slow performance.
```

### Backward Compatibility

The old raw args format continues to work without changes:

```json
{
  "llmModels": {
    "vllm": {
      "command": "vllm",
      "args": [
        "serve",
        "facebook/opt-125m",
        "--port", "8001",
        "--gpu-memory-utilization", "0.9"
      ],
      "env": {},
      "endpoints": {"base_url": "http://localhost:8001/v1"}
    }
  }
}
```

**Note**: High-level config is optional and additive. Existing configs require no changes.

---

## API Reference

### OpenAI-Compatible Endpoints

FluidMCP proxies requests to vLLM's native OpenAI server:

#### `POST /llm/v1/chat/completions`

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

#### `POST /llm/v1/completions`

**Request**:
```json
{
  "model": "facebook/opt-125m",
  "prompt": "Once upon a time",
  "max_tokens": 100,
  "temperature": 0.8
}
```

#### `GET /llm/v1/models`

List all available models or get details for a specific model using `?model={model_id}` query parameter.

---

## Examples

### Basic Chat Completion

```bash
curl -X POST http://localhost:8099/llm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "facebook/opt-125m",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### With System Prompt

```bash
curl -X POST http://localhost:8099/llm/v1/chat/completions \
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

### Streaming Chat Completion

**NEW**: Real-time token streaming using Server-Sent Events (SSE):

```bash
curl -X POST http://localhost:8099/llm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "facebook/opt-125m",
    "messages": [{"role": "user", "content": "Write a short poem about AI"}],
    "stream": true,
    "max_tokens": 100
  }'
```

**Response** (Server-Sent Events):
```
data: {"id":"cmpl-...","object":"chat.completion.chunk","created":1234567890,"model":"facebook/opt-125m","choices":[{"index":0,"delta":{"role":"assistant","content":"In"},"finish_reason":null}]}

data: {"id":"cmpl-...","object":"chat.completion.chunk","created":1234567890,"model":"facebook/opt-125m","choices":[{"index":0,"delta":{"content":" silicon"},"finish_reason":null}]}

data: {"id":"cmpl-...","object":"chat.completion.chunk","created":1234567890,"model":"facebook/opt-125m","choices":[{"index":0,"delta":{"content":" dreams"},"finish_reason":null}]}

...

data: [DONE]
```

### Using OpenAI Python SDK

```python
from openai import OpenAI

# Point to FluidMCP gateway
client = OpenAI(
    base_url="http://localhost:8099/llm/v1",
    api_key="dummy"  # Not used, but required by SDK
)

# Non-streaming request
response = client.chat.completions.create(
    model="facebook/opt-125m",
    messages=[
        {"role": "user", "content": "What is Python?"}
    ],
    max_tokens=100
)
print(response.choices[0].message.content)

# Streaming request
stream = client.chat.completions.create(
    model="facebook/opt-125m",
    messages=[
        {"role": "user", "content": "Write a short story about robots"}
    ],
    stream=True,
    max_tokens=200
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

---

## Architecture

### How It Works

```
Client Request (OpenAI format)
    ↓
FluidMCP Gateway (port 8099)
    ↓
POST /llm/v1/chat/completions (with model="vllm" in body)
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
4. Check FluidMCP logs for vLLM launch errors. Note: vLLM stderr/stdout are not captured by FluidMCP. To debug vLLM startup issues, run `vllm serve ...` manually in a separate terminal

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

## Environment Variables

### LLM_STREAMING_TIMEOUT

Controls the timeout for streaming requests.

```bash
# Set timeout in seconds (e.g., 5 minutes)
export LLM_STREAMING_TIMEOUT=300

# Or use indefinite timeout (default)
export LLM_STREAMING_TIMEOUT=0
# or omit the variable entirely
```

**Default**: Indefinite timeout (when variable is not set or set to 0)

**Behavior**:
- Positive number (> 0): Timeout in seconds
- Zero or negative (≤ 0): Indefinite timeout (allows variable generation times)
- Invalid value: Indefinite timeout (warning logged)

**Note**: LLM token generation times are highly variable. For most use cases, the default indefinite timeout is recommended. Only set a timeout if you need to enforce maximum response times.

**Important for Production**: When using reverse proxies (nginx, HAProxy, load balancers), you must configure their timeout settings separately:
- **nginx**: `proxy_read_timeout 600s;` (or higher)
- **HAProxy**: `timeout server 600s` (or higher)
- **AWS ELB/ALB**: Set idle timeout to match your expected generation time

The `LLM_STREAMING_TIMEOUT` only controls FluidMCP's connection to the vLLM backend, not client-to-proxy timeouts.

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
POST /llm/v1/chat/completions
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
