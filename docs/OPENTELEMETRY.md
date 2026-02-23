# OpenTelemetry Distributed Tracing

FluidMCP supports distributed tracing via OpenTelemetry with **OTLP HTTP exporter**, compatible with Jaeger, Tempo, and other OTLP-compatible backends.

## Quick Start (GitHub Codespaces)

### 1. Start Jaeger

Use the included helper script:

```bash
./scripts/start-jaeger-codespaces.sh
```

Or manually:

```bash
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

### 2. Configure FluidMCP

```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER=jaeger
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
export OTEL_SERVICE_NAME=fluidmcp
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Start FluidMCP

```bash
fmcp serve --port 8099
```

Look for these log messages:
```
✓ OTLP exporter configured: http://localhost:4318/v1/traces
✓ OpenTelemetry initialized: service=fluidmcp, version=2.0.0, exporters=[otlp(...)]
✓ FastAPI instrumented with OpenTelemetry
```

### 5. Generate Traffic

```bash
# Health check
curl http://localhost:8099/health

# MCP request (if server configured)
curl -X POST http://localhost:8099/{server_name}/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

### 6. View Traces in Jaeger

1. Open `http://localhost:16686` (or your Codespaces forwarded URL)
2. Select Service: **fluidmcp**
3. Click **Find Traces**
4. Browse HTTP requests and MCP operations

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `true` | Set to `false` to disable tracing |
| `OTEL_SERVICE_NAME` | `fluidmcp` | Service name shown in Jaeger |
| `OTEL_SERVICE_VERSION` | `2.0.0` | Service version |
| `OTEL_EXPORTER` | `jaeger` | Exporter type: `jaeger`, `console`, or `both` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318/v1/traces` | OTLP HTTP endpoint URL |

## What Gets Traced?

### Automatic HTTP Tracing

FastAPI instrumentation automatically traces:
- HTTP request method and path
- HTTP status codes
- Request duration
- Errors and exceptions

### Explicit MCP Operation Tracing

FluidMCP creates explicit spans for MCP operations:
- `mcp.tools/list` - List available tools
- `mcp.tools/call` - Execute a tool
- `mcp.resources/list` - List resources
- `mcp.prompts/list` - List prompts

Each span includes:
- `mcp.server_id` - Which MCP server handled the request
- `mcp.operation` - JSON-RPC method name
- `request_id` - JSON-RPC request ID
- Error details (if operation failed)

## Exporter Options

### OTLP HTTP (Recommended for Codespaces)

**Works with:** Jaeger, Grafana Tempo, any OTLP collector

```bash
export OTEL_EXPORTER=jaeger
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

**Advantages:**
- Uses HTTP (works in restricted networks)
- Industry standard (OpenTelemetry standard)
- Compatible with modern observability platforms

### Console Exporter (Debugging)

Prints traces to console output:

```bash
export OTEL_EXPORTER=console
```

**Advantages:**
- No external dependencies
- Useful for development/debugging
- See traces immediately in logs

### Both Exporters

Export to both Jaeger and console:

```bash
export OTEL_EXPORTER=both
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

## Jaeger Ports

When running Jaeger with OTLP:

| Port | Protocol | Purpose |
|------|----------|---------|
| `16686` | HTTP | Jaeger UI (web interface) |
| `4318` | HTTP | OTLP HTTP collector (FluidMCP uses this) |
| `14250` | gRPC | Jaeger gRPC collector (optional) |

## Architecture

### Why OTLP Instead of Jaeger Thrift?

**Old approach (Phase 1):** Jaeger Thrift exporter
- Used UDP port 6831
- Blocked in GitHub Codespaces
- Deprecated by OpenTelemetry

**New approach (Phase 2):** OTLP HTTP exporter
- Uses HTTP port 4318
- Works in restricted networks
- Modern standard (future-proof)
- Compatible with more backends

### Trace Flow

```
FluidMCP Request
    ↓
FastAPI HTTP span (automatic)
    ↓
MCP operation span (explicit)
    ↓
OTLP HTTP exporter
    ↓
Jaeger collector (port 4318)
    ↓
Jaeger storage
    ↓
Jaeger UI (port 16686)
```

## Advanced Configuration

### Custom OTLP Endpoint

Point to a different OTLP collector:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318/v1/traces
```

### Grafana Tempo

FluidMCP works with Grafana Tempo out of the box:

```bash
# Start Tempo
docker run -d --name tempo \
  -p 3200:3200 \
  -p 4318:4318 \
  grafana/tempo:latest

# Configure FluidMCP
export OTEL_EXPORTER=jaeger
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

### Production Deployment

For production, use a dedicated OTLP collector:

```bash
# OpenTelemetry Collector
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces

# Grafana Cloud
export OTEL_EXPORTER_OTLP_ENDPOINT=https://tempo-prod-01-prod-us-central-0.grafana.net/v1/traces
```

## Troubleshooting

### Issue: Jaeger shows "Service (0)" with no traces

**Causes:**
1. OTLP endpoint not reachable
2. FluidMCP not configured correctly
3. Jaeger OTLP not enabled

**Solution:**

```bash
# 1. Verify Jaeger is running with OTLP
docker ps | grep jaeger
docker logs jaeger | grep OTLP

