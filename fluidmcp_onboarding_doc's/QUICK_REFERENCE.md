# FluidMCP - Quick Reference Guide

**For developers who need quick answers**

---

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt && pip install -e .

# Run sample config (no install needed)
fmcp run examples/sample-config.json --file --start-server

# Access UI
open http://localhost:8099
```

---

## 📁 Where to Find Things

| What | Where |
|------|-------|
| **CLI entry point** | [fluidmcp/cli/cli.py](../fluidmcp/cli/cli.py) |
| **FastAPI server** | [fluidmcp/cli/server.py](../fluidmcp/cli/server.py) |
| **API routes** | [fluidmcp/cli/api/management.py](../fluidmcp/cli/api/management.py) |
| **MCP server launcher** | [fluidmcp/cli/services/package_launcher.py](../fluidmcp/cli/services/package_launcher.py) |
| **Server lifecycle** | [fluidmcp/cli/services/server_manager.py](../fluidmcp/cli/services/server_manager.py) |
| **LLM orchestration** | [fluidmcp/cli/services/llm_launcher.py](../fluidmcp/cli/services/llm_launcher.py) |
| **Frontend entry** | [fluidmcp/frontend/src/App.tsx](../fluidmcp/frontend/src/App.tsx) |
| **API client** | [fluidmcp/frontend/src/services/api.ts](../fluidmcp/frontend/src/services/api.ts) |
| **Custom hooks** | [fluidmcp/frontend/src/hooks/](../fluidmcp/frontend/src/hooks/) |
| **Sample configs** | [examples/](../examples/) |
| **Tests** | [tests/](../tests/) |
| **Logs** | `~/.fluidmcp/logs/` |
| **Packages** | `.fmcp-packages/` |

---

## 🔧 Common Commands

### CLI Commands

```bash
# Install package from registry
fmcp install Author/Package@1.0

# Run single package
fmcp run Author/Package@1.0 --start-server

# Run all installed packages
fmcp run all --start-server

# Run from config file
fmcp run config.json --file --start-server

# Clone and run from GitHub
fmcp github owner/repo --github-token TOKEN --start-server

# Start API server (production mode)
fmcp serve --port 8099

# List installed packages
fmcp list

# Validate configuration
fmcp validate config.json --file

# Show version
fmcp --version
```

### API Calls

```bash
# Set bearer token (if in secure mode)
export TOKEN="your-bearer-token"

# List servers
curl http://localhost:8099/api/servers \
  -H "Authorization: Bearer $TOKEN"

# Add server
curl -X POST http://localhost:8099/api/servers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "my-server",
    "config": {
      "command": "npx",
      "args": ["-y", "@package/server"],
      "env": {}
    }
  }'

# Start server
curl -X POST http://localhost:8099/api/servers/my-server/start \
  -H "Authorization: Bearer $TOKEN"

# Stop server
curl -X POST http://localhost:8099/api/servers/my-server/stop \
  -H "Authorization: Bearer $TOKEN"

# Get server logs
curl http://localhost:8099/api/servers/my-server/logs?lines=100 \
  -H "Authorization: Bearer $TOKEN"

# List tools
curl http://localhost:8099/my-server/mcp/tools/list

# Execute tool
curl -X POST http://localhost:8099/my-server/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "tool_name",
    "arguments": {"param": "value"}
  }'

# Chat completion (OpenAI-compatible)
curl -X POST http://localhost:8099/api/llm/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-2-70b",
    "messages": [{"role": "user", "content": "Hello"}],
    "temperature": 0.7,
    "max_tokens": 100
  }'
```

### Frontend Development

```bash
# Start backend
fmcp serve --port 8099

# Start frontend dev server (separate terminal)
cd fluidmcp/frontend
npm install
npm run dev
# Opens http://localhost:5173
```

---

## 🏗️ Architecture Cheat Sheet

### Request Flow

```
Browser → React Component → Custom Hook → API Client (api.ts) →
HTTP Request → FastAPI Gateway (management.py) →
MCP Server (subprocess via stdio) → Response → UI Update
```

### Key Ports

| Port | Purpose |
|------|---------|
| `8090` | Single package mode (legacy) |
| `8099` | Unified gateway / serve mode (production) |
| `5173` | Frontend dev server (Vite) |
| `27017` | MongoDB (if using persistence) |

### File Structure Quick Map

```
Backend Entry:     fluidmcp/cli/cli.py → server.py
API Routes:        fluidmcp/cli/api/management.py
MCP Launcher:      fluidmcp/cli/services/package_launcher.py
Server Manager:    fluidmcp/cli/services/server_manager.py
Frontend Entry:    fluidmcp/frontend/src/App.tsx
API Client:        fluidmcp/frontend/src/services/api.ts
```

---

## 🔍 Debugging Tips

### Backend Debugging

```bash
# Check logs
tail -f ~/.fluidmcp/logs/{server_id}_stderr.log

