# Basic vLLM Omni (Multimodal) Support for FluidMCP

> **Implementation Note**: This document represents the original plan. In the final implementation, `tencent/hunyuan-video` was replaced with `lucataco/animatediff-lightning-4step` due to model availability on Replicate. See [examples/vllm-omni-complete.json](../examples/vllm-omni-complete.json) for the actual working configuration.

## Context

**Current State**: FluidMCP supports vLLM for text-only LLM inference.

**Problem**: Client needs video generation capabilities. Sir suggested this should be implemented as "basic vLLM Omni support" for multimodal models.

**User Requirements** (CLARIFIED):
- Basic support only 
- Enable vLLM Omni: multimodal models supporting vision, image generation, and video generation
- Support Chinese models (CogVideoX, Hunyuan Video)
- Keep implementation practical and lightweight

## What is vLLM Omni?

vLLM Omni refers to **multimodal model capabilities**:

**Currently Supported by vLLM**:
- ✅ Vision input: Accept text + image inputs (LLaVA, Qwen-VL, InternVL)
- ✅ Text output: Generate text descriptions of images

**NOT Supported by vLLM (Need Integration)**:
- ❌ Image generation: Text → image (requires Stable Diffusion, FLUX, etc.)
- ❌ Video generation: Text → video (requires CogVideoX, Hunyuan Video, etc.)

### Important Clarification: What "vLLM Omni" Means in FluidMCP

In this context, **vLLM Omni does NOT imply that vLLM itself performs image or video generation**.

Instead:
- **vLLM** is used for **text + vision-language models** (image understanding)
- **Image and video generation** are provided via **external generators** (Replicate)
- **FluidMCP** presents these capabilities under a **unified Omni interface**

This matches the industry reality:
- vLLM = inference engine for LLMs/VLMs
- Diffusion & video models = separate systems

The "Omni" designation refers to FluidMCP's platform-level capability to orchestrate multiple model types under a unified API, not to vLLM's native capabilities.

## Basic Support Scope

**What We'll Add**:
1. **Vision Models** (vLLM native): Configuration and docs for vision-language models
2. **Image Generation** (Replicate integration): Text-to-image via Replicate API
3. **Video Generation** (Replicate integration): Text-to-video, image-to-video via Replicate API
4. **Unified Configuration**: Use existing types (`"vllm"` and `"replicate"`) with `capabilities` metadata

**Implementation Strategy**:
- Vision: Use vLLM's existing OpenAI-compatible vision API (documentation only)
- Image/Video: Leverage Replicate API (lightweight client, already proven pattern)
- Config: Keep existing `"type": "vllm"` and `"type": "replicate"`, use `"capabilities"` to indicate functionality

**What We Won't Add** (out of scope for "basic"):
- Local video generation servers (requires A100 80GB+)
- Custom diffusion model hosting
- Complex model orchestration
- Video file storage infrastructure

## Recommended Architecture

**Hybrid Approach** (Best for "Basic Support"):
- **Vision** (input): Use vLLM natively → No code changes, just documentation
- **Image/Video** (generation): Use Replicate API → Reuse existing replicate_client.py patterns
- **Configuration**: Unified under clear model types

This leverages:
- ✅ vLLM's existing vision capabilities
- ✅ Replicate's proven integration (already in codebase)
- ✅ No heavy infrastructure for video generation
- ✅ Support for Chinese models (CogVideoX, Hunyuan on Replicate)

## Implementation Plan

### Part A: Vision Models (vLLM Native)

#### Phase 1: Configuration Support (Documentation Only)

**File**: No code changes needed - vLLM already supports this

**Configuration Example** (`examples/vllm-omni-vision.json`):
```json
{
  "llmModels": {
    "llava-1.5-7b": {
      "type": "vllm",
      "command": "vllm",
      "args": [
        "serve",
        "llava-hf/llava-1.5-7b-hf",
        "--port", "8001",
        "--dtype", "float16",
        "--max-model-len", "4096"
      ],
      "env": {
        "CUDA_VISIBLE_DEVICES": "0"
      },
      "endpoints": {
        "base_url": "http://localhost:8001/v1"
      },
      "capabilities": ["text", "vision"]
    },
    "qwen-vl": {
      "type": "vllm",
      "command": "vllm",
      "args": [
        "serve",
        "Qwen/Qwen-VL-Chat",
        "--port", "8002",
        "--dtype", "float16",
        "--trust-remote-code"
      ],
      "endpoints": {
        "base_url": "http://localhost:8002/v1"
      },
      "capabilities": ["text", "vision"]
    }
  }
}
```

