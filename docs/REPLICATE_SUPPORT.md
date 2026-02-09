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
- Model lifecycle management

## Key Features

✅ **Inference-only** - No local model deployment
✅ **No GPU required** - All computation runs on Replicate's infrastructure
✅ **Simple setup** - Just API key needed
✅ **Wide model selection** - Access to Meta Llama, Mistral, CodeLlama, Stable Diffusion, and thousands more
✅ **Automatic retries** - Built-in error recovery

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
| `cache.enabled` | ❌ No | `false` | Enable response caching (reduces API calls for identical requests) |
| `cache.ttl` | ❌ No | `300` | Cache time-to-live in seconds (5 minutes default) - **Note**: Only the first model to enable caching sets global TTL |
| `cache.max_size` | ❌ No | `1000` | Maximum number of cached responses - **Note**: Only the first model to enable caching sets global max_size |
| `rate_limit.requests_per_second` | ❌ No | `10` | Rate limit for API requests per second |
| `rate_limit.burst_capacity` | ❌ No | `20` | Burst capacity for rate limiter |

### Cache Architecture Note

**Important**: FluidMCP uses a **single global cache** shared across all Replicate models. The `cache.ttl` and `cache.max_size` settings from the **first model** that enables caching will be used for all subsequent models.

This means:
- ✅ All models share the same cache (efficient for duplicate requests across models)
- ⚠️ Per-model cache settings (different TTL/max_size) are not supported
- ⚠️ If Model A sets `ttl=300` and Model B sets `ttl=600`, only Model A's `ttl=300` is used

**Recommendation**: If you need different cache settings for different models, configure the first model with the most conservative settings (lowest TTL, smallest max_size) that work for all models.

**Future Enhancement**: Per-model caching with individual TTL/max_size settings could be implemented by maintaining a dictionary of caches keyed by `(ttl, max_size)` or `model_id`. See [response_cache.py:325](../fluidmcp/cli/services/response_cache.py) for implementation notes.

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

### Production Configuration with Caching and Rate Limiting

For production use, enable caching and rate limiting to optimize API usage and costs:

```json
{
  "mcpServers": {},
  "llmModels": {
    "llama-production": {
      "type": "replicate",
      "model": "meta/llama-2-70b-chat",
      "api_key": "${REPLICATE_API_TOKEN}",
      "default_params": {
        "temperature": 0.7,
        "max_tokens": 1000
      },
      "cache": {
        "enabled": true,
        "ttl": 3600,
        "max_size": 5000
      },
      "rate_limit": {
        "requests_per_second": 5,
        "burst_capacity": 10
      },
      "timeout": 120,
      "max_retries": 3
    }
  }
}
```

**Benefits:**
- **Caching**: Identical requests return cached responses instantly, saving API calls and costs
- **Rate Limiting**: Prevents exceeding Replicate's rate limits (token bucket algorithm)
- **Retries**: Automatic retry with exponential backoff for transient errors
- **Timeouts**: Prevents hanging requests