# Test JSON-RPC directly
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | npx -y @package/server

# Check port usage
lsof -i :8099

# View running processes
ps aux | grep -E "fmcp|npx|vllm"

# Check MongoDB connection
mongosh $MONGODB_URI --eval "db.adminCommand('ping')"
```

### Frontend Debugging

```bash
# Browser console logs
# React DevTools
# Network tab in DevTools

# Check API calls
# Open http://localhost:8099/docs (Swagger UI)

# Test API endpoints manually
curl -X GET http://localhost:8099/api/servers
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Port already in use | `fmcp run --force-reload` or `lsof -ti:8099 \| xargs kill -9` |
| Server won't start | Check logs: `~/.fluidmcp/logs/{server_id}_stderr.log` |
| MongoDB connection failed | Verify `MONGODB_URI`, check MongoDB is running |
| Tool execution timeout | Increase timeout in metadata.json or code |
| Frontend can't connect | Check CORS settings, verify backend is running |

---

## 📦 Configuration Formats

### Direct Server Config (No Installation)

```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@package/server"],
      "env": {"VAR": "value"}
    }
  }
}
```

### GitHub Repository

```json
{
  "mcpServers": {
    "server-name": {
      "github_repo": "owner/repo",
      "branch": "main",
      "github_token": "${GITHUB_TOKEN}",
      "env": {}
    }
  }
}
```

### Package String

```json
{
  "mcpServers": {
    "server-name": "Author/Package@1.0"
  }
}
```

### With LLM Models

```json
{
  "mcpServers": { /* ... */ },
  "llmModels": {
    "vllm": {
      "type": "vllm",
      "command": "vllm",
      "args": ["serve", "facebook/opt-125m", "--port", "8001"],
      "endpoints": {"base_url": "http://localhost:8001/v1"}
    },
    "replicate": {
      "type": "replicate",
      "model": "meta/llama-2-70b-chat",
      "api_key": "${REPLICATE_API_TOKEN}"
    }
  }
}
```

---

## 🧪 Testing Checklist

- [ ] Run pytest: `pytest`
- [ ] Check coverage: `pytest --cov=fluidmcp`
- [ ] Test sample config: `fmcp run examples/sample-config.json --file --start-server`
- [ ] Test UI: Open http://localhost:8099, navigate pages
- [ ] Test tool execution: Run a tool via UI
- [ ] Test chat: Send message in LLM Playground
- [ ] Test logs: View server logs in UI
- [ ] Test health endpoint: `curl http://localhost:8099/health`
- [ ] Test metrics: `curl http://localhost:8099/metrics`

---

## 🎯 Development Workflow

### Feature Development

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes
3. Run tests: `pytest`
4. Test manually with sample config
5. Update documentation if needed
6. Commit and push
7. Create pull request

### Adding a New MCP Tool Endpoint

1. Add route to [management.py](../fluidmcp/cli/api/management.py)
2. Add TypeScript method to [api.ts](../fluidmcp/frontend/src/services/api.ts)
3. Create custom hook if complex logic needed
4. Use hook in React component
5. Add tests to [tests/test_*.py](../tests/)

### Adding a New Frontend Page

1. Create component in [pages/](../fluidmcp/frontend/src/pages/)
2. Add route to [App.tsx](../fluidmcp/frontend/src/App.tsx)
3. Add navigation link to [Navbar.tsx](../fluidmcp/frontend/src/components/Navbar.tsx)
4. Create custom hook if API interaction needed
5. Test in browser

---

## 🔑 Key Concepts

**MCP Server:** JSON-RPC subprocess that exposes tools via stdio

**Tool:** A function with JSON Schema input definition

**Gateway:** FastAPI proxy that routes HTTP → MCP servers

**Dynamic Routing:** Routes created at runtime as servers start

**Tool Execution:** HTTP → Gateway → JSON-RPC (stdio) → MCP Server → Response

**Persistence:** MongoDB storage for server/model configs (survives restarts)

**Unified Endpoint:** Single endpoint routing to multiple LLM backends

---

## 💡 Pro Tips

- **Use Swagger UI** (`/docs`) to explore API endpoints
- **Check logs first** when debugging server issues
- **Use `--force-reload`** to kill stuck processes
- **Test with sample configs** before writing your own
- **Read test files** to understand expected behavior
- **Enable debug logging** for detailed troubleshooting
- **Use AbortController** in frontend for cancellable requests
- **Check MongoDB** if server configs disappear after restart
- **Set FMCP_BEARER_TOKEN** in Railway to prevent token regeneration

---

**Last Updated:** March 24, 2026  
**For detailed documentation, see:** [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md)