**Key Addition**: `"capabilities": ["text", "vision"]` field (optional metadata)

#### Phase 2: Documentation for Vision

**File**: `docs/VLLM_VISION_MODELS.md` (new, ~200 lines)

**Sections**:
1. **Overview**: What are vision-language models
2. **Supported Models**:
   - LLaVA-v1.5-7b/13b
   - LLaVA-v1.6
   - Qwen-VL
   - InternVL
3. **Configuration**: How to configure vision models
4. **API Usage**:
   - Request format with image URLs
   - Base64 encoded images
   - Multiple images per request
5. **Examples**:
   - Image description
   - Visual question answering
   - OCR tasks
6. **Requirements**:
   - GPU memory requirements (typically 16GB+ for 7B models)
   - vLLM version requirements (0.3.0+)
7. **Troubleshooting**:
   - Image loading errors
   - Memory issues
   - Model-specific quirks

**File**: `CLAUDE.md` (update existing)

Add section under "LLM Inference Servers":
```markdown
### Vision-Language Models (vLLM Omni)

vLLM supports vision-language models (VLMs) that accept both text and images:

**Supported Models**:
- LLaVA-1.5-7b/13b (image understanding)
- Qwen-VL (multilingual vision)
- InternVL (high-performance vision)

**Configuration**:
```json
{
  "llmModels": {
    "llava": {
      "type": "vllm",
      "command": "vllm",
      "args": ["serve", "llava-hf/llava-1.5-7b-hf", "--port", "8001"],
      "endpoints": {"base_url": "http://localhost:8001/v1"}
    }
  }
}
```

**API Usage** (OpenAI-compatible):
```bash
curl -X POST http://localhost:8099/api/llm/llava/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llava",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "What is in this image?"},
        {"type": "image_url", "image_url": {"url": "https://example.com/cat.jpg"}}
      ]
    }]
  }'
```

See [docs/VLLM_VISION_MODELS.md](docs/VLLM_VISION_MODELS.md) for details.
```

### Part B: Image & Video Generation (Replicate Integration)

#### Phase 3: Configuration Schema

**File**: `examples/vllm-omni-generation.json` (new)

```json
{
  "llmModels": {
    "flux-image-gen": {
      "type": "replicate",
      "model": "black-forest-labs/flux-schnell",
      "api_key": "${REPLICATE_API_TOKEN}",
      "default_params": {
        "aspect_ratio": "1:1",
        "output_format": "png"
      },
      "capabilities": ["text-to-image"]
    },
    "cogvideox": {
      "type": "replicate",
      "model": "tencent/hunyuan-video",
      "api_key": "${REPLICATE_API_TOKEN}",
      "default_params": {
        "fps": 24,
        "num_frames": 120
      },
      "capabilities": ["text-to-video"],
      "timeout": 600
    },
    "stable-video": {
      "type": "replicate",
      "model": "stability-ai/stable-video-diffusion",
      "api_key": "${REPLICATE_API_TOKEN}",
      "capabilities": ["image-to-video"],
      "timeout": 300
    }
  }
}
```

**Key Points**:
- Use existing `"type": "replicate"` (already implemented!)
- Add `"capabilities"` metadata for clarity
- Chinese models supported: Hunyuan Video, CogVideoX

#### Phase 4: API Endpoints (Extend Existing)

**File**: `fluidmcp/cli/api/management.py` (extend existing routes)

**Design Decision**: Extend `/api/llm/*` namespace instead of creating separate `/api/omni/*` namespace to avoid API fragmentation.

**New Endpoints** (~80 lines):

