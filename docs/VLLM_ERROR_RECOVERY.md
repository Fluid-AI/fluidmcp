# vLLM Error Recovery System

FluidMCP includes a comprehensive error recovery system for vLLM processes, with automatic health monitoring, restart policies, and management APIs.

## Features

### 1. Automatic Health Monitoring
- **Background Health Checks**: Monitors vLLM processes every 30 seconds
- **HTTP Endpoint Probing**: Tests `/health` and `/v1/models` endpoints
- **Process Status Tracking**: Detects crashed or unresponsive processes
- **CUDA OOM Detection**: Parses stderr logs for GPU memory errors

### 2. Automatic Recovery
- **Exponential Backoff**: Restart delays increase with each attempt (5s, 10s, 20s, 40s, 80s, 160s)
- **Restart Limits**: Configurable maximum restart attempts (default: 3)
- **Failure Threshold**: Triggers restart after 2 consecutive health check failures
- **Graceful Shutdown**: SIGTERM with fallback to SIGKILL

### 3. Management APIs
- **Status Endpoints**: Query health, uptime, restart count
- **Control Endpoints**: Manually restart or stop processes
- **Log Access**: Retrieve stderr logs via API
- **Health Checks**: Trigger on-demand health checks

## Configuration

### Restart Policies

Configure restart behavior in your FluidMCP configuration:

```json
{
  "llmModels": {
    "vllm": {
      "command": "vllm",
      "args": ["serve", "facebook/opt-125m", "--port", "8001"],
      "endpoints": {
        "base_url": "http://localhost:8001/v1"
      },
      "restart_policy": "on-failure",
      "max_restarts": 3,
      "restart_delay": 5
    }
  }
}
```

### Policy Options

**`restart_policy`** (string, default: `"no"`)
- `"no"` - Never restart automatically
- `"on-failure"` - Restart only on crashes or health check failures
- `"always"` - Restart whenever process stops (planned for future)

**`max_restarts`** (integer, default: `3`)
- Maximum number of restart attempts
- After reaching limit, process remains stopped
- Set to `0` to disable restart limits (not recommended)

**`restart_delay`** (integer, default: `5`)
- Base delay in seconds between restarts
- Actual delay uses exponential backoff: `delay * (2 ^ attempt)`
- Example: 5s, 10s, 20s, 40s, 80s, 160s

**`health_check_timeout`** (float, default: `10.0`)
- Timeout in seconds for health check HTTP requests
- Increase for large models with slow startup times
- Recommended: 10-30 seconds depending on model size

**`health_check_interval`** (integer, default: `30`)
- Interval in seconds between health checks
- Only applies when health monitoring is enabled
- Recommended: 30-60 seconds for production

### Health Check Configuration

Health checks are automatically configured based on the `endpoints.base_url` setting:

```json
{
  "llmModels": {
    "vllm": {
      "endpoints": {
        "base_url": "http://localhost:8001/v1"
      },
      "health_check_timeout": 30.0,
      "health_check_interval": 60
    }
  }
}
```

**Configuration for Large Models:**
```json
{
  "llmModels": {
    "llama-70b": {
      "command": "vllm",
      "args": ["serve", "meta-llama/Llama-2-70b-hf", "--port", "8002"],
      "endpoints": {
        "base_url": "http://localhost:8002/v1"
      },
      "restart_policy": "on-failure",
      "max_restarts": 3,
      "health_check_timeout": 30.0,
      "health_check_interval": 60
    }
  }
}
```

If `base_url` is not provided, health checks will only verify process status (no HTTP checks).

## Management APIs

### List All LLM Models

```bash
GET /api/llm/models
```

**Response:**
```json
{
  "models": [
    {
      "id": "vllm",
      "is_running": true,
      "is_healthy": true,
      "health_message": null,
      "restart_policy": "on-failure",
      "restart_count": 0,
      "max_restarts": 3,
      "consecutive_health_failures": 0,
      "uptime_seconds": 125.3,
      "last_restart_time": null,
      "last_health_check_time": 1705423890.12
    }
  ],
  "total": 1
}
```

### Get Model Status

```bash
GET /api/llm/models/{model_id}
```

**Response:**
```json
{
  "id": "vllm",
  "is_running": true,
  "is_healthy": true,
  "health_message": null,
  "restart_policy": "on-failure",
  "restart_count": 0,
  "max_restarts": 3,
  "consecutive_health_failures": 0,
  "uptime_seconds": 125.3,
  "last_restart_time": null,
  "last_health_check_time": 1705423890.12,
  "has_cuda_oom": false
}
```

