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

# Stream chat completions (use -N flag for curl to disable buffering)
curl -N -X POST http://localhost:8099/api/llm/llama-2-70b/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-2-70b",
    "messages": [
      {
        "role": "user",
        "content": "Write a haiku about coding"
      }
    ],
    "stream": true
  }'
```

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
curl -X POST http://localhost:8099/api/replicate/models/llama-chat/predict \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "prompt": "What is the capital of France?"
    }
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
curl -X POST http://localhost:8099/api/replicate/models/codellama/predict \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "prompt": "Write a Python function to calculate fibonacci numbers"
    }
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

FluidMCP exposes the following endpoints for Replicate models:

### List Models
```
GET /api/replicate/models
```

Returns list of active Replicate model IDs.

### Create Prediction
```
POST /api/replicate/models/{model_id}/predict
```

Body:
```json
{
  "input": {
    "prompt": "Your prompt here",
    "temperature": 0.7
  },
  "version": "optional-specific-version",
  "webhook": "optional-webhook-url"
}
```

Returns:
```json
{
  "id": "pred_abc123",
  "status": "starting",
  "input": {...}
}
```

### Get Prediction Status
```
GET /api/replicate/models/{model_id}/predictions/{prediction_id}
```

**Parameters:**
- `model_id`: The model identifier that created the prediction (e.g., `llama-2-70b`)
- `prediction_id`: The prediction ID returned from the create prediction call

**Returns:**
```json
{
  "id": "pred_abc123",
  "status": "succeeded",
  "output": "Model output here...",
  "metrics": {
    "predict_time": 1.23
  }
}
```

### Stream Prediction
```
POST /api/replicate/models/{model_id}/stream
```

Body:
```json
{
  "input": {
    "prompt": "Your prompt here"
  }
}
```

Returns server-sent events (SSE) stream of output chunks.

### Cancel Prediction
```
POST /api/replicate/models/{model_id}/predictions/{prediction_id}/cancel
```

**Parameters:**
- `model_id`: The model identifier that created the prediction
- `prediction_id`: The prediction ID to cancel

**Returns:**
```json
{
  "id": "pred_abc123",
  "status": "canceled"
}
```

### Get Model Info
```
GET /api/replicate/models/{model_id}/info
```

Returns model metadata, versions, and schema.

### Health Check
```
GET /api/replicate/models/{model_id}/health
```

Returns:
```json
{
  "healthy": true,
  "model_id": "llama-70b"
}
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

5. **Cancel unnecessary predictions**:
   ```bash
   curl -X POST http://localhost:8099/api/replicate/models/{model_id}/predictions/{id}/cancel
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
location /api/replicate {
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

@app.post("/api/replicate/models/{model_id}/predict")
@limiter.limit("10/minute")
async def create_prediction(...):
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

2. Use streaming instead:
   ```bash
   curl -X POST .../stream  # Streaming avoids single-request timeout; long-lived connections may still be cut off by client/proxy timeouts
   ```

3. Check Replicate status:
   - https://replicate.com/status

### Predictions fail

**Symptom**: Prediction status shows "failed"

**Solutions:**
1. Check error message:
   ```bash
   curl http://localhost:8099/api/replicate/models/{model_id}/predictions/{id}
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
curl -X POST http://localhost:8099/api/replicate/models/llama-2-70b/predict \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "prompt": "What is the meaning of life?"
    }
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
