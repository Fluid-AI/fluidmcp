# Replicate Model Support in FluidMCP

FluidMCP supports running AI models via **Replicate's cloud API**, enabling inference without local GPU requirements or model management.

## Overview

**What is Replicate?**
- Cloud platform for running machine learning models via API
- No local compute or GPU required
- Pay-per-use pricing (charged by Replicate)
- Thousands of pre-trained models available

**What FluidMCP Provides:**
- HTTP client for Replicate API
- Automatic retry logic and error handling
- Health monitoring
- Streaming support
- Model lifecycle management

## Key Features

✅ **Inference-only** - No local model deployment
✅ **No GPU required** - All computation runs on Replicate's infrastructure
✅ **Simple setup** - Just API key needed
✅ **Wide model selection** - Access to Meta Llama, Mistral, CodeLlama, Stable Diffusion, and thousands more
✅ **Automatic retries** - Built-in error recovery
✅ **Streaming support** - Real-time output generation

## Quick Start

### 1. Get Replicate API Token

```bash
# Sign up at https://replicate.com
# Get your API token from https://replicate.com/account/api-tokens
export REPLICATE_API_TOKEN="r8_..."
```

### 2. Create Configuration

Create `replicate-config.json`:

```json
{
  "mcpServers": {},
  "llmModels": {
    "llama-2-70b": {
      "type": "replicate",
      "model": "meta/llama-2-70b-chat",
      "api_key": "${REPLICATE_API_TOKEN}",
      "default_params": {
        "temperature": 0.7,
        "max_tokens": 1000
      }
    }
  }
}
```

### 3. Run FluidMCP

```bash
fluidmcp run replicate-config.json --file --start-server
```

### 4. Use the Model

Replicate-backed models are exposed through FluidMCP's **unified, OpenAI-compatible LLM API**, which is the recommended integration path:

```bash
# Create a chat completion using the unified LLM endpoint
curl -X POST http://localhost:8099/api/llm/llama-2-70b/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-2-70b",
    "messages": [
      {
        "role": "user",
        "content": "Explain quantum computing in simple terms"
      }
    ],
    "temperature": 0.7,
    "max_tokens": 1000
  }'

```

**Streaming Support**: Replicate models do not currently support streaming (`"stream": true`) due to Replicate's polling-based API architecture. Streaming requests will return a 501 error. For real-time output requirements, consider using vLLM or other providers that support native streaming. See [Limitations](#limitations) for details.

**Note**: Legacy Replicate-specific endpoints (`/api/replicate/models/...`) are deprecated and should not be used for new integrations. Use the unified `/api/llm/{model_id}/v1/...` routes shown above.

## Configuration Format

### Complete Example

```json
{
  "mcpServers": {},
  "llmModels": {
    "model-id": {
      "type": "replicate",
      "model": "owner/model-name",
      "api_key": "${REPLICATE_API_TOKEN}",
      "endpoints": {
        "base_url": "https://api.replicate.com/v1"
      },
      "default_params": {
        "temperature": 0.7,
        "max_tokens": 1000,
        "top_p": 0.9,
        "top_k": 50
      },
      "timeout": 120,
      "max_retries": 3
    }
  }
}
```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `model` | ✅ Yes | - | Replicate model identifier (format: `owner/model-name`) |
| `api_key` | ✅ Yes | - | Replicate API token (use `${ENV_VAR}` for environment variables) |
| `endpoints.base_url` | ❌ No | `https://api.replicate.com/v1` | API base URL (usually default is fine) |
| `default_params` | ❌ No | `{}` | Default parameters merged with each prediction request |
| `timeout` | ❌ No | `60.0` | HTTP request timeout in seconds |
| `max_retries` | ❌ No | `3` | Maximum retry attempts for failed requests |

### Model Identifier Format

Replicate models use the format: `owner/model-name`