### Restart Model

```bash
POST /api/llm/models/{model_id}/restart
```

**Response (Success):**
```json
{
  "message": "LLM model 'vllm' restarted successfully",
  "restart_count": 1,
  "uptime_seconds": 2.1
}
```

**Response (Error - Policy):**
```json
{
  "detail": "Cannot restart model 'vllm': restart policy is 'no' or max restarts (3) reached"
}
```

### Stop Model

```bash
POST /api/llm/models/{model_id}/stop?force=false
```

**Query Parameters:**
- `force` (boolean, default: `false`) - If `true`, force kill with SIGKILL

**Response:**
```json
{
  "message": "LLM model 'vllm' stopped gracefully"
}
```

### Get Model Logs

```bash
GET /api/llm/models/{model_id}/logs?lines=100
```

**Query Parameters:**
- `lines` (integer, default: `100`) - Number of recent log lines (1-10000)

**Response:**
```json
{
  "model_id": "vllm",
  "lines": [
    "INFO: Loading model facebook/opt-125m\n",
    "INFO: Model loaded successfully\n"
  ],
  "total_lines": 245,
  "returned_lines": 100
}
```

### Trigger Health Check

```bash
POST /api/llm/models/{model_id}/health-check
```

**Response:**
```json
{
  "model_id": "vllm",
  "is_healthy": true,
  "health_message": null,
  "consecutive_health_failures": 0,
  "last_health_check_time": 1705423890.12,
  "has_cuda_oom": false
}
```

## Error Detection

### CUDA Out of Memory

The system automatically detects CUDA OOM errors in stderr logs:

```python
# Detection patterns:
- "cuda out of memory"
- "cudaerror"
- "out of memory"
```

When detected:
1. Logged with actionable recommendations
2. Exposed via API (`has_cuda_oom` field)
3. Can be checked manually via logs endpoint

**Recommendations for CUDA OOM:**
- Reduce `--gpu-memory-utilization` (default: 0.9)
- Use smaller `max_tokens` values
- Reduce model context length (`--max-model-len`)
- Use a smaller model variant

### Health Check Failures

**Failure Detection:**
- HTTP request timeouts (10 seconds)
- Connection refused errors
- Non-200 status codes
- Process not running

**Restart Trigger:**
- 2 consecutive health check failures (60 seconds apart)
- Immediate restart on process crash

## Monitoring Integration

### Prometheus Metrics

The error recovery system integrates with FluidMCP's metrics:

```
# Server restarts
fluidmcp_server_restarts_total{server="vllm"} 2

# Health check status (1=healthy, 0=unhealthy)
fluidmcp_server_status{server="vllm"} 1

# Server uptime (resets on restart)
fluidmcp_server_uptime_seconds{server="vllm"} 125.3
```

See [MONITORING.md](MONITORING.md) for complete metrics documentation.

## Troubleshooting

### Process Won't Restart

**Check restart count:**
```bash
curl http://localhost:8099/llm/models/vllm
```

If `restart_count >= max_restarts`:
1. Check logs for root cause: `GET /api/llm/models/vllm/logs?lines=500`
2. Fix underlying issue (CUDA OOM, port conflict, etc.)
3. Update configuration if needed
4. Restart FluidMCP server to reset restart count

### CUDA OOM Errors

**Check for OOM:**
```bash
curl http://localhost:8099/llm/models/vllm | jq '.has_cuda_oom'
```

**Solutions:**
1. Reduce GPU memory utilization in config:
   ```json
   {"args": ["serve", "model", "--gpu-memory-utilization", "0.7"]}
   ```
2. Reduce max context length:
   ```json
   {"args": ["serve", "model", "--max-model-len", "2048"]}
   ```
3. Use a smaller model (e.g., opt-125m instead of opt-1.3b)

### Health Checks Failing

**Manual health check:**
```bash
curl -X POST http://localhost:8099/llm/models/vllm/health-check
```

**Common causes:**
- vLLM still loading (check logs for "INFO: Uvicorn running")
- Wrong port in `endpoints.base_url`
- Firewall blocking localhost connections
- vLLM crashed (check `is_running` status)

### Logs Not Available

**Common causes:**
- Process never started (logs created on first start)
- Log file permissions issue
- Log directory not created (`~/.fluidmcp/logs/`)

## Best Practices

### 1. Configure Restart Policies Carefully

```json
{
  "restart_policy": "on-failure",
  "max_restarts": 3,
  "restart_delay": 5
}
```

- Use `"on-failure"` for production vLLM deployments
- Set `max_restarts` to prevent infinite restart loops
- Increase `restart_delay` for slow-loading models