# 2. Test OTLP endpoint connectivity
curl http://localhost:4318/

# 3. Check FluidMCP logs for OTLP initialization
fmcp serve --port 8099 2>&1 | grep -i otlp

# Expected: "✓ OTLP exporter configured: http://localhost:4318/v1/traces"
# If error: "❌ OTLP endpoint ... unreachable"

# 4. Restart Jaeger with OTLP support
./scripts/start-jaeger-codespaces.sh

# 5. Verify environment variables
env | grep OTEL
```

### Issue: ImportError for OTLP exporter

**Error:**
```
❌ OTLP exporter not installed: pip install opentelemetry-exporter-otlp-proto-http
```

**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: Traces not appearing immediately

**Cause:** Batch span processor waits until buffer fills or timeout (default: 5 seconds)

**Solution:** Generate more traffic or wait a few seconds:

```bash
# Generate multiple requests
for i in {1..10}; do
  curl http://localhost:8099/health
done

# Wait 5 seconds, then check Jaeger UI
sleep 5
```

### Issue: Console exporter not showing traces

**Cause:** Console exporter only prints when spans are flushed

**Solution:** Generate traffic and wait for batch export:

```bash
export OTEL_EXPORTER=console
fmcp serve --port 8099

# In another terminal
curl http://localhost:8099/health

# Wait for span export (5-10 seconds)
```

### Issue: UDP port 6831 errors (old Jaeger Thrift)

**Error:**
```
⚠️  Failed to initialize Jaeger exporter: [Errno 111] Connection refused
```

**Cause:** Old Jaeger Thrift exporter configuration (deprecated)

**Solution:** Use OTLP HTTP instead (already fixed in this version):

```bash
# Verify requirements.txt has OTLP, not Jaeger Thrift
grep opentelemetry requirements.txt

# Should see:
# opentelemetry-exporter-otlp-proto-http==1.21.0

# Should NOT see:
# opentelemetry-exporter-jaeger
```

## Disabling Tracing

To disable OpenTelemetry:

```bash
export OTEL_ENABLED=false
fmcp serve --port 8099
```

Log message:
```
OpenTelemetry disabled via OTEL_ENABLED=false
```

## Performance Impact

OpenTelemetry tracing has minimal performance impact:

- **Overhead:** ~1-2ms per request (instrumentation + span creation)
- **Memory:** ~100KB per 1000 spans (before batch export)
- **Network:** ~1-2KB per span (OTLP HTTP payload)

Batch span processor exports asynchronously, so:
- No blocking on request path
- Traces buffered and sent in background
- Automatic retry on failure

## Security Considerations

### Network Exposure

- Jaeger UI (port 16686) exposes all traces
- Restrict access in production:

```bash
# Bind Jaeger UI to localhost only
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 127.0.0.1:16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

### Sensitive Data in Spans

FluidMCP automatically redacts sensitive data:
- Credentials not included in span attributes
- Request bodies not logged (only metadata)
- Use custom span attributes carefully

## Example Traces

### HTTP Request Trace

```
Span: GET /health
├── Duration: 12ms
├── Status: 200 OK
└── Attributes:
    ├── http.method: GET
    ├── http.url: /health
    ├── http.status_code: 200
    └── net.host.name: localhost
```

### MCP Operation Trace

```
Span: mcp.tools/list
├── Duration: 145ms
├── Status: OK
└── Attributes:
    ├── mcp.server_id: filesystem
    ├── mcp.operation: tools/list
    ├── request_id: 1
    └── Child of: POST /{server_name}/mcp
```

### Error Trace

```
Span: mcp.tools/call
├── Duration: 52ms
├── Status: ERROR
├── Exception: FileNotFoundError: /tmp/missing.txt
└── Attributes:
    ├── mcp.server_id: filesystem
    ├── mcp.operation: tools/call
    ├── request_id: 2
    ├── error.type: FileNotFoundError
    └── error.message: /tmp/missing.txt
```

## Further Reading

- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/languages/python/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)
- [FluidMCP Metrics Documentation](./OBSERVABILITY.md)

## Implementation Files

- [fluidmcp/cli/otel.py](../fluidmcp/cli/otel.py) - OpenTelemetry initialization
- [fluidmcp/cli/services/tracing.py](../fluidmcp/cli/services/tracing.py) - MCP operation tracing helpers
- [fluidmcp/cli/services/package_launcher.py](../fluidmcp/cli/services/package_launcher.py) - MCP request handlers with tracing
- [fluidmcp/cli/server.py](../fluidmcp/cli/server.py) - FastAPI app instrumentation
- [scripts/start-jaeger-codespaces.sh](../scripts/start-jaeger-codespaces.sh) - Helper script for Jaeger setup