Examples:
- `meta/llama-2-70b-chat` - Meta's Llama 2 70B chat model
- `mistralai/mistral-7b-instruct-v0.2` - Mistral 7B instruct
- `meta/codellama-34b-instruct` - Meta's CodeLlama 34B
- `stability-ai/sdxl` - Stable Diffusion XL

Find models at: https://replicate.com/explore

## Common Use Cases

### Text Generation (Chat Models)

```json
{
  "mcpServers": {},
  "llmModels": {
    "llama-chat": {
      "type": "replicate",
      "model": "meta/llama-2-70b-chat",
      "api_key": "${REPLICATE_API_TOKEN}",
      "default_params": {
        "temperature": 0.7,
        "max_tokens": 1000,
        "system_prompt": "You are a helpful AI assistant."
      }
    }
  }
}
```

Usage:
```bash
curl -X POST http://localhost:8099/api/llm/llama-chat/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-chat",
    "messages": [
      {
        "role": "user",
        "content": "What is the capital of France?"
      }
    ]
  }'
```

### Code Generation

```json
{
  "mcpServers": {},
  "llmModels": {
    "codellama": {
      "type": "replicate",
      "model": "meta/codellama-34b-instruct",
      "api_key": "${REPLICATE_API_TOKEN}",
      "default_params": {
        "temperature": 0.2,
        "max_tokens": 2000
      }
    }
  }
}
```

Usage:
```bash
curl -X POST http://localhost:8099/api/llm/codellama/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "codellama",
    "messages": [
      {
        "role": "user",
        "content": "Write a Python function to calculate fibonacci numbers"
      }
    ]
  }'
```

### Multiple Models

You can run multiple Replicate models simultaneously:

```json
{
  "mcpServers": {},
  "llmModels": {
    "llama-70b": {
      "type": "replicate",
      "model": "meta/llama-2-70b-chat",
      "api_key": "${REPLICATE_API_TOKEN}",
      "default_params": {"temperature": 0.7}
    },
    "mistral-7b": {
      "type": "replicate",
      "model": "mistralai/mistral-7b-instruct-v0.2",
      "api_key": "${REPLICATE_API_TOKEN}",
      "default_params": {"temperature": 0.5}
    },
    "codellama": {
      "type": "replicate",
      "model": "meta/codellama-34b-instruct",
      "api_key": "${REPLICATE_API_TOKEN}",
      "default_params": {"temperature": 0.2}
    }
  }
}
```

Each model is accessible independently via its model ID.

## API Endpoints

Replicate models are exposed through **FluidMCP's unified OpenAI-compatible API**. This allows seamless integration with OpenAI client libraries and tools.

### Chat Completions (Primary Endpoint)
```
POST /api/llm/{model_id}/v1/chat/completions
```

**OpenAI-compatible request format:**
```json
{
  "model": "llama-2-70b",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "What is quantum computing?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

**Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "llama-2-70b",
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
    "completion_tokens": 100,
    "total_tokens": 120
  }
}
```

### Streaming Responses
Set `"stream": true` in the request:

```bash
curl -N -X POST http://localhost:8099/api/llm/llama-2-70b/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-2-70b",
    "messages": [{"role": "user", "content": "Tell me a story"}],
    "stream": true
  }'
```

**Note**: Replicate doesn't support true streaming yet. FluidMCP polls the prediction and returns the complete response when ready.

### Using with OpenAI Python Client