### 2. Monitor Health via APIs

```bash
# Cron job to check health every 5 minutes
*/5 * * * * curl -sf http://localhost:8099/llm/models/vllm | jq '.is_healthy' || echo "vLLM unhealthy!"
```

### 3. Set Up Alerts

Use Prometheus + Alertmanager to alert on:
- `fluidmcp_server_status{server="vllm"} == 0` - Model unhealthy
- `rate(fluidmcp_server_restarts_total[5m]) > 0` - Frequent restarts
- `fluidmcp_server_uptime_seconds < 60` - Recent restart

### 4. Check Logs Regularly

```bash
# Get recent errors
curl http://localhost:8099/llm/models/vllm/logs?lines=100 | jq -r '.lines[]' | grep ERROR
```

### 5. Test Recovery Scenarios

```bash
# Test crash recovery
curl -X POST "http://localhost:8099/llm/models/vllm/stop?force=true"

# Wait 30 seconds for health check
sleep 30

# Verify automatic restart
curl http://localhost:8099/llm/models/vllm | jq '.restart_count'
```

## Architecture

### Components

**LLMProcess Class:**
- Manages single vLLM process lifecycle
- Tracks health check results
- Implements restart logic with exponential backoff
- Parses stderr logs for CUDA OOM

**LLMHealthMonitor Class:**
- Background asyncio task
- Polls all LLM processes every 30 seconds
- Triggers automatic restarts based on policy
- Logs all health check events

**Management API:**
- FastAPI endpoints in `management.py`
- Direct access to `_llm_processes` registry
- Async health checks for real-time status
- Integrated with FluidMCP authentication

### Health Check Flow

```
┌─────────────────┐
│ Health Monitor  │ (every 30s)
└────────┬────────┘
         │
         ├──> Check process.is_running()
         │
         ├──> HTTP GET /health
         │    HTTP GET /v1/models
         │
         ├──> Update consecutive_health_failures
         │
         └──> If failures >= 2:
              ├──> Check restart_policy
              ├──> Check can_restart()
              ├──> Calculate exponential backoff
              ├──> Stop process (SIGTERM)
              ├──> Start new process
              └──> Update restart_count
```

### Process States

```
┌─────────┐
│ Starting│──> Start command
└────┬────┘
     │
     v
┌─────────┐
│ Healthy │<──> Periodic health checks
└────┬────┘
     │
     v (2 consecutive failures)
┌─────────┐
│Unhealthy│──> Trigger restart (if policy allows)
└────┬────┘
     │
     v (restart_count < max_restarts)
┌─────────┐
│Restarting│──> Exponential backoff delay
└────┬────┘
     │
     v
┌─────────┐
│ Healthy │ (or)
└─────────┘
┌─────────┐
│  Failed │ (max_restarts reached)
└─────────┘
```

## Security Considerations

### Authentication

All management APIs require authentication when `FMCP_SECURE_MODE=true`:

```bash
export FMCP_BEARER_TOKEN="your-secret-token"
export FMCP_SECURE_MODE="true"

curl -H "Authorization: Bearer your-secret-token" \
  http://localhost:8099/llm/models
```

### Rate Limiting

Consider rate limiting management APIs in production:
- Restart API: Max 10 requests/minute per model
- Logs API: Max 30 requests/minute per model

### Log Privacy

Stderr logs may contain sensitive information:
- API keys in stack traces
- Model paths revealing infrastructure
- User prompts (if logging enabled)

**Recommendations:**
- Restrict `/llm/models/{id}/logs` endpoint access
- Rotate logs regularly
- Sanitize logs before exposing via API

## Future Enhancements

Planned improvements for error recovery:

1. **Graceful Degradation**
   - Fallback to smaller model on OOM
   - Queue requests during restart
   - Circuit breaker pattern

2. **Smart Restart**
   - Adjust `--gpu-memory-utilization` after OOM
   - Reduce `--max-model-len` after OOM
   - Detect port conflicts and retry with different port

3. **Multi-Process Resilience**
   - Health checks across multiple vLLM instances
   - Automatic load balancing
   - Zero-downtime restarts

4. **Advanced Monitoring**
   - GPU memory usage tracking
   - Request latency percentiles
   - Model-specific error rates

## Related Documentation

- [Monitoring Guide](MONITORING.md) - Prometheus metrics and Grafana dashboards
- [vLLM Configuration](../examples/vllm-with-error-recovery.json) - Example configuration
- [Management API](../fluidmcp/cli/api/management.py) - Source code for management endpoints
