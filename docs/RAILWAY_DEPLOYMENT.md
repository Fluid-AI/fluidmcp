# Railway Deployment Guide - Replicate LLM Only

This guide covers deploying **FluidMCP with only Replicate models** (no MCP servers) to Railway.

## What Gets Deployed

✅ **Text Generation**: Llama 4 Maverick (chat completions)
✅ **Image Generation**: FLUX Schnell (text-to-image)
✅ **Video Generation**: Kling v2.6 (text-to-video, image-to-video)
❌ **MCP Servers**: Not included (lightweight deployment)

## Prerequisites

1. **Railway Account**: https://railway.app/
2. **Replicate API Token**: https://replicate.com/account/api-tokens
3. **Replicate Billing**: Enable at https://replicate.com/account/billing

## Deployment Steps

### Option 1: Deploy via Railway CLI

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login to Railway
railway login

# 3. Create new project
railway init

# 4. Set environment variable
railway variables set REPLICATE_API_TOKEN="r8_your_token_here"

# 5. Deploy
railway up
```

### Option 2: Deploy via GitHub (Recommended)

```bash
# 1. Push to GitHub
git add .
git commit -m "Add Railway deployment config"
git push origin main

# 2. In Railway Dashboard:
#    - Click "New Project"
#    - Select "Deploy from GitHub repo"
#    - Choose your repository
#    - Railway auto-detects Dockerfile.railway

# 3. Set environment variable in Railway Dashboard:
#    - Go to your project
#    - Click "Variables" tab
#    - Add: REPLICATE_API_TOKEN = r8_your_token_here
```

### Option 3: One-Click Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/fluidmcp)

## Configuration

The deployment uses [`examples/railway-replicate-only.json`](../examples/railway-replicate-only.json):

```json
{
  "mcpServers": {},
  "llmModels": {
    "llama-4-maverick": {
      "type": "replicate",
      "model": "meta/llama-4-maverick-instruct",
      "api_key": "${REPLICATE_API_TOKEN}"
    },
    "flux-image": {
      "type": "replicate",
      "model": "black-forest-labs/flux-schnell",
      "capabilities": ["text-to-image"]
    },
    "kling-video": {
      "type": "replicate",
      "model": "kwaivgi/kling-v2.6",
      "capabilities": ["text-to-video", "image-to-video"]
    }
  }
}
```

## Testing Your Deployment

Once deployed, Railway provides a URL like: `https://your-app.up.railway.app`

### Test Chat Completions (Llama 4):

```bash
curl -X POST https://your-app.up.railway.app/api/llm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-4-maverick",
    "messages": [
      {
        "role": "user",
        "content": "What is 2+2?"
      }
    ]
  }'
```

### Test Image Generation (FLUX):

```bash
curl -X POST https://your-app.up.railway.app/api/llm/v1/generate/image \
  -H "Content-Type: application/json" \
  -d '{
    "model": "flux-image",
    "prompt": "A serene mountain landscape at sunset",
    "aspect_ratio": "16:9"
  }'
```

**Response:**
```json
{
  "id": "abc123xyz",
  "status": "starting"
}
```

**Check status:**
```bash
curl https://your-app.up.railway.app/api/llm/predictions/abc123xyz
```

### Test Video Generation (Kling):

```bash
curl -X POST https://your-app.up.railway.app/api/llm/v1/generate/video \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kling-video",
    "prompt": "A cat walking through a cyberpunk city",
    "duration": 5
  }'
```

### Access Swagger UI:

Open in browser: `https://your-app.up.railway.app/docs`

## Available Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/llm/v1/chat/completions` | POST | Text generation (Llama 4) |
| `/api/llm/v1/generate/image` | POST | Image generation (FLUX) |
| `/api/llm/v1/generate/video` | POST | Video generation (Kling) |
| `/api/llm/v1/animate` | POST | Image-to-video animation |
| `/api/llm/predictions/{id}` | GET | Check generation status |
| `/docs` | GET | Swagger UI (interactive API docs) |
| `/health` | GET | Health check |
| `/api/metrics` | GET | Prometheus metrics |

