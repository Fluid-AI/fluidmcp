#!/bin/bash
# Quick test script for video generation with automatic result display
#

# Check for jq
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed."
    echo "Install with: sudo apt-get install jq (or brew install jq on Mac)"
    exit 1
fi
# Usage: bash examples/test-video-generation.sh

set -e

BASE_URL="${FLUIDMCP_URL:-http://localhost:8099}"

echo "========================================"
echo "Testing Video Generation"
echo "========================================"
echo ""

# Test what you want to generate
read -p "What do you want to generate? (image/video/animate): " TYPE

case $TYPE in
  image)
    read -p "Enter prompt: " PROMPT
    echo ""
    echo "Generating image..."
    RESPONSE=$(curl -s -X POST "${BASE_URL}/api/llm/v1/generate/image" \
      -H "Content-Type: application/json" \
      -d "{\"model\": \"flux-image\", \"prompt\": \"${PROMPT}\"}")
    ;;

  video)
    read -p "Enter prompt: " PROMPT
    echo ""
    echo "Generating video (this takes 1-5 minutes)..."
    RESPONSE=$(curl -s -X POST "${BASE_URL}/api/llm/v1/generate/video" \
      -H "Content-Type: application/json" \
      -d "{\"model\": \"animatediff-video\", \"prompt\": \"${PROMPT}\"}")
    ;;

  animate)
    read -p "Enter image URL: " IMAGE_URL
    echo ""
    echo "Animating image..."
    RESPONSE=$(curl -s -X POST "${BASE_URL}/api/llm/v1/animate" \
      -H "Content-Type: application/json" \
      -d "{\"model\": \"stable-video\", \"image_url\": \"${IMAGE_URL}\"}")
    ;;

  *)
    echo "Invalid choice. Use: image, video, or animate"
    exit 1
    ;;
esac

# Extract prediction ID
PREDICTION_ID=$(echo "$RESPONSE" | jq -r '.id')
echo "Prediction ID: $PREDICTION_ID"
echo ""

# Poll for completion
echo "Polling for completion..."
for i in {1..60}; do
  sleep 3
  STATUS_RESPONSE=$(curl -s "${BASE_URL}/api/llm/predictions/${PREDICTION_ID}")
  STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')

  echo "  Check $i/60: Status = $STATUS"

  if [ "$STATUS" = "succeeded" ]; then
    echo ""
    echo "✅ Generation completed!"
    echo ""

    # Extract output URLs
    OUTPUT=$(echo "$STATUS_RESPONSE" | jq -r '.output[]')

    echo "========================================"
    echo "RESULT URLs:"
    echo "========================================"
    echo "$OUTPUT"
    echo ""
    echo "📋 Copy the URL above and paste in your browser to view"
    echo ""

    # Try to open in browser automatically
    if command -v xdg-open &> /dev/null; then
      echo "Opening in browser..."
      xdg-open "$OUTPUT"
    elif command -v open &> /dev/null; then
      echo "Opening in browser..."
      open "$OUTPUT"
    else
      echo "💡 Manually copy the URL above and paste in your browser"
    fi

    exit 0
  elif [ "$STATUS" = "failed" ]; then
    echo ""
    echo "❌ Generation failed!"
    echo "$STATUS_RESPONSE" | jq '.error'
    exit 1
  fi
done

echo ""
echo "⏱️  Timeout reached. Check status manually:"
echo "curl ${BASE_URL}/api/llm/predictions/${PREDICTION_ID}"
