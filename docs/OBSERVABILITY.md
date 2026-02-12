# FluidMCP Observability and Metrics

## Overview

FluidMCP includes comprehensive observability features for monitoring LLM inference workloads. Track request counts, latency, token usage, and error rates across all models.

**Features:**
- 📊 Per-model metrics tracking
- 🔢 Prometheus-compatible export
- 📈 JSON API for dashboards
- 💰 Token usage tracking (cost estimation)
- ⚡ Real-time latency statistics
- 🚨 Error rate monitoring

---

## Quick Start

### Enable Metrics Collection

Metrics are collected automatically when requests are made to LLM endpoints. No configuration needed!

### View Metrics

```bash
# Prometheus format (for Grafana, Datadog, etc.)
curl http://localhost:8099/api/metrics

# JSON format (for custom dashboards)
curl http://localhost:8099/api/metrics/json

# Specific model
curl http://localhost:8099/api/metrics/models/llama-2-70b
```

---

## API Endpoints

### `GET /api/metrics`

Returns Prometheus-compatible text format metrics.

**Response:**
```
# HELP fluidmcp_llm_requests_total Total number of LLM inference requests
# TYPE fluidmcp_llm_requests_total counter
fluidmcp_llm_requests_total{model_id="llama-2-70b",provider="replicate"} 150
fluidmcp_llm_requests_successful{model_id="llama-2-70b",provider="replicate"} 145
fluidmcp_llm_requests_failed{model_id="llama-2-70b",provider="replicate"} 5

# HELP fluidmcp_llm_latency_seconds Request latency statistics
# TYPE fluidmcp_llm_latency_seconds gauge
fluidmcp_llm_latency_seconds{model_id="llama-2-70b",provider="replicate",stat="avg"} 2.340000
fluidmcp_llm_latency_seconds{model_id="llama-2-70b",provider="replicate",stat="min"} 0.850000
fluidmcp_llm_latency_seconds{model_id="llama-2-70b",provider="replicate",stat="max"} 5.120000

# HELP fluidmcp_llm_tokens_total Total tokens processed
# TYPE fluidmcp_llm_tokens_total counter
fluidmcp_llm_tokens_total{model_id="llama-2-70b",provider="replicate",type="prompt"} 12500
fluidmcp_llm_tokens_total{model_id="llama-2-70b",provider="replicate",type="completion"} 45000
fluidmcp_llm_tokens_total{model_id="llama-2-70b",provider="replicate",type="total"} 57500

# HELP fluidmcp_llm_errors_by_status Error counts by HTTP status code
# TYPE fluidmcp_llm_errors_by_status counter
fluidmcp_llm_errors_by_status{model_id="llama-2-70b",provider="replicate",status_code="429"} 3
fluidmcp_llm_errors_by_status{model_id="llama-2-70b",provider="replicate",status_code="500"} 2

# HELP fluidmcp_uptime_seconds Time since metrics collection started
# TYPE fluidmcp_uptime_seconds gauge
fluidmcp_uptime_seconds 3600
```

### `GET /api/metrics/json`

Returns JSON format metrics for all models.

**Response:**
```json
{
  "uptime_seconds": 3600,
  "models": {
    "llama-2-70b": {
      "provider_type": "replicate",
      "requests": {
        "total": 150,
        "successful": 145,
        "failed": 5,
        "success_rate_percent": 96.67,
        "error_rate_percent": 3.33
      },
      "latency": {
        "avg_seconds": 2.34,
        "min_seconds": 0.85,
        "max_seconds": 5.12
      },
      "tokens": {
        "prompt": 12500,
        "completion": 45000,
        "total": 57500
      },
      "errors_by_status": {
        "429": 3,
        "500": 2
      }
    }
  }
}
```

### `GET /api/metrics/models/{model_id}`

Returns detailed metrics for a specific model.

**Example:**
```bash
curl http://localhost:8099/api/metrics/models/llama-2-70b
```