```python
# Extend existing /llm/* routes - no separate /omni namespace
@router.post("/llm/v1/generate/image")
async def generate_image(
    model_id: str,
    request_body: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    Generate image from text prompt (text-to-image).

    Works with Replicate image generation models.
    Validates model supports 'text-to-image' capability.
    """
    from ..services.omni_adapter import generate_image as omni_generate_image
    return await omni_generate_image(model_id, request_body)

@router.post("/llm/v1/generate/video")
async def generate_video(
    model_id: str,
    request_body: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    Generate video from text prompt (text-to-video).

    Supports: CogVideoX, Hunyuan Video, etc.
    Validates model supports 'text-to-video' capability.
    """
    from ..services.omni_adapter import generate_video as omni_generate_video
    return await omni_generate_video(model_id, request_body)

@router.post("/llm/v1/animate")
async def animate_image(
    model_id: str,
    request_body: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    Animate image into video (image-to-video).

    Supports: Stable Video Diffusion, etc.
    Validates model supports 'image-to-video' capability.
    """
    from ..services.omni_adapter import animate_image as omni_animate_image
    return await omni_animate_image(model_id, request_body)

@router.get("/llm/predictions/{prediction_id}")
async def get_generation_status(
    prediction_id: str,
    token: str = Depends(get_token)
):
    """
    Check status of async generation (image/video).

    Returns status and output URLs when complete.
    """
    from ..services.omni_adapter import get_generation_status
    return await get_generation_status(prediction_id)
```

