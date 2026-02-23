#!/bin/bash
# Start Jaeger with OTLP support for GitHub Codespaces
#
# This script starts Jaeger with OTLP HTTP collector enabled,
# which is required for FluidMCP tracing in GitHub Codespaces.
#
# Jaeger Thrift (UDP port 6831) is blocked in Codespaces,
# so we use OTLP HTTP (port 4318) instead.

set -e

echo "========================================="
echo "Starting Jaeger with OTLP HTTP support"
echo "========================================="
echo ""

# Stop and remove existing Jaeger container if it exists
if docker ps -a --format '{{.Names}}' | grep -q '^jaeger$'; then
    echo "Stopping existing Jaeger container..."
    docker stop jaeger 2>/dev/null || true
    docker rm jaeger 2>/dev/null || true
    echo "✓ Cleaned up existing container"
    echo ""
fi

# Start Jaeger with OTLP enabled
echo "Starting new Jaeger container with OTLP support..."
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4318:4318 \
  -p 14250:14250 \
  jaegertracing/all-in-one:latest

echo ""
echo "✓ Jaeger started successfully!"
echo ""
echo "========================================="
echo "Jaeger Endpoints"
echo "========================================="
echo "UI (Web):      http://localhost:16686"
echo "OTLP HTTP:     http://localhost:4318"
echo "gRPC:          http://localhost:14250"
echo ""
echo "========================================="
echo "Configure FluidMCP"
echo "========================================="
echo "Set these environment variables:"
echo ""
echo "  export OTEL_ENABLED=true"
echo "  export OTEL_EXPORTER=jaeger"
echo "  export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces"
echo "  export OTEL_SERVICE_NAME=fluidmcp"
echo ""
echo "Then start FluidMCP:"
echo "  fmcp serve --port 8099"
echo ""
echo "========================================="
echo ""
