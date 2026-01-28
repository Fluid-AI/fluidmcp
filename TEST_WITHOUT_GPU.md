# Testing FluidMCP vLLM Integration Without GPU

This guide shows how to test and implement vLLM integration features **without a GPU** using mock servers.

## Quick Start (5 minutes)

### Step 1: Start Mock vLLM Server
```bash
# Terminal 1: Start the mock server
cd /workspaces/fluidmcp
python tests/mock_vllm_server.py
```

### Step 2: Start FluidMCP
```bash
# Terminal 2: Start FluidMCP with mock config
fluidmcp run examples/vllm-mock-config.json --file --start-server
```

### Step 3: Test It
```bash
# Terminal 3: Test the integration
curl -X POST http://localhost:8099/llm/mock-llm/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "max_tokens": 100
  }'
```

**Expected Output:**
```json
{
  "id": "chatcmpl-mock123",
  "object": "chat.completion",
  "model": "mock-model",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Mock response to: Hello, how are you?..."
    }
  }]
}
```

---

## What You Can Test Without GPU

### ✅ Test 1: FluidMCP Routing
Verify FluidMCP correctly routes requests to the backend:

```bash
# Test routing to mock LLM
curl -X POST http://localhost:8099/llm/mock-llm/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Test routing"}]}'
```

### ✅ Test 2: Monitoring Metrics (Our PR!)
Test the monitoring metrics we just fixed:

```bash
# Make several requests
for i in {1..10}; do
  curl -s -X POST http://localhost:8099/llm/mock-llm/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"messages\": [{\"role\": \"user\", \"content\": \"Request $i\"}]}" &
done
wait

# Check metrics
curl http://localhost:8099/metrics | grep fluidmcp_requests_total
curl http://localhost:8099/metrics | grep fluidmcp_request_duration
```

**This tests:**
- ✅ Request counting
- ✅ Histogram metrics
- ✅ Concurrent request handling
- ✅ Thread safety fixes we made

### ✅ Test 3: Error Handling
Test the broken pipe fixes we implemented:

```bash
# Kill mock server while requests are in flight
# Terminal 1: Start mock server
python tests/mock_vllm_server.py

# Terminal 2: Send request and immediately kill server
curl -X POST http://localhost:8099/llm/mock-llm/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Test"}]}' &

# Terminal 1: Ctrl+C (kill server)

# Check error is handled gracefully
curl http://localhost:8099/metrics | grep fluidmcp_errors_total
```

### ✅ Test 4: Multi-Model Configuration
Test multiple mock models:

```json
// examples/vllm-multi-mock-config.json
{
  "llmModels": {
    "mock-gpt": {
      "command": "python",
      "args": ["tests/mock_vllm_server.py"],
      "env": {"MODEL_NAME": "mock-gpt"},
      "endpoints": {"base_url": "http://localhost:8001/v1"}
    },
    "mock-llama": {
      "command": "python",
      "args": ["tests/mock_vllm_server.py"],
      "env": {"MODEL_NAME": "mock-llama"},
      "endpoints": {"base_url": "http://localhost:8002/v1"}
    }
  }
}
```

---

## What You Can Build Without GPU

### 1. **Integration Tests**
```python
# tests/test_vllm_integration.py
import pytest
import requests

def test_chat_completion():
    response = requests.post(
        "http://localhost:8099/llm/mock-llm/chat/completions",
        json={
            "messages": [{"role": "user", "content": "test"}]
        }
    )
    assert response.status_code == 200
    assert "choices" in response.json()

def test_metrics_endpoint():
    response = requests.get("http://localhost:8099/metrics")
    assert response.status_code == 200
    assert "fluidmcp_requests_total" in response.text
```

### 2. **Load Testing Scripts**
```bash
#!/bin/bash
# tests/load_test.sh

echo "Running load test with 100 concurrent requests..."

for i in {1..100}; do
  curl -s -X POST http://localhost:8099/llm/mock-llm/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"messages\": [{\"role\": \"user\", \"content\": \"Request $i\"}]}" &
done
wait

echo "Checking metrics..."
curl -s http://localhost:8099/metrics | grep -E "requests_total|errors_total|request_duration"
```

### 3. **API Documentation**
Test and document all endpoints without needing real vLLM.

### 4. **Client Libraries**
Build Python/JS clients that work with the API:

```python
# clients/fluidmcp_client.py
class FluidMCPClient:
    def __init__(self, base_url="http://localhost:8099"):
        self.base_url = base_url

    def chat_completion(self, model_id, messages, **kwargs):
        response = requests.post(
            f"{self.base_url}/llm/{model_id}/chat/completions",
            json={"messages": messages, **kwargs}
        )
        return response.json()

# Usage
client = FluidMCPClient()
result = client.chat_completion(
    "mock-llm",
    [{"role": "user", "content": "Hello"}]
)
```

---

## Advanced: Simulating Real vLLM Behavior

Enhance the mock server to simulate specific scenarios:

### Scenario 1: Slow Responses (Timeout Testing)
```python
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # Simulate slow model
    time.sleep(5)  # 5 second delay
    # ... rest of response
```

### Scenario 2: Random Errors (Error Recovery Testing)
```python
import random

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # Randomly fail 20% of requests
    if random.random() < 0.2:
        raise HTTPException(status_code=500, detail="Model error")
    # ... rest of response
```

### Scenario 3: Rate Limiting
```python
from collections import defaultdict
from datetime import datetime

request_counts = defaultdict(list)

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # Simple rate limiting
    now = datetime.now()
    request_counts["default"] = [t for t in request_counts["default"]
                                   if (now - t).seconds < 60]

    if len(request_counts["default"]) > 10:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    request_counts["default"].append(now)
    # ... rest of response
```

---

## Testing Checklist

Use this to verify FluidMCP features without GPU:

- [ ] **Basic Routing**: Requests reach mock server ✅
- [ ] **Metrics Collection**: Prometheus metrics populate ✅
- [ ] **Error Handling**: Graceful failure when server dies ✅
- [ ] **Concurrent Requests**: No race conditions ✅
- [ ] **Thread Safety**: Multiple simultaneous requests work ✅
- [ ] **Health Checks**: Server status reporting ✅
- [ ] **Dynamic Management**: Start/stop/restart ✅
- [ ] **Configuration**: Different configs load correctly ✅

---

## Next Steps After Testing

Once you've tested with mocks:

1. **Document findings** - What works, what doesn't
2. **Create test suite** - Automated tests using mocks
3. **Write integration guide** - For users with GPUs
4. **Deploy to cloud** - Test with real vLLM when ready

---

## Quick Reference

### Start Mock Server
```bash
python tests/mock_vllm_server.py
```

### Start FluidMCP
```bash
fluidmcp run examples/vllm-mock-config.json --file --start-server
```

### Test Request
```bash
curl -X POST http://localhost:8099/llm/mock-llm/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "test"}]}'
```

### Check Metrics
```bash
curl http://localhost:8099/metrics
```

---

## Benefits of Mock Testing

✅ **No GPU required** - Test on any laptop
✅ **Fast iteration** - No model loading time
✅ **Controlled scenarios** - Simulate specific behaviors
✅ **Cost effective** - No cloud GPU costs
✅ **Reliable CI/CD** - Consistent test results

This approach lets you build and test the entire integration layer without ever needing a GPU!