**Response:**
```json
{
  "model_id": "llama-2-70b",
  "provider_type": "replicate",
  "requests": {
    "total": 150,
    "successful": 145,
    "failed": 5,
    "success_rate_percent": 96.67,
    "error_rate_percent": 3.33
  },
  "latency": {
    "avg_seconds": 2.34,
    "min_seconds": 0.85,
    "max_seconds": 5.12
  },
  "tokens": {
    "prompt": 12500,
    "completion": 45000,
    "total": 57500
  },
  "errors_by_status": {
    "429": 3,
    "500": 2
  }
}
```

### `POST /api/metrics/reset`

Reset metrics for specific model or all models.

**Examples:**
```bash
# Reset all metrics
curl -X POST http://localhost:8099/api/metrics/reset

# Reset specific model
curl -X POST "http://localhost:8099/api/metrics/reset?model_id=llama-2-70b"
```

---

## Grafana Integration

### 1. Add Prometheus Data Source

In Grafana, add FluidMCP as a Prometheus data source:

- **URL**: `http://localhost:8099/api/metrics`
- **Scrape interval**: 15s (recommended)
- **HTTP Method**: GET

### 2. Import Dashboard

Use this dashboard JSON:

```json
{
  "dashboard": {
    "title": "FluidMCP LLM Metrics",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(fluidmcp_llm_requests_total[5m])"
          }
        ]
      },
      {
        "title": "Success Rate",
        "targets": [
          {
            "expr": "fluidmcp_llm_requests_successful / clamp_min(fluidmcp_llm_requests_total, 1)"
          }
        ]
      },
      {
        "title": "Average Latency",
        "targets": [
          {
            "expr": "fluidmcp_llm_latency_seconds{stat=\"avg\"}"
          }
        ]
      },
      {
        "title": "Token Usage",
        "targets": [
          {
            "expr": "rate(fluidmcp_llm_tokens_total[5m])"
          }
        ]
      }
    ]
  }
}
```

### 3. Key Queries

**Request rate by model:**
```promql
rate(fluidmcp_llm_requests_total[5m])
```

**Error rate percentage:**
```promql
(rate(fluidmcp_llm_requests_failed[5m]) / clamp_min(rate(fluidmcp_llm_requests_total[5m]), 1)) * 100
```

**Max (worst-case) latency:**
```promql
fluidmcp_llm_latency_seconds{stat="max"}
```

Note: This shows the maximum observed latency (outlier), not a P95 percentile. For true P95 tracking, histogram buckets would be needed.

**Token cost estimate (Replicate Llama 2 70B: $0.65/1M tokens):**
```promql
(rate(fluidmcp_llm_tokens_total{type="total",provider="replicate"}[5m]) * 0.65) / 1000000
```

---

## Datadog Integration

### 1. Configure Datadog Agent

Add to `datadog.yaml`:

```yaml
openmetrics_check:
  instances:
    - prometheus_url: http://localhost:8099/api/metrics
      namespace: "fluidmcp"
      metrics:
        - fluidmcp_llm_*
```

### 2. Dashboard Metrics

Key Datadog metrics:
- `fluidmcp.llm.requests.total`
- `fluidmcp.llm.requests.successful`
- `fluidmcp.llm.latency.seconds`
- `fluidmcp.llm.tokens.total`

---

## Cost Tracking

### Token Usage → Cost Estimation

Use metrics to estimate API costs:

**Replicate (Llama 2 70B: ~$0.65/1M tokens):**
```bash
curl http://localhost:8099/api/metrics/json | jq '.models["llama-2-70b"].tokens.total'
# Output: 57500
# Cost: 57500 * $0.65 / 1000000 = $0.037
```

**vLLM (self-hosted: fixed cost):**
- Track request count for capacity planning
- Monitor latency for scaling decisions

### Automated Cost Alerts

**Example: Alert when daily token cost exceeds $10:**

```python
import requests

response = requests.get("http://localhost:8099/api/metrics/json")
data = response.json()

total_cost = 0
for model, metrics in data["models"].items():
    if metrics["provider_type"] == "replicate":
        tokens = metrics["tokens"]["total"]
        # Llama 2 70B pricing
        cost = (tokens * 0.65) / 1_000_000
        total_cost += cost

if total_cost > 10:
    # Send alert
    print(f"ALERT: Daily cost exceeded $10 (current: ${total_cost:.2f})")
```

