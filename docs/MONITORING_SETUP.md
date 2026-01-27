# FluidMCP Monitoring Setup Guide

A step-by-step guide to set up Prometheus and Grafana for monitoring your FluidMCP servers.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Setup](#detailed-setup)
  - [1. Start FluidMCP with Metrics](#1-start-fluidmcp-with-metrics)
  - [2. Install and Configure Prometheus](#2-install-and-configure-prometheus)
  - [3. Install and Configure Grafana](#3-install-and-configure-grafana)
  - [4. Import the Dashboard](#4-import-the-dashboard)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)
- [Next Steps](#next-steps)

---

## Overview

FluidMCP exposes Prometheus-compatible metrics at the `/metrics` endpoint. This guide shows you how to:

1. Enable metrics collection in FluidMCP
2. Set up Prometheus to scrape metrics
3. Set up Grafana to visualize metrics
4. Import the pre-built dashboard

**Architecture:**
```
FluidMCP Server → Prometheus → Grafana
   :8099/metrics    :9090        :3000
```

---

## Prerequisites

Before starting, ensure you have:

- ✅ FluidMCP >= 0.1.0 installed (`pip install fluidmcp` or `pip install -e .`)
- ✅ Docker >= 20.10 (recommended) OR manual installation of Prometheus & Grafana
  - Prometheus >= 2.30
  - Grafana >= 8.0
- ✅ A FluidMCP configuration file (e.g., `examples/sample-config.json`)
- ✅ Python >= 3.9 (for FluidMCP)

---

## Quick Start

**Option 1: Docker (Recommended)**

```bash
# 1. Start FluidMCP
fluidmcp run examples/sample-config.json --file --start-server

# 2. Start Prometheus (with host network access)
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  --add-host=host.docker.internal:host-gateway \
  -v $(pwd)/examples/prometheus-config.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:latest

# 3. Start Grafana
docker run -d \
  --name grafana \
  -p 3000:3000 \
  grafana/grafana:latest

# 4. Access services
# - FluidMCP metrics: http://localhost:8099/metrics
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3000 (admin/admin - CHANGE PASSWORD!)
```

**Important Notes**:
- The `--add-host=host.docker.internal:host-gateway` flag allows Prometheus running in Docker to access FluidMCP on the host machine. This works on all platforms (Linux, macOS, Windows).
- **Security**: Change the Grafana default password (`admin/admin`) immediately after first login.
- **Windows users**: If using cmd.exe, replace `$(pwd)` with the absolute path to your config file.

**Option 2: Manual Installation**

Follow the [Detailed Setup](#detailed-setup) section below.

---

## Detailed Setup

### 1. Start FluidMCP with Metrics

FluidMCP automatically exposes metrics when you start the server:

```bash
# Run with a configuration file
fluidmcp run examples/sample-config.json --file --start-server

# Or run all installed servers
fluidmcp run all --start-server
```

**Verify metrics endpoint:**
```bash
curl http://localhost:8099/metrics
```

You should see Prometheus-formatted metrics like:
```
# HELP fluidmcp_requests_total Total number of requests processed
# TYPE fluidmcp_requests_total counter
fluidmcp_requests_total{server_id="filesystem",method="tools/list",status="success"} 5.0
...
```

---

### 2. Install and Configure Prometheus

#### Option A: Docker (Recommended)

```bash
# 1. Copy the example Prometheus config
cp examples/prometheus-config.yml /tmp/prometheus.yml

# 2. Update the config if needed (FluidMCP server address)
# The default config scrapes http://host.docker.internal:8099/metrics

# 3. Run Prometheus
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v /tmp/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:latest
```

#### Option B: Manual Installation

**On macOS:**
```bash
brew install prometheus
```

**On Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install prometheus
```

**Configuration:**

1. Copy the example config:
   ```bash
   cp examples/prometheus-config.yml /etc/prometheus/prometheus.yml
   ```

2. Update `targets` in the config if your FluidMCP server is not on `localhost:8099`:
   ```yaml
   scrape_configs:
     - job_name: 'fluidmcp'
       static_configs:
         - targets: ['your-server:8099']  # Update this
   ```

3. Start Prometheus:
   ```bash
   prometheus --config.file=/etc/prometheus/prometheus.yml
   ```

**Verify Prometheus:**

1. Open http://localhost:9090
2. Go to **Status → Targets**
3. Verify `fluidmcp` target is **UP** (green)

---

### 3. Install and Configure Grafana

#### Option A: Docker (Recommended)

```bash
docker run -d \
  --name grafana \
  -p 3000:3000 \
  grafana/grafana:latest
```

#### Option B: Manual Installation

**On macOS:**
```bash
brew install grafana
brew services start grafana
```

**On Ubuntu/Debian:**
```bash
sudo apt-get install -y software-properties-common
sudo add-apt-repository "deb https://packages.grafana.com/oss/deb stable main"
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
sudo apt-get update
sudo apt-get install grafana
sudo systemctl start grafana-server
```

**Initial Setup:**

1. Open http://localhost:3000
2. Login with default credentials:
   - Username: `admin`
   - Password: `admin`
3. Change the password when prompted

**Add Prometheus as Data Source:**

1. Click **⚙️ → Data Sources**
2. Click **Add data source**
3. Select **Prometheus**
4. Configure:
   - **Name:** `Prometheus`
   - **URL:** `http://localhost:9090` (or `http://prometheus:9090` if using Docker)
   - Leave other settings as default
5. Click **Save & Test**
6. Verify "Data source is working" message appears

---

### 4. Import the Dashboard

#### Import Pre-Built Dashboard

1. In Grafana, click **+ → Import**
2. Click **Upload JSON file**
3. Select `examples/grafana-dashboard.json`
4. Configure:
   - **Name:** FluidMCP Server Monitoring (or customize)
   - **Folder:** General (or create a new folder)
   - **Prometheus:** Select the Prometheus data source you created
5. Click **Import**

#### Dashboard Panels

The dashboard includes:

**📊 Overview Row:**
- Request Rate (req/s)
- Error Rate (%)
- Active Requests
- Server Status

**⏱️ Performance Row:**
- Request Latency (P50/P95/P99)
- Request Duration Heatmap

**🔧 Server Health Row:**
- Server Uptime
- Restart Count
- Health Check Failures

**💾 Resource Usage Row:**
- GPU Memory Usage
- GPU Memory Utilization

**🔄 Streaming Metrics Row:**
- Active Streams
- Stream Completion Status

**🛠️ Tool Execution Row:**
- Tool Call Rate
- Tool Execution Duration

---

## Verification

### 1. Verify Metrics Collection

**Check FluidMCP metrics endpoint:**
```bash
curl http://localhost:8099/metrics | grep fluidmcp_requests_total
```

Expected output:
```
fluidmcp_requests_total{server_id="filesystem",method="tools/list",status="success"} 10.0
```

### 2. Verify Prometheus Scraping

**Query Prometheus:**
```bash
curl -G http://localhost:9090/api/v1/query \
  --data-urlencode 'query=fluidmcp_requests_total' | jq
```

Or open http://localhost:9090/graph and run:
```
fluidmcp_requests_total
```

### 3. Verify Grafana Dashboard

1. Open http://localhost:3000
2. Go to **Dashboards → FluidMCP Server Monitoring**
3. Verify panels are showing data
4. If no data appears, check:
   - FluidMCP server is running
   - Prometheus target is UP
   - Prometheus data source is configured correctly

### 4. Generate Test Traffic

Run the manual test to generate metrics:
```bash
cd /path/to/fluidmcp
python tests/manual/test_metrics.py
```

This will:
- Make requests to FluidMCP
- Generate metrics data
- Verify metrics are being collected

Expected output:
```
=== Test 1: Metrics Endpoint Accessibility ===
✓ /metrics endpoint is accessible

=== Test 2: Prometheus Format Validation ===
✓ Metrics follow Prometheus exposition format
...
```

---

## Troubleshooting

### Metrics endpoint returns 404

**Problem:** `curl http://localhost:8099/metrics` returns 404

**Solution:**
- Verify FluidMCP server is running: `curl http://localhost:8099/health`
- Check server logs for errors
- Ensure you're using the correct port (default: 8099)

### Prometheus target is DOWN

**Problem:** Prometheus shows FluidMCP target as DOWN (red)

**Solution:**
1. Check FluidMCP is accessible from Prometheus:
   ```bash
   # From host
   curl http://localhost:8099/metrics

   # From Docker (if Prometheus is in Docker)
   curl http://host.docker.internal:8099/metrics
   ```

2. Update `prometheus.yml` target if needed:
   ```yaml
   targets: ['host.docker.internal:8099']  # For Docker
   # OR
   targets: ['localhost:8099']  # For local install
   ```

3. Restart Prometheus after config changes

### Grafana shows "No data"

**Problem:** Dashboard panels show "No data"

**Solutions:**

1. **Check time range:**
   - Click the time picker (top right)
   - Select "Last 5 minutes" or "Last 15 minutes"

2. **Verify Prometheus data source:**
   - Go to **⚙️ → Data Sources → Prometheus**
   - Click **Test** button
   - Should show "Data source is working"

3. **Check query syntax:**
   - Click panel title → **Edit**
   - Verify query uses correct metric names
   - Run query in Prometheus first to verify it works

4. **Generate traffic:**
   ```bash
   # Generate some metrics data
   curl -X POST http://localhost:8099/api/servers
   python tests/manual/test_metrics.py
   ```

### Docker networking issues

**Problem:** Prometheus can't reach FluidMCP when both are in Docker

**Solution:**
Use Docker networking:
```bash
# Create a network
docker network create monitoring

# Run FluidMCP in the network
docker run --network monitoring --name fluidmcp ...

# Run Prometheus in the network
docker run --network monitoring --name prometheus ...

# Update prometheus.yml
targets: ['fluidmcp:8099']
```

---

## Next Steps

### 1. Set Up Alerts

Create alerts for critical conditions:

**Example: High Error Rate Alert**

In Grafana:
1. Edit a panel (e.g., "Error Rate")
2. Go to **Alert** tab
3. Create alert rule:
   ```
   WHEN avg() OF query(A, 5m, now) IS ABOVE 5
   ```
4. Configure notification channel (Slack, Email, etc.)

**Example: Server Down Alert**

PromQL:
```promql
fluidmcp_server_status{server_id="your-server"} == 0
```

### 2. Customize Dashboard

- **Add custom panels:** Click **Add Panel** → Create your own visualizations
- **Filter by server:** Use template variables for multi-server setups
- **Create folders:** Organize dashboards by environment (dev, prod, staging)

### 3. Long-Term Storage

For production deployments, consider:
- **Prometheus remote storage** (e.g., Thanos, Cortex)
- **Increase retention:** Default is 15 days
  ```bash
  prometheus --storage.tsdb.retention.time=90d
  ```

### 4. Advanced Monitoring

Explore the comprehensive monitoring documentation:
```bash
# Read the full monitoring guide
cat docs/MONITORING.md
```

Topics covered:
- All available metrics
- Advanced PromQL queries
- Performance tuning
- Best practices
- GPU monitoring integration (optional)

---

## Reference

### Useful Links

- **FluidMCP Docs:** [docs/MONITORING.md](./MONITORING.md)
- **Prometheus Docs:** https://prometheus.io/docs/
- **Grafana Docs:** https://grafana.com/docs/
- **PromQL Guide:** https://prometheus.io/docs/prometheus/latest/querying/basics/

### Default Ports

| Service | Port | Endpoint |
|---------|------|----------|
| FluidMCP | 8099 | http://localhost:8099 |
| FluidMCP Health | 8099 | http://localhost:8099/health |
| FluidMCP Metrics | 8099 | http://localhost:8099/metrics |
| Prometheus | 9090 | http://localhost:9090 |
| Grafana | 3000 | http://localhost:3000 |

### API Endpoints

#### Health Check Endpoint

**GET** `/health`

Returns the health status of FluidMCP server.

**Response Schema**:
```json
{
  "status": "healthy",
  "servers": 2,
  "running_servers": 1
}
```

**Field Descriptions**:
- `status` (string): Health status - "healthy", "degraded", or "unhealthy"
- `servers` (integer): Total number of registered servers
- `running_servers` (integer): Number of currently running servers

**Status Codes**:
- `200 OK` - Server is healthy (at least one server running)
- `503 Service Unavailable` - Server is degraded or unhealthy

**Example**:
```bash
curl http://localhost:8099/health
# Response: {"status":"healthy","servers":2,"running_servers":1}
```

### Quick Commands

```bash
# Check FluidMCP health
curl http://localhost:8099/health

# Check FluidMCP metrics
curl http://localhost:8099/metrics

# Query Prometheus
curl 'http://localhost:9090/api/v1/query?query=fluidmcp_requests_total'

# Test metrics collection (if test file is available in your branch)
python tests/manual/test_metrics.py
```

**Note**: `tests/manual/test_metrics.py` is part of the monitoring metrics feature. If it's not available in your branch, use the curl commands above for manual testing.

---

## Support

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review [docs/MONITORING.md](./MONITORING.md) for detailed information
3. Open an issue: https://github.com/Fluid-AI/fluidmcp/issues

---

**🎉 Congratulations!** You now have a complete monitoring setup for FluidMCP.
