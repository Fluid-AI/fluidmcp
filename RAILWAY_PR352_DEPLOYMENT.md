# Railway Deployment - PR #352 (Llama 4 Text Generation)

## Quick Overview

This deployment provides **text-only LLM API** using Replicate cloud:
- ✅ Llama 4 Maverick (latest Meta model)
- ✅ Mixtral 8x7B (high-quality open model)
- ✅ OpenAI-compatible API format
- ✅ No GPU required (Replicate handles inference)

## 🚀 Deploy to Railway (2 minutes)

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Add Railway deployment for PR #352 (Llama 4)"
git push origin fix/openai-api-format-and-cleanup
```

### Step 2: Deploy on Railway

**Option A: Railway Dashboard (Recommended)**

1. Go to https://railway.app/
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository
5. Select branch: `fix/openai-api-format-and-cleanup`
6. Railway auto-detects `Dockerfile.pr352`
7. Add environment variable:
   - Key: `REPLICATE_API_TOKEN`
   - Value: `r8_your_token_here` (get from https://replicate.com/account/api-tokens)
8. Click **Deploy**

**Option B: Railway CLI**

```bash
# Install CLI
npm install -g @railway/cli

# Login
railway login

# Create project
railway init

# Link to Railway config
cp railway-pr352.toml railway.toml

# Set token
railway variables set REPLICATE_API_TOKEN="r8_your_token_here"

# Deploy
railway up --dockerfile Dockerfile.pr352
```

### Step 3: Get Your Endpoint

After deployment, Railway provides a URL like:

```
https://your-app-name.up.railway.app
```

Or set a custom domain in Railway dashboard.

---

## 📡 API Endpoints for Client

### Base URL
```
https://your-app-name.up.railway.app
```

### 1. Chat Completions (Main Endpoint)

**Endpoint:** `POST /api/llm/v1/chat/completions`

**Request:**
```bash
curl -X POST https://your-app-name.up.railway.app/api/llm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-4-maverick",
    "messages": [
      {
        "role": "user",
        "content": "Explain quantum computing in simple terms"
      }
    ],
    "temperature": 0.7,
    "max_tokens": 500
  }'
```

**Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1707123456,
  "model": "llama-4-maverick",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Quantum computing uses quantum mechanics principles..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 85,
    "total_tokens": 100
  }
}
```

### 2. Available Models

**Endpoint:** `GET /api/llm/models`

**Response:**
```json
{
  "models": [
    {
      "id": "llama-4-maverick",
      "type": "replicate",
      "model": "meta/llama-4-maverick-instruct"
    },
    {
      "id": "mixtral-8x7b",
      "type": "replicate",
      "model": "nateraw/mixtral-8x7b-32kseqlen"
    }
  ]
}
```

### 3. Health Check

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "servers": 0,
  "running_servers": 0
}
```

### 4. Metrics (Monitoring)

**Endpoint:** `GET /api/metrics`

Returns Prometheus-format metrics:
- Request counts
- Latency statistics
- Token usage
- Error rates

### 5. Interactive API Documentation

**Endpoint:** `GET /docs`

Open in browser: `https://your-app-name.up.railway.app/docs`

Provides Swagger UI for testing all endpoints interactively.

---

## 🔧 Client Integration Examples

### Python (OpenAI SDK)

```python
from openai import OpenAI

# Point to your Railway endpoint
client = OpenAI(
    base_url="https://your-app-name.up.railway.app/api/llm/v1",
    api_key="dummy"  # Not used, but required by SDK
)

response = client.chat.completions.create(
    model="llama-4-maverick",
    messages=[
        {"role": "user", "content": "What is 2+2?"}
    ]
)

print(response.choices[0].message.content)
```

### JavaScript/TypeScript

```javascript
const response = await fetch('https://your-app-name.up.railway.app/api/llm/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    model: 'llama-4-maverick',
    messages: [
      { role: 'user', content: 'What is 2+2?' }
    ]
  })
});

const data = await response.json();
console.log(data.choices[0].message.content);
```

### cURL

