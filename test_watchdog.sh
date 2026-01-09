#!/bin/bash

# Test script for watchdog functionality

set -e

echo "=================================================="
echo "FluidMCP Watchdog Test Script"
echo "=================================================="
echo ""

# Create test directory
echo "1. Creating test directory..."
mkdir -p /tmp/test-directory
echo "✅ Test directory created: /tmp/test-directory"
echo ""

# Check if example config exists
if [ ! -f "examples/test-watchdog.json" ]; then
    echo "❌ Test config not found: examples/test-watchdog.json"
    exit 1
fi

echo "2. Test config found: examples/test-watchdog.json"
cat examples/test-watchdog.json
echo ""

echo "3. Starting FluidMCP with watchdog enabled..."
echo "   Command: fluidmcp run examples/test-watchdog.json --file --start-server --watchdog"
echo ""
echo "   Note: The server will start and monitor the filesystem MCP server."
echo "   To test auto-restart:"
echo "   - Open another terminal"
echo "   - Find the MCP process: ps aux | grep '@modelcontextprotocol'"
echo "   - Kill it: kill -9 <PID>"
echo "   - Watch the watchdog automatically restart it"
echo ""
echo "=================================================="
echo "Starting server... (Press Ctrl+C to stop)"
echo "=================================================="
echo ""

# Run FluidMCP with watchdog
fluidmcp run examples/test-watchdog.json --file --start-server --watchdog