```python
from openai import OpenAI

# Point OpenAI client to FluidMCP gateway
client = OpenAI(
    base_url="http://localhost:8099/api/llm/llama-2-70b/v1",
    api_key="not-needed"  # FluidMCP uses REPLICATE_API_TOKEN from config
)

response = client.chat.completions.create(
    model="llama-2-70b",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

### Model Discovery

List all available models (including Replicate):
```bash
curl http://localhost:8099/api/models
```

### Health Check
```bash
curl http://localhost:8099/health
```

## Error Handling

FluidMCP provides automatic error handling for Replicate API calls:

### Automatic Retries

Failed requests are automatically retried with exponential backoff:

```json
{
  "mcpServers": {},
  "llmModels": {
    "model-id": {
      "type": "replicate",
      "model": "meta/llama-2-70b-chat",
      "api_key": "${REPLICATE_API_TOKEN}",
      "max_retries": 5,
      "timeout": 120
    }
  }
}
```

Retry schedule:
- 1st retry: immediately
- 2nd retry: after 2 seconds
- 3rd retry: after 4 seconds
- 4th retry: after 8 seconds
- 5th retry: after 16 seconds

### Common Errors

**Authentication Error (401)**:
```json
{
  "error": "Invalid API token"
}
```
Solution: Check your `REPLICATE_API_TOKEN` is correct.

**Rate Limit (429)**:
```json
{
  "error": "Rate limit exceeded"
}
```
Solution: Wait before retrying, or upgrade Replicate plan.

**Model Not Found (404)**:
```json
{
  "error": "Model not found"
}
```
Solution: Verify model identifier format is `owner/model-name`.

**Timeout**:
```json
{
  "error": "Request timeout"
}
```
Solution: Increase `timeout` value in configuration.

## Cost Management

Replicate charges based on compute time. Tips to manage costs:

1. **Use smaller models** for simple tasks:
   - `mistralai/mistral-7b` instead of `llama-2-70b`
   - Significantly cheaper, often sufficient

2. **Set reasonable `max_tokens`**:
   ```json
   {
     "default_params": {
       "max_tokens": 500
     }
   }
   ```

3. **Use caching** where possible:
   - Cache frequently requested outputs
   - Implement request deduplication

4. **Monitor usage**:
   ```bash
   # Check your Replicate dashboard
   # https://replicate.com/account/billing
   ```

5. **Use shorter timeouts** in your config to fail fast:
   ```json
   {
     "llmModels": {
       "llama-2-70b": {
         "type": "replicate",
         "timeout": 60,
         "max_retries": 2
       }
     }
   }
   ```

## Security Best Practices

### API Key Storage

**❌ Don't:**
```json
{
  "api_key": "r8_hardcoded_token_here"
}
```

**✅ Do:**
```json
{
  "api_key": "${REPLICATE_API_TOKEN}"
}
```

Store tokens in environment variables or secrets management.

### Network Security

**Recommendation**: Run FluidMCP behind a reverse proxy with authentication:

```nginx
location /api/llm {
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://localhost:8099;
}
```

### Rate Limiting

Implement rate limiting to prevent abuse:

```python
# Example with FastAPI middleware
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/llm/{model_id}/v1/chat/completions")
@limiter.limit("10/minute")
async def unified_chat_completions(...):
    ...
```

## Testing

FluidMCP includes comprehensive tests for Replicate functionality:

```bash
# Run Replicate client tests
pytest tests/test_replicate_client.py -v