**Note**: Caching is disabled for streaming and webhook requests to ensure real-time behavior.

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
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
  // Note: Replicate API doesn't provide token counts, so usage fields are always 0
}
```

### Streaming Not Supported

Replicate-backed models do not support **OpenAI-compatible streaming** via `"stream": true` on the `/api/llm/...` endpoints. Such requests will return HTTP 501 (Not Implemented) because Replicate's API is fundamentally polling-based.

FluidMCP also exposes a legacy, Replicate-specific SSE endpoint at `/api/replicate/models/{model_id}/stream` that streams the results of polling Replicate; this endpoint is **deprecated** and is not a replacement for OpenAI-style token-by-token streaming.

For real-time streaming requirements, use vLLM or other providers that support native streaming. See [Limitations](#limitations) for details.

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

## Observability & Metrics

FluidMCP provides metrics endpoints to monitor cache performance and rate limiter utilization.

### Cache Statistics

Get cache performance metrics:

```bash
curl http://localhost:8099/api/metrics/cache/stats
```

**Response**:
```json
{
  "enabled": true,
  "hits": 150,
  "misses": 50,
  "size": 45,
  "max_size": 1000,
  "hit_rate": 75.0,
  "ttl": 300
}
```

**Metrics**:
- `hits` - Number of cache hits (requests served from cache)
- `misses` - Number of cache misses (requests that hit API)
- `hit_rate` - Cache effectiveness percentage (hits / total * 100)
- `size` - Current number of cached entries
- `max_size` - Maximum cache capacity (LRU eviction when exceeded)
- `ttl` - Time-to-live in seconds (how long entries stay cached)

**Use Cases**:
- Monitor cache effectiveness (aim for >70% hit rate)
- Identify if cache size needs adjustment
- Track cost savings from reduced API calls

### Clear Cache

Force fresh API calls by clearing cache:

```bash
curl -X POST http://localhost:8099/api/metrics/cache/clear
```

**Response**:
```json
{
  "message": "Cache cleared successfully",
  "entries_cleared": 45
}
```

Useful for testing or when you need to bypass cached responses.

### Rate Limiter Statistics

Get rate limiter stats for all models:

```bash
curl http://localhost:8099/api/metrics/rate-limiters
```

**Response**:
```json
{
  "rate_limiters": {
    "llama-2-70b": {
      "available_tokens": 18.5,
      "capacity": 20,
      "rate": 10.0,
      "utilization_pct": 7.5
    },
    "mistral-7b": {
      "available_tokens": 15.2,
      "capacity": 20,
      "rate": 5.0,
      "utilization_pct": 24.0
    }
  },
  "total_models": 2
}
```

**Metrics per model**:
- `available_tokens` - Tokens available for immediate use
- `capacity` - Burst capacity (max tokens in bucket)
- `rate` - Tokens per second (steady-state rate)
- `utilization_pct` - How much capacity is in use (100% = fully throttled)

**Use Cases**:
- Check if rate limits are being hit (utilization > 80%)
- Identify which models need higher rate limits
- Monitor API call patterns

### Per-Model Rate Limiter Stats

Get stats for a specific model:

```bash
curl http://localhost:8099/api/metrics/rate-limiters/llama-2-70b
```

**Response**:
```json
{
  "model_id": "llama-2-70b",
  "available_tokens": 18.5,
  "capacity": 20,
  "rate": 10.0,
  "utilization_pct": 7.5
}
```

### Monitoring Best Practices

1. **Track cache hit rates** - Monitor `/api/metrics/cache/stats` every 5-10 minutes
   - Hit rate < 50%: Cache TTL too short or max_size too small
   - Hit rate > 90%: Consider increasing cache size for more savings

2. **Monitor rate limiter utilization** - Check `/api/metrics/rate-limiters` periodically
   - Utilization > 80%: Increase `rate` or `burst_capacity` in config
   - Utilization < 20%: Rate limits may be too conservative

3. **Set up alerts**:
   ```bash
   # Alert if cache hit rate drops below 60%
   curl http://localhost:8099/api/metrics/cache/stats | jq '.hit_rate < 60'

   # Alert if any model exceeds 90% utilization
   curl http://localhost:8099/api/metrics/rate-limiters | jq '.rate_limiters[].utilization_pct > 90'
   ```

4. **Cost tracking** - Use cache hits to estimate cost savings:
   ```
   Cost savings = (cache_hits / total_requests) * total_api_cost
   ```

### Unified Metrics Integration (Prometheus)

Replicate metrics are automatically integrated with FluidMCP's unified Prometheus metrics system. When you query the API endpoints above, the metrics are also updated in the global registry for Prometheus scraping.

**Prometheus Metrics Exported**:

```
# Cache metrics (global, no labels)
fluidmcp_replicate_cache_hits_total          # Total cache hits
fluidmcp_replicate_cache_misses_total        # Total cache misses
fluidmcp_replicate_cache_size                # Current cache size
fluidmcp_replicate_cache_hit_rate            # Hit rate (0.0-1.0 ratio)

# Rate limiter metrics (per-model labels)
fluidmcp_replicate_rate_limiter_tokens{model_id="..."}         # Available tokens
fluidmcp_replicate_rate_limiter_utilization{model_id="..."}    # Utilization (0.0-1.0 ratio)
fluidmcp_replicate_rate_limiter_capacity{model_id="..."}       # Maximum capacity
fluidmcp_replicate_rate_limiter_rate{model_id="..."}           # Refill rate (tokens/sec)
```

**Prometheus Scrape Configuration**:

```yaml
scrape_configs:
  - job_name: 'fluidmcp'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:8099']
    metrics_path: '/metrics'  # FluidMCP exposes Prometheus metrics here
```

**Example Prometheus Queries**:

```promql
# Cache hit ratio (current snapshot since last restart/clear)
fluidmcp_replicate_cache_hits_total /
  (fluidmcp_replicate_cache_hits_total + fluidmcp_replicate_cache_misses_total)

# Cache hit rate (pre-computed as ratio 0.0-1.0)
fluidmcp_replicate_cache_hit_rate

# Models approaching rate limit (>80% utilization)
fluidmcp_replicate_rate_limiter_utilization > 0.8

# Current cumulative API calls saved by caching (since last restart/cache clear)
fluidmcp_replicate_cache_hits_total

# Average available tokens across all models
avg(fluidmcp_replicate_rate_limiter_tokens)
```

**Important**: Cache metrics are Gauges (absolute values) that may reset on cache clear. Do not use `rate()` or `increase()` functions on these metrics. For tracking changes over time, use the raw gauge values or the pre-computed `hit_rate` metric.

**Integration Details**:

- Metrics are auto-registered on startup (via `replicate_metrics.py`)
- Metrics automatically updated on every Prometheus scrape of `/metrics` endpoint
- Manual updates also available via `/api/metrics/*` REST endpoints
- No additional configuration required - works out of the box
- Compatible with Grafana, Prometheus AlertManager, etc.

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

**Test Coverage**: 25 tests covering:
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
- Client-side rate limiting is available via `rate_limit` config (token bucket algorithm)
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