**Implementation Strategy**:
- **Extend existing `/api/llm/*` namespace** - no separate `/omni` routes
- Delegate to thin `omni_adapter.py` for validation + execution
- Validate capabilities before execution (fail fast)
- Reuse existing `replicate_client.py` for actual API calls
- Polling-based (Replicate's async prediction API)
- Return job ID + status URL

**Why This Design**:
- Single API namespace reduces cognitive load
- Consistent with existing LLM endpoints
- No duplicate routing logic
- Stays "basic" - just extends existing patterns

#### Phase 5: Examples

**File**: `examples/vllm-vision-config.json` (new)

Complete working example with LLaVA model configuration.

**File**: `examples/vllm-omni-complete.json` (new)

Complete example with vision + image + video models:
```json
{
  "llmModels": {
    "llava": {
      "type": "vllm",
      "command": "vllm",
      "args": ["serve", "llava-hf/llava-1.5-7b-hf", "--port", "8001"],
      "endpoints": {"base_url": "http://localhost:8001/v1"},
      "capabilities": ["vision"]
    },
    "flux-image": {
      "type": "replicate",
      "model": "black-forest-labs/flux-schnell",
      "api_key": "${REPLICATE_API_TOKEN}",
      "capabilities": ["text-to-image"]
    },
    "hunyuan-video": {
      "type": "replicate",
      "model": "tencent/hunyuan-video",
      "api_key": "${REPLICATE_API_TOKEN}",
      "capabilities": ["text-to-video"],
      "timeout": 600
    }
  }
}
```

**File**: `examples/omni-api-examples.sh` (new)

Shell script demonstrating all vLLM Omni capabilities:
```bash
#!/bin/bash
# Example: vLLM Omni - Vision, Image Gen, Video Gen

# 1. Vision: Image understanding (vLLM)
curl -X POST http://localhost:8099/api/llm/llava/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llava",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "Describe this image"},
        {"type": "image_url", "image_url": {"url": "https://picsum.photos/800/600"}}
      ]
    }]
  }'

# 2. Image Generation: Text-to-image (Replicate)
curl -X POST http://localhost:8099/api/llm/v1/generate/image \
  -H "Content-Type: application/json" \
  -d '{
    "model": "flux-image",
    "prompt": "A serene Japanese garden with cherry blossoms",
    "aspect_ratio": "16:9"
  }'
# Returns: {"prediction_id": "abc123", "status": "processing"}

# 3. Video Generation: Text-to-video (Replicate)
curl -X POST http://localhost:8099/api/llm/v1/generate/video \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hunyuan-video",
    "prompt": "一只熊猫在雨中弹吉他 (A panda playing guitar in the rain)",
    "duration": 5
  }'
# Returns: {"prediction_id": "xyz789", "status": "starting"}

# 4. Image-to-Video: Animate image (Replicate)
curl -X POST http://localhost:8099/api/llm/v1/animate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "stable-video",
    "image_url": "https://example.com/photo.jpg",
    "motion_bucket_id": 127
  }'

# 5. Check Status (for async gen)
curl http://localhost:8099/api/llm/predictions/xyz789
# Returns: {"status": "succeeded", "output": ["https://cdn.url/video.mp4"]}
```

### Phase 6: Testing

**File**: `tests/test_vllm_vision.py` (new, ~100 lines)

**Test Cases**:
```python
@pytest.mark.asyncio
class TestVLLMVisionSupport:
    """Test vision-language model support."""

    async def test_vision_request_format_validation(self):
        """Test that vision request format is valid."""
        request = {
            "model": "llava",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/img.jpg"}}
                ]
            }]
        }
        # Validate request structure
        assert isinstance(request["messages"][0]["content"], list)

    async def test_text_only_fallback(self):
        """Test that text-only requests still work."""
        request = {
            "model": "llava",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        # Should not raise error

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("VLLM_VISION_INTEGRATION_TEST"), reason="Requires GPU and vLLM")
    async def test_vision_inference(self):
        """Test actual vision inference (requires GPU)."""
        # Real integration test with vLLM running
        pass
```

## Critical Files

### Files to Create (7 new files):
1. `docs/VLLM_OMNI.md` - Complete vLLM Omni documentation (~400 lines)
2. `examples/vllm-omni-vision.json` - Vision models config
3. `examples/vllm-omni-generation.json` - Image/video generation config
4. `examples/vllm-omni-complete.json` - All capabilities combined
5. `examples/omni-api-examples.sh` - API usage demonstrations
6. `tests/test_vllm_omni.py` - Tests for omni endpoints (~150 lines)
7. `fluidmcp/cli/services/omni_adapter.py` - Ultra-thin adapter (~50-80 lines)

### Files to Modify (2 existing files):
1. `fluidmcp/cli/api/management.py` - Extend LLM routes (~80 lines)
2. `CLAUDE.md` - Add vLLM Omni section (~100 lines)

### Files to Reference (patterns to reuse):
1. `fluidmcp/cli/services/replicate_client.py` - Prediction/polling pattern
2. `fluidmcp/cli/services/replicate_openai_adapter.py` - Adapter pattern
3. `fluidmcp/cli/api/management.py` - Existing chat completions proxy
4. `examples/replicate-inference.json` - Replicate config structure

## Key Design Decisions

### 1. No Code Changes to Core
**Decision**: Documentation-only implementation
**Rationale**:
- vLLM already supports vision API (OpenAI-compatible)
- Our proxy already forwards requests correctly
- Just need to document how to use it

### 2. Optional Capabilities Field
**Decision**: Add optional `"capabilities": ["text", "vision"]` metadata
**Rationale**:
- Helps users identify model capabilities
- Not enforced (backward compatible)
- Can be used by UI/docs later

### 3. Image Input Only
**Decision**: Focus on image inputs (not video, not generated images)
**Rationale**:
- Matches vLLM's current capabilities
- "Basic support" as requested
- Can expand later if needed

### 4. No New Model Type in Phase 1
**Decision**: Do NOT introduce a new `"vllm-omni"` model type.
**Rationale**:
- Keeps configuration backward-compatible
- Avoids conflating vLLM with generation models
- Omni behavior is derived from `capabilities`, not model type
- `"type": "vllm"` → text + vision understanding
- `"type": "replicate"` → image/video generation

A dedicated `vllm-omni` type can be added later if needed for UI or routing logic, but is unnecessary for basic support.

### 5. Extend `/llm/*` Routes (No Separate `/omni/*` Namespace)
**Decision**: Add generation endpoints under existing `/api/llm/{model_id}/...` namespace.
**Rationale**:
- Avoids API surface fragmentation
- No duplicate routing logic
- Consistent with existing LLM endpoints
- Reduces cognitive load for users
- Single unified API namespace

**Routes**:
- `/api/llm/v1/generate/image` (not `/api/omni/...`)
- `/api/llm/v1/generate/video`
- `/api/llm/v1/animate`

This keeps the API "basic" by extending existing patterns rather than creating parallel systems.

### 6. Capability Validation (Enforced)
**Decision**: Validate `capabilities` field before executing requests.
**Rationale**:
- Fail fast with clear error messages
- Prevents confusing runtime errors
- Simple validation helper (~10 lines)
- Not complex - just dict lookup + raise

**Implementation**:
```python
def assert_capability(model_id: str, required: str):
    config = get_model_config(model_id)
    caps = config.get("capabilities", [])
    if required not in caps:
        raise HTTPException(400, f"Model doesn't support '{required}'")
```

### 7. Ultra-Thin omni_adapter.py (50-80 Lines)
**Decision**: Keep adapter extremely minimal - validation + delegation only.
**Rationale**:
- No complex orchestration logic
- Just validates capabilities and calls replicate_client
- 4 functions total: 3 generators + 1 status check
- Actual work done by existing replicate_client.py

**Structure**:
```python
# fluidmcp/cli/services/omni_adapter.py (~50-80 lines)

async def generate_image(model_id, payload):
    assert_capability(model_id, "text-to-image")
    return await replicate_client.predict(model_id, payload)

async def generate_video(model_id, payload):
    assert_capability(model_id, "text-to-video")
    return await replicate_client.predict(model_id, payload)

async def animate_image(model_id, payload):
    assert_capability(model_id, "image-to-video")
    return await replicate_client.predict(model_id, payload)

async def get_generation_status(prediction_id):
    return await replicate_client.get_prediction(prediction_id)
```

This is NOT a new architecture layer - just a thin routing adapter.

### 8. Standardize Shared Config Fields
**Decision**: Document shared vs. provider-specific configuration fields.
**Rationale**:
- Reduce config schema drift
- Clear naming conventions
- Easy to understand what applies to all models vs. specific providers

**Shared Fields** (all models):
- `type` - Model provider (vllm, replicate)
- `capabilities` - Feature list (optional but recommended)
- `timeout` - Request timeout in seconds
- `endpoints` - API endpoints dict

**Provider-Specific Fields**:
- vLLM only: `command`, `args`, `env`
- Replicate only: `model`, `api_key`, `default_params`

## Output Quality Considerations

Replicate provides access to state-of-the-art hosted models, including:
- **FLUX** (image generation) - Black Forest Labs' latest diffusion model
- **Stable Diffusion** variants - Industry-standard image generation
- **CogVideoX** - Zhipu AI's video generation model
- **Hunyuan Video** - Tencent's video generation model (Chinese support)

These are the **same model families** users would run locally, but hosted and optimized by Replicate.

**Output quality is comparable to self-hosted deployments**, with the trade-off being:
- ✅ No GPU infrastructure required
- ✅ Automatic scaling and optimization
- ✅ Latest model versions maintained
- ⚠️ External API dependency
- ⚠️ Usage-based cost (vs. fixed hardware cost)

**Cost Estimates** (approximate):
- Image generation: $0.001-0.01 per image
- Video generation: $0.05-0.20 per video (2-5 seconds)

For basic support and prototyping, this cost structure is typically acceptable. Production deployments can later migrate to self-hosted infrastructure if volume justifies it.

## Supported Models

| Model | Size | Use Case | GPU Memory |
|-------|------|----------|------------|
| LLaVA-1.5-7b | 7B | General vision | 16GB+ |
| LLaVA-1.5-13b | 13B | Better accuracy | 24GB+ |
| LLaVA-1.6 | 7B/13B | Improved version | 16-24GB+ |
| Qwen-VL-Chat | 7B | Multilingual | 16GB+ |
| InternVL-Chat | 2B-26B | High performance | 8-48GB+ |

## API Format (OpenAI Vision Compatible)

**Request Structure**:
```json
{
  "model": "model-id",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Question about image"},
        {"type": "image_url", "image_url": {"url": "https://..."}}
      ]
    }
  ],
  "max_tokens": 300
}
```

**Image URL Formats Supported**:
- HTTP/HTTPS URLs: `https://example.com/image.jpg`
- Data URLs (base64): `data:image/jpeg;base64,/9j/4AAQ...`

**Response**: Standard OpenAI chat completion format

## Verification Steps

1. **Install vLLM with vision support**:
   ```bash
   pip install vllm>=0.3.0
   ```

2. **Start vLLM with vision model**:
   ```bash
   vllm serve llava-hf/llava-1.5-7b-hf --port 8001
   ```

3. **Configure FluidMCP**:
   ```bash
   fluidmcp run examples/vllm-vision-config.json --file --start-server
   ```

4. **Test vision API**:
   ```bash
   curl -X POST http://localhost:8099/api/llm/llava/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d @examples/vision-request.json
   ```

5. **Verify response** contains image description

## Timeline Estimate

**Part A: Vision (Documentation Only)**:
- Configuration examples - 30 minutes
- Documentation writing - 1-2 hours

**Part B: Image/Video Generation**:
- Omni adapter implementation - 2-3 hours
- API endpoints (management.py) - 1-2 hours
- Configuration examples - 1 hour
- Testing - 2-3 hours
- Documentation - 2-3 hours

**Total**: ~1-2 engineering days (9-14 focused hours)

This timeline assumes PR #302 has been merged, providing the foundation of Replicate integration, unified LLM API structure, and observability infrastructure.

## Success Criteria

✅ **Vision** (vLLM native):
  - Users can configure vision models (LLaVA, Qwen-VL, etc.)
  - API accepts OpenAI vision format (image_url in messages)
  - Requests proxy correctly to vLLM endpoints
  - Documentation covers vision model usage

✅ **Image Generation** (Replicate):
  - Text-to-image endpoint works via Replicate
  - Supports FLUX, Stable Diffusion models
  - Async prediction with status polling

✅ **Video Generation** (Replicate):
  - Text-to-video endpoint (Chinese models: CogVideoX, Hunyuan)
  - Image-to-video endpoint (Stable Video Diffusion)
  - Polling-based async generation (30s-5min)
  - Download URLs returned on completion

✅ **Documentation**:
  - Complete guide to vLLM Omni capabilities
  - Example configurations for all types
  - API usage examples and shell scripts
  - Troubleshooting section

✅ **Testing**:
  - Unit tests for omni endpoints
  - Integration tests (with mocking for Replicate)
  - Example requests validated

✅ **No Breaking Changes**:
  - Existing vLLM text models work unchanged
  - Existing Replicate integration unaffected

## Implementation Strategy Summary

**Leverage Existing Code** (~85% reuse):
- Vision: vLLM already supports this, just document
- Image/Video: Replicate already integrated, just add thin routing layer
- API structure: Extend existing `/api/llm/*` routes (no new namespace)
- Configuration: Reuse existing `"type": "replicate"` pattern
- Polling/async: Already implemented in replicate_client.py

**New Code** (~15% new):
- `omni_adapter.py`: Ultra-thin validation + delegation (~50-80 lines)
- New API routes in `management.py`: 4 endpoints (~80 lines)
- Capability validation: Simple helper (~10 lines)
- Documentation and examples (~500 lines)

**Total New Code**: ~640-670 lines (reduced from ~1,040 lines)

**Architectural Principles**:
- ✅ No separate API namespace (extends `/llm/*`)
- ✅ No new model types (uses existing `vllm` and `replicate`)
- ✅ No complex orchestration (just validation + delegation)
- ✅ Capability enforcement (simple validation helper)
- ✅ Config standardization (shared fields documented)

**Why This Works**:
- ✅ Client gets video generation (requested feature)
- ✅ Stays "basic" (no heavy infrastructure)
- ✅ Supports Chinese models (CogVideoX, Hunyuan)
- ✅ Practical timeline (1-2 engineering days)
- ✅ Minimal risk (reuses proven patterns)
- ✅ No API fragmentation (single unified namespace)
- ✅ Simple mental model (extend, don't create parallel system)

## Out of Scope (Not "Basic Support")

❌ Local video generation servers (requires A100 80GB+)
❌ Custom diffusion model hosting
❌ Video file storage/CDN infrastructure
❌ Real-time streaming generation
❌ Advanced video editing capabilities
❌ Multi-GPU orchestration

These would require significant additional infrastructure and are beyond "basic support."