```bash
curl -X POST https://your-app-name.up.railway.app/api/llm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-4-maverick",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

---

## 💰 Cost Breakdown

### Railway Costs
- **Free Tier**: $5/month credit (good for testing)
- **Pro**: $20/month + usage
- **Estimate**: $5-20/month for moderate traffic

### Replicate Costs (per request)
- **Llama 4 Maverick**: ~$0.001-0.003 per request
- **Mixtral 8x7B**: ~$0.001-0.002 per request

**Example Monthly Cost** (1,000 requests/day):
- 30,000 requests × $0.002 = **$60/month Replicate**
- Railway: **$20/month**
- **Total: ~$80/month**

---

## 🔐 Security (Optional)

To add authentication, set environment variable in Railway:

```bash
railway variables set MCP_SERVER_TOKEN="your-secret-token"
```

Then clients must include header:
```bash
curl -X POST https://your-app-name.up.railway.app/api/llm/v1/chat/completions \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '...'
```

---

## 📊 Monitoring

### View Logs in Railway
```bash
railway logs
```

### Check Metrics
```bash
curl https://your-app-name.up.railway.app/api/metrics
```

### Replicate Dashboard
Monitor usage and costs: https://replicate.com/account/billing

---

## 🐛 Troubleshooting

### Issue: "REPLICATE_API_TOKEN not set"
**Solution:** Add token in Railway dashboard → Variables → Add Variable

### Issue: 422 Error from Replicate
**Solution:** Model parameters invalid. Check model docs:
- Llama 4: https://replicate.com/meta/llama-4-maverick-instruct
- Mixtral: https://replicate.com/nateraw/mixtral-8x7b-32kseqlen

### Issue: Slow responses
**Solution:**
- Normal: First request can take 10-30s (cold start)
- Subsequent requests: 1-5s
- Increase timeout if needed

---

## 📞 Client Support Information

**Endpoint Base URL:**
```
https://your-app-name.up.railway.app
```

**API Format:** OpenAI-compatible (drop-in replacement)

**Available Models:**
- `llama-4-maverick` - Meta's latest Llama 4 (recommended)
- `mixtral-8x7b` - High-quality alternative

**Rate Limits:** None (Replicate handles scaling)

**Uptime:** 99.9% (Railway SLA)

**Support:**
- GitHub Issues: https://github.com/Fluid-AI/fluidmcp/issues
- Replicate Status: https://status.replicate.com/

---

## 🔄 Updates and Maintenance

### Update Deployment
```bash
git pull origin fix/openai-api-format-and-cleanup
git push origin fix/openai-api-format-and-cleanup
# Railway auto-deploys
```

### Add More Models
Edit `railway-pr352.json`:
```json
{
  "llmModels": {
    "your-new-model": {
      "type": "replicate",
      "model": "owner/model-name",
      "api_key": "${REPLICATE_API_TOKEN}"
    }
  }
}
```

Commit and push - Railway redeploys automatically.

---

## ✅ Quick Test Checklist

After deployment, verify:

- [ ] Health check returns 200 OK
- [ ] Swagger UI loads at `/docs`
- [ ] Chat completion works with Llama 4
- [ ] Chat completion works with Mixtral
- [ ] Metrics endpoint returns data
- [ ] Response time < 10s

**Test Command:**
```bash
curl https://your-app-name.up.railway.app/health && \
curl -X POST https://your-app-name.up.railway.app/api/llm/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-4-maverick","messages":[{"role":"user","content":"test"}]}'
```

---

## 📝 Client Handoff Checklist

Provide to client:

- [x] Base URL: `https://your-app-name.up.railway.app`
- [x] API endpoint: `/api/llm/v1/chat/completions`
- [x] Available models: `llama-4-maverick`, `mixtral-8x7b`
- [x] Swagger UI: `/docs`
- [x] Health check: `/health`
- [x] Example code (Python, JavaScript, cURL)
- [x] Expected response format
- [x] Cost estimates
- [x] Support contact

---

**Deployment Ready!** 🚀

Client can start making requests to your Railway endpoint immediately after deployment.