## Cost Estimates

### Railway Costs:
- **Free Tier**: $5/month credit (enough for testing)
- **Pro Plan**: $20/month + usage
- **Typical Usage**: ~$5-20/month for moderate traffic

### Replicate Costs (per request):
- **Llama 4 Maverick**: ~$0.001-0.003
- **FLUX Schnell (image)**: ~$0.003
- **Kling v2.6 (video)**: ~$0.08-0.20

**Example Monthly Cost** (100 requests/day):
- 3,000 text completions: ~$6
- 3,000 images: ~$9
- 100 videos: ~$15
- **Total**: ~$30/month Replicate + $20 Railway = **$50/month**

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `REPLICATE_API_TOKEN` | ✅ Yes | Your Replicate API token (r8_...) |
| `PORT` | No | Port to bind (default: 8099, Railway auto-sets) |

## Monitoring

### Health Check:
```bash
curl https://your-app.up.railway.app/health
```

**Healthy response:**
```json
{
  "status": "healthy",
  "servers": 0,
  "running_servers": 0
}
```

### Metrics:
```bash
curl https://your-app.up.railway.app/api/metrics
```

Returns Prometheus-format metrics:
- Request counts
- Latency stats
- Token usage
- Error rates

## Scaling

Railway automatically scales based on traffic:
- **Vertical scaling**: Upgrade to more RAM/CPU in Railway dashboard
- **Horizontal scaling**: Not needed (Replicate handles load)
- **Rate limits**: Replicate has generous limits, Railway is unlimited

## Security

### Recommended Settings:

1. **Add Authentication** (optional):
   - Set `MCP_SERVER_TOKEN` environment variable in Railway
   - All API requests will require `Authorization: Bearer <token>` header

2. **Enable CORS** (for web apps):
   - Railway enables HTTPS by default
   - CORS is pre-configured in FluidMCP

3. **Rate Limiting**:
   - Replicate has built-in rate limits
   - Add application-level limits if needed

## Troubleshooting

### Issue: "REPLICATE_API_TOKEN not set"

**Solution:** Add the environment variable in Railway dashboard:
```bash
railway variables set REPLICATE_API_TOKEN="r8_your_token_here"
```

### Issue: "422 Unprocessable Entity" from Replicate

**Solution:** The model parameters are wrong. Check model documentation:
- FLUX: https://replicate.com/black-forest-labs/flux-schnell
- Kling: https://replicate.com/kwaivgi/kling-v2.6
- Llama 4: https://replicate.com/meta/llama-4-maverick-instruct

### Issue: Image/Video generation hangs

**Solution:** Increase timeout in config:
```json
{
  "timeout": 600,
  "max_retries": 5
}
```

### Issue: High costs

**Solution:** Monitor usage at https://replicate.com/account/billing
- Set spending limits in Replicate dashboard
- Cache responses when possible
- Use cheaper models for testing

## Local Testing

Before deploying, test locally:

```bash
# Set token
export REPLICATE_API_TOKEN="r8_your_token_here"

# Run with Railway config
fluidmcp run examples/railway-replicate-only.json --file --start-server

# Test in browser
open http://localhost:8099/docs
```

## Custom Domain

In Railway dashboard:
1. Go to your project → Settings
2. Click "Domains"
3. Add custom domain (e.g., `api.yourdomain.com`)
4. Update DNS records as instructed

## Support

- FluidMCP Issues: https://github.com/Fluid-AI/fluidmcp/issues
- Railway Docs: https://docs.railway.app/
- Replicate Docs: https://replicate.com/docs

## Example Use Cases

1. **AI Chatbot**: Text generation with Llama 4
2. **Content Creation**: Generate images for marketing
3. **Video Production**: Create videos from text prompts
4. **API Backend**: Provide AI services to frontend apps
5. **Prototyping**: Quick AI feature testing

## Next Steps

After deployment:
1. Test all endpoints via Swagger UI
2. Set up monitoring/alerts
3. Add authentication if needed
4. Configure custom domain
5. Monitor costs in Replicate dashboard
