#!/bin/bash

# Start HTML UI MCP Server in HTTP Streaming Mode
# This runs the server with direct HTTP access on port 8090

set -e

echo "🚀 Starting HTML UI Streaming Server..."
echo ""
echo "  📍 Server: http://localhost:8090"
echo "  🌊 Streaming: POST http://localhost:8090/stream-html"
echo "  ❤️  Health: GET http://localhost:8090/health"
echo ""
echo "  📖 Demo: Open streaming-demo.html in your browser"
echo "     Then update the fetch URL to localhost:8090"
echo ""
echo "Press Ctrl+C to stop"
echo ""

cd "$(dirname "$0")"
python3 server.py --http-only