---

## Performance Monitoring

### Latency Tracking

Metrics track three latency statistics per model:
- **Average**: `avg_seconds`
- **Minimum**: `min_seconds`
- **Maximum**: `max_seconds`

**Identify slow requests:**
```bash
curl http://localhost:8099/api/metrics/json | \
  jq '.models | to_entries[] | select(.value.latency.max_seconds > 10)'
```

### Success Rate Monitoring

**Alert on low success rate:**
```bash
# Check if success rate < 95%
curl http://localhost:8099/api/metrics/json | \
  jq '.models | to_entries[] | select(.value.requests.success_rate_percent < 95)'
```

---

## Load Testing

FluidMCP includes Locust load testing scripts.

### Run Load Test

```bash
# Install Locust
pip install locust

# Start FluidMCP
fluidmcp run config.json --file --start-server

# Run load test (web UI)
locust -f examples/load_test_locust.py --host=http://localhost:8099

# Open browser: http://localhost:8089
# Configure: 10 users, spawn rate 2/sec, duration 60s
```

### Headless Load Test

```bash
locust -f examples/load_test_locust.py \
  --host=http://localhost:8099 \
  --users 10 \
  --spawn-rate 2 \
  --run-time 60s \
  --headless
```

### Stress Test

```bash
# High load stress test
MODEL_ID=llama-2-70b locust -f examples/load_test_locust.py \
  --host=http://localhost:8099 \
  --user-class StressTestUser \
  --users 50 \
  --spawn-rate 10 \
  --run-time 120s \
  --headless
```

---

## Troubleshooting

### Metrics Not Updating

**Problem**: Metrics show 0 requests
**Solution**: Metrics only track requests to unified `/api/llm/v1/...` endpoints

**Verify metrics are being collected:**
```bash
# Make a request
curl -X POST http://localhost:8099/api/llm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "test-model", "messages": [{"role": "user", "content": "test"}]}'

# Check metrics
curl http://localhost:8099/api/metrics/models/test-model
```

### High Latency

**Problem**: `max_seconds` is very high
**Possible causes:**
- Replicate: Cold start (first request to model)
- vLLM: Model overloaded, need to scale
- Network: Check connectivity to provider

**Debug:**
```bash
# Check model health
curl -X POST http://localhost:8099/api/llm/models/model-id/health-check

# Check error rates
curl http://localhost:8099/api/metrics/json | jq '.models["model-id"].errors_by_status'
```

### Token Count Accuracy

**Note**: Token counts are estimates based on response data.

- **Replicate**: Accurate (from API response)
- **vLLM**: Estimated (usage field in response)
- **OpenAI-compatible**: Uses response `usage` field

---

## Best Practices

### 1. Monitor Success Rate

Alert when success rate drops below 95%:
```bash
# Grafana alert rule
(fluidmcp_llm_requests_successful / fluidmcp_llm_requests_total) < 0.95
```

### 2. Track Cost Daily

Reset metrics daily and track token usage:
```bash
# Cron job: Reset metrics at midnight
0 0 * * * curl -X POST http://localhost:8099/api/metrics/reset
```

### 3. Capacity Planning

Use metrics to plan scaling:
- Request rate > 10/sec → Add more vLLM instances
- Avg latency > 5s → Optimize model or upgrade hardware
- Error rate > 5% → Investigate root cause

### 4. Cost Optimization

Monitor token usage to optimize costs:
- High prompt tokens → Reduce context window
- High completion tokens → Lower `max_tokens`
- High total cost → Consider smaller model

---

## API Reference

See [API Documentation](API.md) for complete endpoint details.

---

## Related Documentation

- [Replicate Support](REPLICATE_SUPPORT.md) - Replicate-specific features
- [Architecture](../CLAUDE.md) - System architecture
- [Load Testing](../examples/load_test_locust.py) - Load testing scripts

---

**Questions?** Open an issue at [github.com/Fluid-AI/fluidmcp](https://github.com/Fluid-AI/fluidmcp/issues)
