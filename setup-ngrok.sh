#!/bin/bash

echo "🔐 Setting up HTTPS tunnel with ngrok"
echo "======================================"
echo ""

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo "📥 Installing ngrok..."

    # Download ngrok
    curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | \
      sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && \
      echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | \
      sudo tee /etc/apt/sources.list.d/ngrok.list && \
      sudo apt update && sudo apt install ngrok

    echo "✅ ngrok installed"
    echo ""
fi

echo "🚀 Starting ngrok tunnel on port 8099..."
echo ""
echo "This will create an HTTPS URL for your FluidMCP server."
echo "Copy the HTTPS URL and use it in Auth0 configuration."
echo ""
echo "Press Ctrl+C to stop ngrok when done."
echo ""

# Start ngrok
ngrok http 8099
