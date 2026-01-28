# vLLM Integration Demo Guide

This guide shows what you can implement **RIGHT NOW** with FluidMCP's merged vLLM integration.

## Prerequisites

```bash
# Install vLLM
pip install vllm

# Or if you have GPU:
pip install vllm torch
```

---

## Demo 1: Quick Start - Single Model (5 minutes)

### Step 1: Start FluidMCP
```bash
cd /workspaces/fluidmcp
fluidmcp run examples/vllm-config.json --file --start-server
```

This starts:
- vLLM serving `facebook/opt-125m` (small, fast model)
- FluidMCP gateway on port 8099
- vLLM backend on port 8001

### Step 2: Test Chat Completion
```bash
curl -X POST http://localhost:8099/llm/vllm/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Write a Python hello world"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

### Step 3: Test Streaming
```bash
curl -X POST http://localhost:8099/llm/vllm/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Count from 1 to 10"}
    ],
    "stream": true,
    "max_tokens": 100
  }'
```

---

## Demo 2: Multi-Model Setup (10 minutes)

### Step 1: Start Multiple Models
```bash
fluidmcp run examples/vllm-multi-model-config.json --file --start-server
```

This starts:
- Model 1: `facebook/opt-125m` on port 8001
- Model 2: `gpt2` on port 8002
- Both accessible through FluidMCP on port 8099

### Step 2: Test Model Routing
```bash
# Query OPT model
curl -X POST http://localhost:8099/llm/vllm-opt/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Explain AI"}], "max_tokens": 50}'

# Query GPT2 model
curl -X POST http://localhost:8099/llm/vllm-gpt2/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Explain AI"}], "max_tokens": 50}'
```

### Step 3: Compare Responses
```bash
# Compare both models side-by-side
echo "=== OPT Model ===" && \
curl -s -X POST http://localhost:8099/llm/vllm-opt/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is 2+2?"}], "max_tokens": 20}' | jq -r '.choices[0].message.content'

echo "\n=== GPT2 Model ===" && \
curl -s -X POST http://localhost:8099/llm/vllm-gpt2/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is 2+2?"}], "max_tokens": 20}' | jq -r '.choices[0].message.content'
```

---

## Demo 3: Production Configuration (30 minutes)

### Step 1: Create Production Config
```json
{
  "llmModels": {
    "llama2-7b-prod": {
      "model": "meta-llama/Llama-2-7b-chat-hf",
      "port": 8001,
      "profile": "production",
      "config": {
        "gpu_memory_utilization": 0.9,
        "max_num_seqs": 64,
        "max_num_batched_tokens": 8192,
        "max_model_len": 4096,
        "dtype": "float16",
        "tensor_parallel_size": 2,
        "quantization": "awq"
      },
      "timeouts": {
        "startup": 300,
        "streaming": null,
        "non_streaming": 120
      },
      "env": {
        "CUDA_VISIBLE_DEVICES": "0,1"
      }
    }
  }
}
```

### Step 2: Test Production Features
```bash
# High throughput test
for i in {1..10}; do
  curl -X POST http://localhost:8099/llm/llama2-7b-prod/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"messages\": [{\"role\": \"user\", \"content\": \"Request $i\"}]}" &
done
wait

# Long context test
curl -X POST http://localhost:8099/llm/llama2-7b-prod/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Summarize this long text: [your 4000 token text here]"}
    ],
    "max_tokens": 500
  }'
```

---

## Demo 4: Dynamic Server Management (15 minutes)

### Available Endpoints

```bash
# List running models
curl http://localhost:8099/servers

# Get specific model status
curl http://localhost:8099/servers/vllm

# Start a new model dynamically
curl -X POST http://localhost:8099/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "dynamic-gpt2",
    "config": {
      "command": "vllm",
      "args": ["serve", "gpt2", "--port", "8003"],
      "endpoints": {"base_url": "http://localhost:8003/v1"}
    }
  }'

# Stop a model
curl -X DELETE http://localhost:8099/servers/dynamic-gpt2

# Restart a model
curl -X POST http://localhost:8099/servers/vllm/restart
```

---

## Demo 5: Advanced Use Cases

### Use Case 1: A/B Testing Different Models
```bash
# Create config with two model versions
cat > ab-test-config.json <<'EOF'
{
  "llmModels": {
    "model-a": {
      "command": "vllm",
      "args": ["serve", "facebook/opt-125m", "--port", "8001"],
      "endpoints": {"base_url": "http://localhost:8001/v1"}
    },
    "model-b": {
      "command": "vllm",
      "args": ["serve", "gpt2", "--port", "8002"],
      "endpoints": {"base_url": "http://localhost:8002/v1"}
    }
  }
}
EOF

# Test both with same prompt
PROMPT='{"messages": [{"role": "user", "content": "Explain AI in 20 words"}]}'

echo "Model A:" && curl -s -X POST http://localhost:8099/llm/model-a/chat/completions \
  -H "Content-Type: application/json" -d "$PROMPT" | jq -r '.choices[0].message.content'

echo "Model B:" && curl -s -X POST http://localhost:8099/llm/model-b/chat/completions \
  -H "Content-Type: application/json" -d "$PROMPT" | jq -r '.choices[0].message.content'
```

### Use Case 2: Load Balancing (Future: when monitoring merges)
```bash
# Monitor model performance
curl http://localhost:8099/metrics | grep vllm

# Route based on load
# (This will be automatic when PR #173 merges)
```

---

## What's Available Now vs Coming Soon

### ✅ Available NOW (Merged to main):
- ✅ Single model serving
- ✅ Multi-model serving
- ✅ OpenAI-compatible API
- ✅ Streaming responses
- ✅ Advanced configuration (quantization, GPU settings)
- ✅ Dynamic start/stop/restart
- ✅ Health monitoring
- ✅ MongoDB persistence

### ⏳ Coming Soon (In Review):
- ⏳ Function calling with tools (PR #27)
- ⏳ Prometheus metrics & monitoring (PR #173)
- ⏳ Automatic error recovery
- ⏳ Request rate limiting
- ⏳ Load balancing

---

## Troubleshooting

### Issue: vLLM not starting
```bash
# Check logs
tail -f /tmp/fluidmcp-*.log

# Check if port is available
lsof -i :8001
```

### Issue: Out of memory
```bash
# Reduce GPU memory utilization in config
"gpu_memory_utilization": 0.5  # Instead of 0.9

# Or use CPU mode
"device": "cpu"
```

### Issue: Model download fails
```bash
# Pre-download model
python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('facebook/opt-125m')"
```

---

## Next Steps

1. **Test with your own models** - Replace model names in configs
2. **Integrate with your app** - Use the OpenAI-compatible API
3. **Scale up** - Add more models or use tensor parallelism
4. **Wait for function calling** - PR #27 adds tool use capabilities
5. **Wait for monitoring** - PR #173 adds production metrics

---

## Questions?

Check:
- `/workspaces/fluidmcp/examples/` for more config examples
- `/workspaces/fluidmcp/fluidmcp/cli/services/vllm_config.py` for all config options
- GitHub Issues for support
