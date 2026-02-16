# Manual Testing Guide - vLLM Omni Image & Video Generation

This guide shows you how to manually test the vLLM Omni image and video generation features.

## Prerequisites

1. **Get a Replicate API token**: https://replicate.com/account/api-tokens
2. **Set the token** in your environment:
   ```bash
   export REPLICATE_API_TOKEN="r8_your_token_here"
   ```

## Quick Test - Image Generation


**Note**: These examples assume secure mode is disabled for testing. If `FMCP_SECURE_MODE` is enabled,
add the authentication header: `-H "Authorization: Bearer $FMCP_BEARER_TOKEN"` to all curl commands.
### Step 1: Start FluidMCP Server

```bash
cd /workspaces/fluidmcp
fluidmcp run examples/vllm-omni-generation.json --file --start-server
```

Server starts on: **http://localhost:8099**

### Step 2: Generate an Image

Open a new terminal and run:

```bash
curl -X POST http://localhost:8099/api/llm/v1/generate/image \
  -H "Content-Type: application/json" \
  -d '{
    "model": "flux-image-gen",
    "prompt": "A beautiful sunset over mountains with cherry blossoms",
    "aspect_ratio": "16:9"
  }'
```

**Response** (save the `id`):
```json
{
  "id": "abc123xyz",
  "status": "starting"
}
```

### Step 3: Check Generation Status

```bash
PREDICTION_ID="abc123xyz"  # Use your actual ID from Step 2

curl http://localhost:8099/api/llm/predictions/$PREDICTION_ID
```

**Status meanings**:
- `"starting"` → Just queued
- `"processing"` → Generating (10-30 seconds)
- `"succeeded"` → ✅ Done!
- `"failed"` → ❌ Error

### Step 4: Get Your Image

When status is `"succeeded"`:
```json
{
  "id": "abc123xyz",
  "status": "succeeded",
  "output": [
    "https://replicate.delivery/pbxt/abc123/image.png"
  ]
}
```

**Copy the URL** and open it in your browser! 🎨

## Video Generation Test

```bash
# Generate video (takes 2-5 minutes)
curl -X POST http://localhost:8099/api/llm/v1/generate/video \
  -H "Content-Type: application/json" \
  -d '{
    "model": "animatediff-video",
    "prompt": "A panda playing guitar in the rain",
    "duration": 5
  }'

# Get prediction ID from response, then poll:
curl http://localhost:8099/api/llm/predictions/YOUR_PREDICTION_ID
```

Video URL will be in `output` when status is `"succeeded"`.

## Automated Demo Script

We have a complete demo script:

```bash
bash examples/omni-api-examples.sh
```

This automatically:
1. ✅ Generates an image
2. ✅ Starts a video generation
3. ✅ Starts an image animation
4. ✅ Polls for completion
5. ✅ Prints result URLs

## Swagger UI (Interactive Testing)

1. Open: **http://localhost:8099/docs**
2. Find: `/api/llm/{model_id}/generate/image`
3. Click: **"Try it out"**
4. Set `model_id`: `flux-image-gen`
5. Enter your prompt
6. Click: **"Execute"**
7. Copy the `prediction_id` from the response
8. Use `/api/llm/predictions/{prediction_id}` to check status

## Available Models

In `examples/vllm-omni-generation.json`:

| Model ID | Type | Description |
|----------|------|-------------|
| `flux-image-gen` | text-to-image | FLUX Schnell (fast, high-quality) |
| `stable-diffusion` | text-to-image | Stable Diffusion |
| `animatediff-video` | text-to-video | AnimateDiff Lightning (fast, short clips) |
| `stable-video` | image-to-video | Animate static images |

## Troubleshooting

### ❌ "No Replicate API token found"
```bash
# Check if token is set
echo $REPLICATE_API_TOKEN

# If not set:
export REPLICATE_API_TOKEN="r8_your_token_here"
```

### ❌ "Model does not support 'text-to-image' capability"
Make sure your config has:
```json
{
  "capabilities": ["text-to-image"]
}
```

### ⏱️ Status stuck on "processing"
- **Images**: Wait up to 2 minutes
- **Videos**: Wait up to 5 minutes
- Check Replicate dashboard: https://replicate.com/predictions

### 💰 Check Costs
- Image generation: ~$0.001-0.01 per image
- Video generation: ~$0.05-0.20 per video
- Monitor usage: https://replicate.com/account/billing

## Example Prompts

**Images**:
- "A serene Japanese garden with cherry blossoms in full bloom"
- "Cyberpunk city at night with neon lights reflecting on wet streets"
- "Oil painting of a mountain landscape in the style of Bob Ross"

**Videos**:
- "A cat walking through a cyberpunk city at night"
- "一只熊猫在雨中弹吉他" (A panda playing guitar in the rain - Chinese)
- "Ocean waves crashing on a beach at sunset"

## Next Steps

- See [VLLM_OMNI_IMPLEMENTATION_PLAN.md](VLLM_OMNI_IMPLEMENTATION_PLAN.md) for complete technical details
- Check [examples/omni-api-examples.sh](../examples/omni-api-examples.sh) for full automation
- Review [CLAUDE.md](../CLAUDE.md) for configuration options