# Run with coverage
pytest tests/test_replicate_client.py --cov=fluidmcp.cli.services.replicate_client
```

**Test Coverage**: 22 tests covering:
- Client initialization
- Prediction creation and retrieval
- Streaming
- Error handling and retries
- Health checks
- Model management

All tests use mocked HTTP responses (no actual Replicate API calls).

## Limitations

### Streaming Not Supported

Replicate models do not currently support streaming responses (`"stream": true` in requests). This is due to Replicate's polling-based API architecture:

- **Why**: Replicate predictions are asynchronous jobs that must be polled for completion
- **Alternative**: Use vLLM, Ollama, or other providers for real-time streaming requirements
- **Behavior**: Requests with `"stream": true` return HTTP 501 (Not Implemented)

### Polling-Based Architecture

Unlike vLLM which provides instant responses, Replicate uses a prediction-polling model:

- Predictions are created as async jobs
- FluidMCP polls every 1-5 seconds for completion
- This adds latency compared to synchronous inference
- Best suited for non-interactive use cases

### Rate Limiting

- Replicate enforces API rate limits at the account level
- No client-side throttling is currently implemented
- High-volume usage may hit 429 (Too Many Requests) errors
- Consider implementing request queuing for production use

## Comparison: Replicate vs vLLM

| Feature | Replicate | vLLM |
|---------|-----------|------|
| **Deployment** | Cloud (Replicate) | Local (your hardware) |
| **GPU Required** | ❌ No | ✅ Yes |
| **Setup Complexity** | Low (API key only) | High (GPU, drivers, models) |
| **Cost** | Pay-per-use | Hardware + electricity |
| **Model Selection** | Thousands available | Must download/host |
| **Latency** | Higher (network) | Lower (local) |
| **Privacy** | Data sent to Replicate | Data stays local |
| **Scalability** | Automatic | Limited by hardware |
| **Best For** | Prototyping, low volume | Production, high volume, privacy |

**When to use Replicate:**
- Prototyping and development
- Low to moderate inference volume
- No GPU hardware available
- Quick experimentation with different models
- Cost-effective for low usage

**When to use vLLM:**
- Production deployments
- High inference volume
- Data privacy requirements
- Need for customization
- Have GPU infrastructure

## Troubleshooting

### Model initialization fails

**Symptom**: "Health check failed for Replicate model"

**Solutions:**
1. Check API token is valid:
   ```bash
   echo $REPLICATE_API_TOKEN
   ```

2. Verify model exists:
   ```bash
   curl https://api.replicate.com/v1/models/meta/llama-2-70b-chat \
     -H "Authorization: Token $REPLICATE_API_TOKEN"
   ```

3. Check network connectivity:
   ```bash
   curl https://api.replicate.com/v1/models
   ```

### Predictions timeout

**Symptom**: "Request timeout"

**Solutions:**
1. Increase timeout:
   ```json
   {
     "timeout": 300
   }
   ```

2. Increase timeout in config:
   ```json
   {
     "llmModels": {
       "llama-2-70b": {
         "type": "replicate",
         "timeout": 300
       }
     }
   }
   ```

3. Check Replicate status:
   - https://replicate.com/status

### Requests fail

**Symptom**: Chat completion requests fail with errors

**Solutions:**
1. Check FluidMCP logs:
   ```bash
   tail -f ~/.fluidmcp/logs/fluidmcp.log
   ```

2. Verify input format matches model requirements:
   - Check model page on Replicate.com
   - Look at "API" tab for input schema

3. Try with simpler input:
   ```json
   {
     "input": {
       "prompt": "Hello"
     }
   }
   ```

### High costs

**Symptom**: Unexpected Replicate bills

**Solutions:**
1. Check usage dashboard:
   - https://replicate.com/account/billing

2. Reduce `max_tokens`:
   ```json
   {
     "default_params": {
       "max_tokens": 100
     }
   }
   ```

3. Use smaller models:
   - `mistral-7b` instead of `llama-2-70b`

4. Implement caching:
   - Cache frequent queries
   - Deduplicate requests

## Examples

See [examples/replicate-inference.json](../examples/replicate-inference.json) for complete working examples.

### Running the Examples

```bash
# Set your API token
export REPLICATE_API_TOKEN="r8_..."

# Run the example config
fluidmcp run examples/replicate-inference.json --file --start-server

# Server runs on http://localhost:8099
# Test with:
curl -X POST http://localhost:8099/api/llm/llama-2-70b/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-2-70b",
    "messages": [
      {
        "role": "user",
        "content": "What is the meaning of life?"
      }
    ]
  }'
```

## Additional Resources

- **Replicate Documentation**: https://replicate.com/docs
- **Available Models**: https://replicate.com/explore
- **API Reference**: https://replicate.com/docs/reference/http
- **Pricing**: https://replicate.com/pricing
- **Status Page**: https://replicate.com/status

## Support

For issues specific to FluidMCP's Replicate integration:
- GitHub Issues: https://github.com/Fluid-AI/fluidmcp/issues
- Include logs from `~/.fluidmcp/logs/` directory
- Mention FluidMCP version: `fluidmcp --version`

For Replicate platform issues:
- Replicate Support: support@replicate.com
- Discord: https://discord.gg/replicate
