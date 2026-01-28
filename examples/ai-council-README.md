# AI Council Integration with FluidMCP

## Overview

This directory contains configuration files for integrating [ai-council](https://github.com/0xAkuti/ai-council-mcp) with FluidMCP. AI Council is a multi-model consensus tool that queries multiple AI models (Claude, Gemini, DeepSeek) in parallel via OpenRouter and synthesizes their responses to reduce bias and improve answer quality through ensemble AI decision-making.

## What is AI Council?

**AI Council is an automatic multi-LLM consensus engine**, NOT a manual agent coordinator.

Think of it like:
- ✅ A voting panel of AI experts (queries 3-5 models, synthesizes consensus)
- ✅ Ensemble machine learning for AI (reduces individual model bias)
- ❌ NOT a manual multi-agent chat (that's agents-council)
- ❌ NOT a single AI model (calls multiple models per query)

### How It Works

1. **Parallel Consultation**: When you ask a question, ai-council simultaneously queries 3 models (e.g., Claude Sonnet 4, Gemini 2.5 Pro, DeepSeek V3)
2. **Anonymous Analysis**: Responses are anonymized with code names (Alpha, Beta, Gamma) to prevent synthesis bias
3. **Smart Synthesis**: A randomly-selected model reviews all anonymous responses and produces a comprehensive consensus answer

### Key Benefits

- **Reduced Bias**: No single model's quirks dominate the answer
- **Improved Accuracy**: Ensemble decision-making catches errors individual models might make
- **Diverse Perspectives**: Different models trained on different data provide complementary insights
- **Automatic**: No manual coordination needed - just ask and receive synthesized answer

## Configuration Files

### 1. ai-council-config.json
Basic configuration using ai-council defaults.

```json
{
  "mcpServers": {
    "ai-council": {
      "command": "uvx",
      "args": ["ai-council"],
      "env": {
        "OPENROUTER_API_KEY": "your-openrouter-api-key-here"
      }
    }
  }
}
```

**Use case**: Simple setup - ai-council automatically selects 3 models via OpenRouter and synthesizes responses.

**Default behavior**:
- Queries 3 models in parallel (cost: 3 API calls per query)
- 60-second timeout per model
- Uses OpenRouter's default model selection

### 2. ai-council-advanced.json
Advanced configuration with explicit parameters.

```json
{
  "mcpServers": {
    "ai-council-advanced": {
      "command": "uvx",
      "args": [
        "ai-council",
        "--max-models", "3",
        "--parallel-timeout", "90",
        "--log-level", "INFO"
      ],
      "env": {
        "OPENROUTER_API_KEY": "your-openrouter-api-key-here",
        "OPENAI_API_KEY": "your-openai-api-key-here"
      }
    }
  }
}
```

**Use case**: Control over model count, timeouts, and logging.

**Parameters**:
- `--max-models 3`: Limit to 3 models (controls cost)
- `--parallel-timeout 90`: Wait up to 90 seconds for all models to respond
- `--log-level INFO`: Set logging verbosity (DEBUG/INFO/WARNING/ERROR)
- `OPENAI_API_KEY`: Optional - enables GPT models in addition to OpenRouter models

## Required API Keys

### OpenRouter API Key (Required)

**What is OpenRouter?**
OpenRouter is a unified API gateway that provides access to multiple AI models (Claude, Gemini, DeepSeek, GPT, etc.) through a single API key.

**Why OpenRouter?**
- Single API key for multiple models (no need for separate Anthropic, Google, OpenAI accounts)
- Pay-as-you-go pricing
- No subscriptions required
- Supports all major AI models

**Get your OpenRouter API key**:
1. Visit https://openrouter.ai/keys
2. Sign up for an account (free)
3. Generate an API key
4. Add credits to your account (required for usage)

**Pricing** (as of 2026):
- Claude Sonnet 4: ~$3 per 1M input tokens
- Gemini 2.5 Pro: ~$1.25 per 1M input tokens
- DeepSeek V3: ~$0.27 per 1M input tokens
- **Cost per query**: 3x multiplier (3 models queried)

### OpenAI API Key (Optional)

**Purpose**: Enable GPT models (GPT-4, GPT-4 Turbo) in addition to OpenRouter models.

**Get your OpenAI API key**:
1. Visit https://platform.openai.com/api-keys
2. Sign up for an account
3. Generate an API key
4. Add credits or set up billing

**Note**: If you only use OpenRouter, you don't need an OpenAI key.

## Quick Start Guide

### Step 1: Start FluidMCP Backend

```bash
# Start backend + frontend on port 8099
fmcp serve --allow-insecure --allow-all-origins --port 8099
```

Access points:
- Frontend UI: http://localhost:8099/ui
- Swagger API: http://localhost:8099/docs
- API Base: http://localhost:8099/api

### Step 2: Verify uvx is Available

```bash
# Check uvx installation
uvx --version

# If not installed:
pip install uv
```

**What is uvx?**
`uvx` is a Python package runner (like `npx` for Node.js) that downloads and runs Python packages without permanent installation. ai-council will be downloaded automatically on first use.

### Step 3: Add AI Council Server

**Option A: Using curl**

```bash
curl -X POST http://localhost:8099/api/servers \
  -H "Content-Type: application/json" \
  -d '{
    "id": "ai-council",
    "name": "AI Council",
    "description": "Multi-model consensus AI - queries Claude, Gemini, DeepSeek in parallel",
    "command": "uvx",
    "args": ["ai-council"],
    "env": {
      "OPENROUTER_API_KEY": "sk-or-v1-your-actual-key-here"
    }
  }'
```

**Option B: Using Swagger UI**

1. Navigate to http://localhost:8099/docs
2. Find `POST /api/servers`
3. Click "Try it out"
4. Paste the JSON body
5. Click "Execute"

**Option C: Run from config file**

```bash
# First, update ai-council-config.json with your real API key
# Then run:
fmcp run examples/ai-council-config.json --file --start-server
```

### Step 4: Start the Server

**Via curl**:
```bash
curl -X POST http://localhost:8099/api/servers/ai-council/start
```

**Via Swagger UI**:
- Navigate to `POST /api/servers/{id}/start`
- Enter `ai-council` as the server ID
- Execute

**Via Frontend**:
- Go to http://localhost:8099/ui
- Find "AI Council" server card
- Click "Start" button

**First start**: uvx will download ai-council package (~10-30 seconds). Subsequent starts are instant.

### Step 5: Verify Tools Discovered

```bash
curl -X POST http://localhost:8099/ai-council/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

Expected: List of MCP tools (tool names and schemas will be documented after discovery).

## Testing Workflow

### Basic Consensus Query

Once the exact tool name is discovered (placeholder: `query_council`), test with:

```bash
curl -X POST http://localhost:8099/api/servers/ai-council/tools/query_council/run \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the best practices for implementing JWT authentication in a REST API?",
    "max_models": 3
  }'
```

**Expected response structure**:
```json
{
  "individual_responses": [
    {"model": "Alpha", "response": "..."},
    {"model": "Beta", "response": "..."},
    {"model": "Gamma", "response": "..."}
  ],
  "synthesized_answer": "Based on consensus from 3 models...",
  "metadata": {
    "models_queried": 3,
    "execution_time": "45.2s",
    "synthesis_model": "Beta"
  }
}
```

### Example Queries

**Architecture Decision**:
```bash
curl -X POST http://localhost:8099/api/servers/ai-council/tools/query_council/run \
  -d '{"query": "Should we use microservices or monolith for a startup MVP?"}'
```

**Technical Comparison**:
```bash
curl -X POST http://localhost:8099/api/servers/ai-council/tools/query_council/run \
  -d '{"query": "Compare PostgreSQL vs MongoDB for a real-time analytics platform"}'
```

**Best Practices**:
```bash
curl -X POST http://localhost:8099/api/servers/ai-council/tools/query_council/run \
  -d '{"query": "What are the security best practices for handling user passwords in 2026?"}'
```

## Frontend UI Usage

### Dashboard View
1. Navigate to http://localhost:8099/ui
2. See "AI Council" server listed
3. Check status (stopped/running/starting)
4. Tool count badge (number of available tools)
5. Start/Stop/Restart buttons

### Configure API Keys
1. Click "Details" on AI Council card
2. Navigate to "Environment Variables" tab
3. Click "Edit Environment Variables"
4. Add/update `OPENROUTER_API_KEY`
5. Optionally add `OPENAI_API_KEY`
6. Click "Save"
7. Server automatically restarts with new keys

**Security**: API keys are masked as `****` in the UI. Once set, you cannot view them again (only update).

### Execute Queries
1. On Server Details page, view available tools
2. Click on consensus query tool
3. Fill in the form:
   - Query: Your question
   - Max Models: 3 (recommended)
4. Click "Run Tool"
5. Wait 30-60 seconds for response
6. View:
   - Individual model responses (Alpha, Beta, Gamma)
   - Synthesized consensus answer
   - Execution metadata

### Execution History
- All tool executions are saved in browser localStorage
- View past queries and responses
- Clear history option available

## Cost Management

### Understanding Costs

**Each query = 3-5 API calls** (one per model)

Example costs per query (based on typical question length):
- Claude Sonnet 4: $0.003
- Gemini 2.5 Pro: $0.001
- DeepSeek V3: $0.0003
- **Total per query**: ~$0.0043 (3 models)

**Monthly cost estimate**:
- 100 queries/month: ~$0.43
- 1,000 queries/month: ~$4.30
- 10,000 queries/month: ~$43.00

**Cost control measures**:
1. Default to `--max-models 3` (not 5)
2. Use `--parallel-timeout 90` to avoid hanging queries
3. Monitor OpenRouter usage dashboard

### Reducing Costs

**Option 1**: Use cheaper models
- DeepSeek V3 is 10x cheaper than Claude but still effective
- Gemini 2.5 Pro offers good balance (2.4x cheaper than Claude)

**Option 2**: Reduce max_models
- 2 models = 2x cost (less consensus)
- 3 models = 3x cost (recommended balance)
- 5 models = 5x cost (maximum diversity)

**Option 3**: Batch queries
- Group similar questions
- Use ai-council for important decisions only
- Use single model for routine queries

## Comparison: ai-council vs agents-council

Both are MCP servers for FluidMCP, but serve different purposes:

| Feature | ai-council | agents-council |
|---------|------------|----------------|
| **Purpose** | Multi-model consensus | Multi-agent coordination |
| **How it works** | Calls 3-5 AI models automatically | Passes messages between agent sessions |
| **API Keys** | ✅ Required (OpenRouter/OpenAI) | ❌ Not required |
| **Cost per query** | 3-5x (one call per model) | Free (no API calls) |
| **Response time** | 30-60 seconds (parallel queries) | Instant (message passing) |
| **Use case** | Get consensus on complex questions | Coordinate multiple AI sessions |
| **Automatic** | ✅ Fully automatic | ❌ Manual (requires human-driven agents) |
| **State** | Stateless (no session) | Stateful (persistent sessions) |
| **Installation** | uvx (Python) | npx (Node.js) |

### When to Use ai-council

- ✅ Making important technical decisions (architecture, technology choices)
- ✅ Answering complex questions with multiple valid approaches
- ✅ Reducing bias in AI responses
- ✅ Getting diverse perspectives automatically
- ✅ You have OpenRouter API key and budget for 3x cost

### When to Use agents-council

- ✅ Coordinating multiple human developers with AI assistants
- ✅ Async collaboration across different AI tools (Claude Code, Codex, Gemini)
- ✅ Persistent discussion threads
- ✅ No API costs acceptable
- ✅ Manual control over agent responses

### Can You Use Both?

Yes! They serve complementary purposes:
- Use **agents-council** for human-in-loop multi-agent discussions
- Use **ai-council** for automatic multi-model consensus on specific questions

## Troubleshooting

### Issue: uvx command not found

**Solution**:
```bash
# Install uv (includes uvx)
pip install uv

# Or use system package manager
# macOS:
brew install uv

# Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Issue: Server fails to start with "Invalid API key"

**Solution**:
1. Verify your OpenRouter API key at https://openrouter.ai/keys
2. Check key format: starts with `sk-or-v1-`
3. Ensure key has credits in OpenRouter account
4. Update key via FluidMCP UI: Server Details → Environment Variables
5. Restart server after updating key

### Issue: "Connection timeout" errors

**Solution**:
1. Increase timeout in config: `--parallel-timeout 120`
2. Check internet connection
3. Verify OpenRouter API status: https://openrouter.ai/status
4. Reduce number of models: `--max-models 2`

### Issue: Python version error ("Requires Python 3.10+")

**Solution**:
```bash
# Check Python version
python3 --version

# If < 3.10, upgrade Python:
# macOS:
brew install python@3.12

# Linux (Ubuntu/Debian):
sudo apt install python3.12

# Windows:
# Download from python.org
```

### Issue: Slow responses (>60 seconds)

**Expected behavior**: ai-council queries 3 models in parallel, which takes 30-60 seconds.

**To speed up**:
1. Use `--parallel-timeout 60` (shorter timeout)
2. Reduce to 2 models: `--max-models 2`
3. Use faster models (DeepSeek is faster than Claude)

### Issue: High API costs

**Solution**:
1. Verify `--max-models 3` is set (default may be higher)
2. Monitor usage at https://openrouter.ai/activity
3. Set spending limits in OpenRouter account
4. Use for critical queries only

### Issue: Frontend shows "****" for API key, need to verify

**Expected behavior**: Keys are masked for security.

**To verify key is set**:
1. Try running a query tool
2. If it returns results, key is valid
3. If it returns auth error, key is invalid or missing

**To update key**:
1. Server Details → Environment Variables → Edit
2. Enter new key
3. Save (triggers server restart)

## MongoDB Integration

### Collections Used

**fluidmcp_servers** (Server Configuration):
```json
{
  "id": "ai-council",
  "name": "AI Council",
  "config": {
    "command": "uvx",
    "args": ["ai-council"],
    "env": {"OPENROUTER_API_KEY": "****"}  // Masked
  },
  "tools": [...],  // Cached after discovery
  "created_at": "2026-01-28T...",
  "updated_at": "2026-01-28T..."
}
```

**fluidmcp_server_instances** (Runtime State):
```json
{
  "server_id": "ai-council",
  "state": "running",
  "pid": 12345,
  "start_time": "2026-01-28T...",
  "env": {"OPENROUTER_API_KEY": "sk-or-v1-actual-key"},  // Stored securely
  "started_by": "user@example.com"
}
```

**fluidmcp_server_logs** (Server Logs):
```json
{
  "server_name": "ai-council",
  "timestamp": "2026-01-28T...",
  "stream": "stdout",
  "content": "Query completed in 42.3s"
}
```

### Querying MongoDB

```javascript
// Connect to MongoDB
use fluidmcp

// View ai-council config
db.fluidmcp_servers.find({"id": "ai-council"}).pretty()

// View runtime state
db.fluidmcp_server_instances.find({"server_id": "ai-council"}).pretty()

// View recent logs
db.fluidmcp_server_logs.find({"server_name": "ai-council"})
  .sort({"timestamp": -1})
  .limit(50)
```

## Security Best Practices

### API Key Storage
- ✅ Keys stored in MongoDB with restricted access
- ✅ Keys masked in all API responses (`****`)
- ✅ Keys never logged or exposed in error messages
- ✅ Keys only visible during initial configuration
- ✅ Use environment variables for key management

### Environment Variable Security
- ✅ Strict validation on key names (uppercase + underscores only)
- ✅ Loose validation on values (allows API key characters)
- ✅ No null bytes or control characters allowed
- ✅ Max 10,000 characters per value
- ✅ Keys encrypted at rest in MongoDB

### Cost Protection
- ✅ Default to 3 models maximum
- ✅ Document 3x cost multiplier clearly
- ✅ Recommend setting OpenRouter spending limits
- ✅ Provide cost calculator in documentation

### Network Security
- ✅ Use HTTPS for OpenRouter API calls
- ✅ Validate SSL certificates
- ✅ No credentials in URL parameters
- ✅ Bearer token authentication for FluidMCP API (optional `--secure` mode)

## Advanced Configuration

### Custom Timeout Values

Adjust timeouts for slow or fast networks:

```json
{
  "command": "uvx",
  "args": [
    "ai-council",
    "--parallel-timeout", "120",  // Wait up to 2 minutes
    "--max-models", "3"
  ]
}
```

### Logging Configuration

Enable debug logging for troubleshooting:

```json
{
  "args": [
    "ai-council",
    "--log-level", "DEBUG"  // Options: DEBUG, INFO, WARNING, ERROR
  ]
}
```

Check logs:
```bash
curl http://localhost:8099/api/servers/ai-council/logs
```

### Multiple ai-council Instances

Run different configurations simultaneously:

```json
{
  "mcpServers": {
    "ai-council-fast": {
      "command": "uvx",
      "args": ["ai-council", "--max-models", "2", "--parallel-timeout", "30"],
      "env": {"OPENROUTER_API_KEY": "..."}
    },
    "ai-council-thorough": {
      "command": "uvx",
      "args": ["ai-council", "--max-models", "5", "--parallel-timeout", "120"],
      "env": {"OPENROUTER_API_KEY": "..."}
    }
  }
}
```

Use case:
- `ai-council-fast` for quick queries (2 models, 30s timeout)
- `ai-council-thorough` for important decisions (5 models, 2min timeout)

## Support & Resources

### Official Resources
- **AI Council GitHub**: https://github.com/0xAkuti/ai-council-mcp
- **PyPI Package**: https://pypi.org/project/ai-council/
- **FluidMCP Docs**: https://github.com/yourusername/fluidmcp

### API Documentation
- **OpenRouter**: https://openrouter.ai/docs
- **OpenAI**: https://platform.openai.com/docs

### Get Help
- **FluidMCP Issues**: https://github.com/yourusername/fluidmcp/issues
- **AI Council Issues**: https://github.com/0xAkuti/ai-council-mcp/issues
- **OpenRouter Support**: https://openrouter.ai/support

## License

AI Council is licensed under its respective license. FluidMCP integration examples are provided as-is for educational purposes.

---

**Ready to get started?** Get your OpenRouter API key at https://openrouter.ai/keys and add ai-council to your FluidMCP instance!
