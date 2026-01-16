# FluidMCP Monitoring & Metrics

FluidMCP provides comprehensive Prometheus-compatible metrics for monitoring MCP server performance, health, and resource utilization.

## Table of Contents

- [Quick Start](#quick-start)
- [Available Metrics](#available-metrics)
- [Prometheus Setup](#prometheus-setup)
- [Grafana Dashboard](#grafana-dashboard)
- [Alert Rules](#alert-rules)
- [Metrics Reference](#metrics-reference)
- [Best Practices](#best-practices)

## Quick Start

### 1. Start FluidMCP Server

```bash
fluidmcp run config.json --file --start-server
```

The server exposes metrics at `http://localhost:8099/metrics`

### 2. View Raw Metrics

```bash
curl http://localhost:8099/metrics
```

Output example:
```
# HELP fluidmcp_requests_total Total number of requests processed
# TYPE fluidmcp_requests_total counter
fluidmcp_requests_total{server_id="filesystem",method="tools/list",status="success"} 42

# HELP fluidmcp_request_duration_seconds Request processing duration in seconds
# TYPE fluidmcp_request_duration_seconds histogram
fluidmcp_request_duration_seconds_bucket{server_id="filesystem",method="tools/call",le="0.005"} 15
fluidmcp_request_duration_seconds_bucket{server_id="filesystem",method="tools/call",le="0.01"} 28
...
```

### 3. Set Up Prometheus (Optional)

See [Prometheus Setup](#prometheus-setup) for detailed instructions.

## Available Metrics

FluidMCP exposes the following metric categories:

### Request Metrics
- **Request counts** - Total requests by server, method, and status
- **Error counts** - Errors by server and error type
- **Active requests** - Currently processing requests
- **Request latency** - Response time distribution (histograms)

### Server Lifecycle Metrics
- **Server status** - Current state (stopped/starting/running/error/restarting)
- **Restart counts** - Total restarts by reason
- **Uptime** - Time since last start

### Resource Metrics
- **GPU memory usage** - Bytes allocated per GPU
- **GPU memory utilization** - Utilization ratio (0.0-1.0)

### Tool Execution Metrics
- **Tool call counts** - Calls by tool name and status
- **Tool execution latency** - Execution time distribution

### Streaming Metrics
- **Streaming request counts** - Total streaming requests by completion status
- **Active streams** - Currently active streaming connections

## Prometheus Setup

### Step 1: Install Prometheus

```bash
# macOS
brew install prometheus

# Linux
wget https://github.com/prometheus/prometheus/releases/latest/download/prometheus-*.linux-amd64.tar.gz
tar xvfz prometheus-*.linux-amd64.tar.gz
cd prometheus-*
```

### Step 2: Configure Prometheus

Create or update `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'fluidmcp'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['localhost:8099']
```

Or use the example configuration:
```bash
cp examples/prometheus-config.yml prometheus.yml
```

### Step 3: Start Prometheus

```bash
prometheus --config.file=prometheus.yml
```

Access Prometheus UI at [http://localhost:9090](http://localhost:9090)

### Step 4: Query Metrics

Example queries in Prometheus:

```promql
# Request rate per server
sum(rate(fluidmcp_requests_total[1m])) by (server_id)

# Error rate
sum(rate(fluidmcp_errors_total[1m])) by (server_id, error_type)

# P95 request latency
histogram_quantile(0.95, sum(rate(fluidmcp_request_duration_seconds_bucket[5m])) by (le, server_id))

# GPU memory utilization
fluidmcp_gpu_memory_utilization_ratio

# Active requests
sum(fluidmcp_active_requests) by (server_id)
```

## Grafana Dashboard

### Step 1: Install Grafana

```bash
# macOS
brew install grafana

# Linux
sudo apt-get install -y grafana
```

### Step 2: Start Grafana

```bash
# macOS
brew services start grafana

# Linux
sudo systemctl start grafana-server
```

Access Grafana at [http://localhost:3000](http://localhost:3000) (default credentials: admin/admin)

### Step 3: Add Prometheus Data Source

1. Go to Configuration → Data Sources
2. Click "Add data source"
3. Select "Prometheus"
4. Set URL to `http://localhost:9090`
5. Click "Save & Test"

### Step 4: Import Dashboard

1. Go to Dashboards → Import
2. Upload `examples/grafana-dashboard.json`
3. Select Prometheus data source
4. Click "Import"

The dashboard includes:
- Request rate and error rate graphs
- Active requests and server status stats
- Request latency percentiles (P50, P95, P99)
- GPU memory utilization gauge
- Active streams and uptime stats
- Tool execution metrics
- Restart counts and status distributions

## Alert Rules

Create `alerts.yml` with alert definitions:

```yaml
groups:
  - name: fluidmcp_alerts
    interval: 30s
    rules:
      # High error rate alert
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(fluidmcp_errors_total[5m]))
            /
            sum(rate(fluidmcp_requests_total[5m]))
          ) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }}"

      # Server down alert
      - alert: ServerDown
        expr: fluidmcp_server_status == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Server {{ $labels.server_id }} is down"

      # High GPU memory alert
      - alert: HighGPUMemory
        expr: fluidmcp_gpu_memory_utilization_ratio > 0.95
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High GPU memory utilization"
          description: "GPU memory at {{ $value | humanizePercentage }}"

      # High latency alert
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(fluidmcp_request_duration_seconds_bucket[5m])) by (le, server_id)
          ) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High request latency"
          description: "P95 latency is {{ $value }}s"
```

Add to `prometheus.yml`:
```yaml
rule_files:
  - "alerts.yml"
```

## Metrics Reference

### Counter Metrics

#### `fluidmcp_requests_total`
Total number of requests processed.

Labels:
- `server_id` - Server identifier
- `method` - JSON-RPC method (e.g., "tools/list", "tools/call")
- `status` - Request status ("success" or "error")

#### `fluidmcp_errors_total`
Total number of errors encountered.

Labels:
- `server_id` - Server identifier
- `error_type` - Error classification (e.g., "server_not_found", "broken_pipe", "timeout")

#### `fluidmcp_server_restarts_total`
Total number of server restarts.

Labels:
- `server_id` - Server identifier
- `reason` - Restart reason (e.g., "manual_restart", "crash", "health_check_failure")

#### `fluidmcp_tool_calls_total`
Total number of tool calls executed.

Labels:
- `server_id` - Server identifier
- `tool_name` - Name of the tool
- `status` - Call status ("success" or "error")

#### `fluidmcp_streaming_requests_total`
Total number of streaming requests.

Labels:
- `server_id` - Server identifier
- `completion_status` - How the stream ended ("success", "error", "broken_pipe")

### Gauge Metrics

#### `fluidmcp_active_requests`
Number of requests currently being processed.

Labels:
- `server_id` - Server identifier

#### `fluidmcp_server_status`
Current server status code.

Labels:
- `server_id` - Server identifier

Values:
- `0` - Stopped
- `1` - Starting
- `2` - Running
- `3` - Error
- `4` - Restarting

#### `fluidmcp_server_uptime_seconds`
Server uptime in seconds since last start.

Labels:
- `server_id` - Server identifier

#### `fluidmcp_gpu_memory_bytes`
GPU memory usage in bytes.

Labels:
- `server_id` - Server identifier
- `gpu_index` - GPU index (0, 1, 2, ...)

#### `fluidmcp_gpu_memory_utilization_ratio`
GPU memory utilization ratio (0.0-1.0).

Labels:
- `server_id` - Server identifier

#### `fluidmcp_active_streams`
Number of active streaming connections.

Labels:
- `server_id` - Server identifier

### Histogram Metrics

#### `fluidmcp_request_duration_seconds`
Request processing duration distribution.

Labels:
- `server_id` - Server identifier
- `method` - JSON-RPC method

Buckets (seconds):
- 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0

Suffixes:
- `_bucket{le="X"}` - Count of requests ≤ X seconds
- `_sum` - Total duration of all requests
- `_count` - Total number of requests

#### `fluidmcp_tool_execution_seconds`
Tool execution duration distribution.

Labels:
- `server_id` - Server identifier
- `tool_name` - Name of the tool

Buckets: Same as `request_duration_seconds`

## Best Practices

### 1. Monitoring Strategy

**Essential Metrics to Monitor:**
- Request rate and error rate (detect anomalies)
- Server status (detect outages)
- Request latency percentiles (detect performance degradation)
- GPU memory utilization (prevent OOM errors)
- Active requests (detect traffic spikes)

**Recommended Alert Thresholds:**
- Error rate > 5% for 5 minutes → Warning
- Server down for > 1 minute → Critical
- GPU memory > 95% for 5 minutes → Warning
- P95 latency > 5s for 5 minutes → Warning
- Active requests > 100 → Warning

### 2. Performance Optimization

**High Request Volume:**
- Monitor `fluidmcp_active_requests` to identify bottlenecks
- Check `request_duration_seconds` percentiles for slowdowns
- Use rate limiting if `active_requests` consistently high

**GPU Memory Issues:**
- Monitor `gpu_memory_utilization_ratio` closely
- Set alerts at 0.90 and 0.95 thresholds
- Adjust `gpu_memory_utilization` config if OOM errors occur

**Tool Execution Bottlenecks:**
- Track `tool_execution_seconds` per tool
- Identify slow tools with high P95 latency
- Consider caching or optimization for slow tools

### 3. Production Deployment

**Prometheus Configuration:**
- Set `scrape_interval: 15s` for general monitoring
- Use `scrape_interval: 5s` for high-frequency monitoring (development/debugging)
- Enable remote write for long-term storage (Thanos, Cortex, etc.)

**Retention:**
- Prometheus default: 15 days
- Adjust with `--storage.tsdb.retention.time=30d` flag
- Use remote storage for longer retention

**High Availability:**
- Run multiple Prometheus instances
- Use Thanos or Cortex for global view
- Set up Alertmanager for notification routing

### 4. Debugging with Metrics

**Server Not Responding:**
```promql
# Check if server is running
fluidmcp_server_status{server_id="your-server"} == 2

# Check uptime
fluidmcp_server_uptime_seconds{server_id="your-server"}

# Check recent errors
rate(fluidmcp_errors_total{server_id="your-server"}[5m])
```

**High Latency Issues:**
```promql
# P95 latency by method
histogram_quantile(0.95,
  sum(rate(fluidmcp_request_duration_seconds_bucket[5m])) by (le, method)
)

# Compare P50 vs P95 (large gap indicates outliers)
histogram_quantile(0.50, sum(rate(fluidmcp_request_duration_seconds_bucket[5m])) by (le))
histogram_quantile(0.95, sum(rate(fluidmcp_request_duration_seconds_bucket[5m])) by (le))
```

**Memory Issues:**
```promql
# Total GPU memory across all GPUs
sum(fluidmcp_gpu_memory_bytes{server_id="your-server"}) by (server_id)

# Utilization ratio trend
fluidmcp_gpu_memory_utilization_ratio{server_id="your-server"}
```

### 5. Cost Optimization

**Reduce Metric Cardinality:**
- Avoid high-cardinality labels (e.g., user_id, request_id)
- Use recording rules for expensive queries
- Set retention policies based on importance

**Recording Rules:**
Create `recording_rules.yml`:
```yaml
groups:
  - name: fluidmcp_recording
    interval: 60s
    rules:
      # Pre-compute request rate
      - record: fluidmcp:requests:rate1m
        expr: sum(rate(fluidmcp_requests_total[1m])) by (server_id)

      # Pre-compute P95 latency
      - record: fluidmcp:latency:p95_5m
        expr: histogram_quantile(0.95, sum(rate(fluidmcp_request_duration_seconds_bucket[5m])) by (le, server_id))
```

## Troubleshooting

### Metrics Not Showing Up

1. **Check endpoint is accessible:**
   ```bash
   curl http://localhost:8099/metrics
   ```

2. **Verify Prometheus scrape config:**
   - Check `prometheus.yml` has correct target
   - Ensure port 8099 is not firewalled

3. **Check Prometheus logs:**
   ```bash
   # Look for scrape errors
   tail -f /var/log/prometheus/prometheus.log
   ```

### Missing Labels

If labels are missing from metrics:
1. Ensure server_id is correctly set when creating MetricsCollector
2. Check that labels are provided when calling metric methods
3. Verify label values are not empty strings

### High Memory Usage

If Prometheus memory usage is high:
1. Reduce metric cardinality (fewer unique label combinations)
2. Decrease retention period
3. Use recording rules for complex queries
4. Consider remote storage

### Stale Metrics

If metrics show stale data:
1. Check FluidMCP server is still running
2. Verify Prometheus scrape_interval matches expectations
3. Look for scrape timeout errors in Prometheus

## API Integration

### Programmatic Metrics Access

You can query metrics programmatically:

```python
import requests

# Get all metrics
response = requests.get("http://localhost:8099/metrics")
print(response.text)

# Parse with prometheus_client
from prometheus_client.parser import text_string_to_metric_families

for family in text_string_to_metric_families(response.text):
    print(f"Metric: {family.name}")
    for sample in family.samples:
        print(f"  {sample.name}{sample.labels} = {sample.value}")
```

### Custom Metrics

To add custom metrics to your FluidMCP deployment, extend the metrics module:

```python
from fluidmcp.cli.services.metrics import get_registry, Counter

# Register custom metric
registry = get_registry()
my_custom_metric = Counter(
    "my_custom_metric_total",
    "Description of my metric",
    labels=["label1", "label2"]
)
registry.register(my_custom_metric)

# Use it
my_custom_metric.inc({"label1": "value1", "label2": "value2"})
```

## Further Reading

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [FluidMCP GitHub](https://github.com/yourusername/fluidmcp)
