#!/bin/bash
# vLLM Omni API Examples - Vision, Image Generation, Video Generation
#
# Prerequisites:
# 1. FluidMCP running with vllm-omni-complete.json config
# 2. vLLM server running with vision model (e.g., LLaVA)
# 3. REPLICATE_API_TOKEN set in environment
#
# Usage: bash examples/omni-api-examples.sh

set -e

# Check for jq
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed."
    echo "Install with: sudo apt-get install jq (or brew install jq on Mac)"
    exit 1
fi

BASE_URL="${FLUIDMCP_URL:-http://localhost:8099}"
AUTH_TOKEN="${FLUIDMCP_TOKEN:-}"

# Build auth header if token is provided
AUTH_HEADER=""
if [ -n "$AUTH_TOKEN" ]; then
  AUTH_HEADER="-H \"Authorization: Bearer ${AUTH_TOKEN}\""
fi

echo "==================================================================="
echo "vLLM Omni API Examples"
echo "==================================================================="
echo ""
echo "Note: If running in secure mode, set FLUIDMCP_TOKEN environment variable"
echo ""

# ============================================================================
# 1. Vision: Image Understanding (vLLM)
# ============================================================================
echo "1. Vision: Image Understanding (vLLM)"
echo "-------------------------------------------------------------------"
curl -X POST "${BASE_URL}/api/llm/llava/v1/chat/completions" \
  -H "Content-Type: application/json" \
  ${AUTH_HEADER} \
  -d '{
    "model": "llava",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "Describe what you see in this image"},
        {"type": "image_url", "image_url": {"url": "https://picsum.photos/800/600"}}
      ]
    }],
    "max_tokens": 200
  }'
echo -e "\n"

# ============================================================================
# 2. Image Generation: Text-to-Image (Replicate)
# ============================================================================
echo ""
echo "2. Image Generation: Text-to-Image (Replicate FLUX)"
echo "-------------------------------------------------------------------"
PREDICTION=$(curl -s -X POST "${BASE_URL}/api/llm/v1/generate/image" \
  -H "Content-Type: application/json" \
  ${AUTH_HEADER} \
  -d '{
    "model": "flux-image",
    "prompt": "A serene Japanese garden with cherry blossoms in full bloom, golden hour lighting",
    "aspect_ratio": "16:9",
    "output_format": "png"
  }')
echo "$PREDICTION"
IMAGE_PREDICTION_ID=$(echo "$PREDICTION" | jq -r '.id')
echo "Image generation started. Prediction ID: $IMAGE_PREDICTION_ID"
echo -e "\n"

# ============================================================================
# 3. Video Generation: Text-to-Video (Replicate)
# ============================================================================
echo ""
echo "3. Video Generation: Text-to-Video (Replicate AnimateDiff)"
echo "-------------------------------------------------------------------"
PREDICTION=$(curl -s -X POST "${BASE_URL}/api/llm/v1/generate/video" \
  -H "Content-Type: application/json" \
  ${AUTH_HEADER} \
  -d '{
    "model": "animatediff-video",
    "prompt": "A cat walking in the rain",
    "width": 512,
    "height": 512,
    "num_frames": 16
  }')
echo "$PREDICTION"
VIDEO_PREDICTION_ID=$(echo "$PREDICTION" | jq -r '.id')
echo "Video generation started. Prediction ID: $VIDEO_PREDICTION_ID"
echo -e "\n"

# ============================================================================
# 4. Image Animation: Image-to-Video (Replicate)
# ============================================================================
echo ""
echo "4. Image Animation: Image-to-Video (Replicate Stable Video)"
echo "-------------------------------------------------------------------"
PREDICTION=$(curl -s -X POST "${BASE_URL}/api/llm/v1/animate" \
  -H "Content-Type: application/json" \
  ${AUTH_HEADER} \
  -d '{
    "model": "stable-video",
    "image_url": "https://picsum.photos/1024/576",
    "motion_bucket_id": 127,
    "fps": 24
  }')
echo "$PREDICTION"
ANIMATION_PREDICTION_ID=$(echo "$PREDICTION" | jq -r '.id')
echo "Image animation started. Prediction ID: $ANIMATION_PREDICTION_ID"
echo -e "\n"

# ============================================================================
# 5. Check Generation Status (Polling)
# ============================================================================
echo ""
echo "5. Polling for Completion"
echo "-------------------------------------------------------------------"
echo "Waiting for image generation to complete..."
for i in {1..30}; do
  sleep 2
  STATUS=$(curl -s "${BASE_URL}/api/llm/predictions/${IMAGE_PREDICTION_ID}" ${AUTH_HEADER})
  CURRENT_STATUS=$(echo "$STATUS" | jq -r '.status')
  echo "  Attempt $i/30: Status = $CURRENT_STATUS"

  if [ "$CURRENT_STATUS" = "succeeded" ]; then
    echo ""
    echo "Image generation completed!"
    echo "$STATUS" | jq '.output'
    break
  elif [ "$CURRENT_STATUS" = "failed" ]; then
    echo "Image generation failed:"
    echo "$STATUS" | jq '.error'
    break
  fi
done
echo ""

echo "==================================================================="
echo "Examples Complete"
echo "==================================================================="
echo ""
echo "Note: Video and animation take 30s-5min. Check status manually:"
echo "  curl ${BASE_URL}/api/llm/predictions/${VIDEO_PREDICTION_ID}"
echo "  curl ${BASE_URL}/api/llm/predictions/${ANIMATION_PREDICTION_ID}"
echo ""
