# FluidMCP - Architecture Diagrams

Visual reference for understanding FluidMCP's architecture.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FLUIDMCP ECOSYSTEM                          │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                  FRONTEND (React SPA)                         │ │
│  │  Port: 8099 (served by FastAPI in both dev & prod)           │ │
│  │                                                               │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │ │
│  │  │Dashboard │ │ Tool     │ │   LLM    │ │  Server  │       │ │
│  │  │          │ │ Runner   │ │Playground│ │  Manage  │       │ │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │ │
│  │       │            │            │            │               │ │
│  │       └────────────┴────────────┴────────────┘               │ │
│  │                           │                                  │ │
│  │                    ┌──────▼──────┐                          │ │
│  │                    │  API Client │                          │ │
│  │                    │  (api.ts)   │                          │ │
│  │                    └──────┬──────┘                          │ │
│  └───────────────────────────┼───────────────────────────────┘ │
│                               │                                  │
│                               │ HTTP/REST                        │
│                               │                                  │
│  ┌───────────────────────────▼───────────────────────────────┐ │
│  │            GATEWAY (FastAPI) - Port 8099                   │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ Management API (/api/servers, /api/models)           │ │ │
│  │  │ - Bearer token auth (secure mode)                    │ │ │
│  │  │ - Rate limiting (optional Redis)                     │ │ │
│  │  │ - Request size limiting (10MB)                       │ │ │
│  │  │ - CORS middleware                                    │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ LLM Proxy (/api/llm/v1/*)                            │ │ │
│  │  │ - OpenAI-compatible endpoints                        │ │ │
│  │  │ - Model routing (vLLM/Replicate/Ollama)             │ │ │
│  │  │ - Streaming support (SSE)                            │ │ │
│  │  │ - Metrics collection                                 │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ Dynamic MCP Routes (/{server}/mcp/tools/*)           │ │ │
│  │  │ - Created at runtime per server                      │ │ │
│  │  │ - Thread-safe stdio communication                    │ │ │
│  │  │ - Automatic header injection                         │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ System (/health, /metrics, /docs)                    │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  └───────────┬───────────────────┬──────────────────┬────────┘ │
│              │                   │                  │           │
│              ▼                   ▼                  ▼           │
│  ┌─────────────────┐ ┌─────────────────┐ ┌────────────────┐  │
│  │  MCP Server 1   │ │  MCP Server 2   │ │  LLM Models    │  │
│  │  (Subprocess)   │ │  (Subprocess)   │ │  (HTTP)        │  │
│  │                 │ │                 │ │                │  │
│  │  stdio pipes    │ │  stdio pipes    │ │  vLLM: 8001    │  │
│  │  JSON-RPC 2.0   │ │  JSON-RPC 2.0   │ │  Replicate API │  │
│  │  Thread lock    │ │  Thread lock    │ │  Ollama: 11434 │  │
│  └─────────────────┘ └─────────────────┘ └────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              MongoDB (Persistence Layer)                  │  │
│  │              Port: 27017 (localhost only)                 │  │
│  │              Railway: uses MONGODB_URI env var            │  │
│  │                                                           │  │
│  │  Collections:                                             │  │
│  │  - servers        (MCP server configs & state)           │  │
│  │  - llm_models     (LLM model configs & state)            │  │
│  │  - tool_cache     (Cached tool schemas)                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Server Startup Sequence

### `fmcp serve` (Production Mode)

```
 START
   │
   ▼
┌──────────────────────────────────┐
│  Parse CLI Arguments             │
│  - Port: 8099 (default)          │
│  - Require persistence flag      │
│  - Bearer token setup            │
└────────────┬─────────────────────┘
             ▼
┌──────────────────────────────────┐
│  Initialize Persistence          │
│  - Connect to MongoDB            │
│  - Retry: 3 attempts             │
│  - Fallback: InMemoryBackend     │
│  - Fail-fast if --require-persist│
└────────────┬─────────────────────┘
             ▼
┌──────────────────────────────────┐
│  Create ServerManager            │
│  - Load configs from DB          │
│  - Initialize state tracking     │
└────────────┬─────────────────────┘
             ▼
┌──────────────────────────────────┐
│  Create FastAPI App              │
│  - Add CORS middleware           │
│  - Add request size limiter      │
│  - Mount management API          │
│  - Mount dynamic MCP router      │
│  - Mount frontend routes         │
│  - Add /health, /metrics         │
└────────────┬─────────────────────┘
             ▼
┌──────────────────────────────────┐
│  Background Tasks                │
│  - Start health monitors         │
│  - Start idle cleanup task       │
│  - Load models from DB           │
└────────────┬─────────────────────┘
             ▼
┌──────────────────────────────────┐
│  Start Uvicorn Server            │
│  - Listen on configured port     │
│  - Log startup message           │
└────────────┬─────────────────────┘
             ▼
          READY
   (API accepting requests)
```

---

## MCP Server Lifecycle

```
NOT_RUNNING
     │
     │ POST /api/servers/{id}/start
     ▼
┌──────────────────────────────────┐
│  STARTING                        │
│  1. Validate config              │
│  2. Spawn subprocess             │
│  3. Initialize (JSON-RPC)        │
│  4. Fetch tools                  │
│  5. Create router                │
│  6. Cache tools in DB            │
└────────────┬─────────────────────┘
             ▼
         RUNNING ◄────┐
             │        │
             │        │ Health check succeeded
             │        │ (if enabled)
             │        │
             │        │
   Process  │        │
   died or  │   ┌────┴─────────────────┐
   SIGTERM  │   │  HEALTH_CHECK        │
             │   │  - Periodic checks   │
             │   │  - Auto-restart on   │
             ▼   │    failure           │
┌──────────────────────────────────┐   │
│  STOPPING                        │   │
│  1. Send SIGTERM                 │   │
│  2. Wait 5 seconds               │   │
│  3. Send SIGKILL if needed       │   │
│  4. Remove router                │   │
│  5. Cleanup resources            │   │
└────────────┬─────────────────────┘   │
             ▼                         │
         STOPPED                       │
             │                         │
             │ POST /api/servers/{id}/restart
             │                         │
             └─────────────────────────┘
```

---

## Tool Execution Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (React)                           │
│                                                                 │
│  User fills form → JsonSchemaForm validates →                  │
│  useToolRunner.runTool() → apiClient.runTool()                │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ HTTP POST /{server}/mcp/tools/call
                           │ {"name": "read_file", "arguments": {...}}
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GATEWAY (FastAPI)                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Router Handler (package_launcher.py)                    │  │
│  │  1. Extract tool name & args                             │  │
│  │  2. Inject HTTP headers                                  │  │
│  │  3. Build JSON-RPC request                               │  │
│  │  4. Acquire thread lock                                  │  │
│  │  5. Start metrics timer                                  │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                     │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            │ stdin.write(json_rpc_request + "\n")
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   MCP SERVER (Subprocess)                       │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  1. Read line from stdin                                 │  │
│  │  2. Parse JSON-RPC                                       │  │
│  │  3. Route to tool handler                                │  │
│  │  4. Execute tool logic                                   │  │
│  │     - read_file("/tmp/test.txt")                        │  │
│  │  5. Build JSON-RPC response                              │  │
│  │  6. Write to stdout                                      │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                     │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            │ stdout.readline() → JSON response
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GATEWAY (FastAPI)                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Response Handler                                        │  │
│  │  1. Parse JSON from stdout                               │  │
│  │  2. Release thread lock                                  │  │
│  │  3. Record metrics (latency, tokens)                     │  │
│  │  4. Return HTTP response                                 │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                     │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            │ HTTP 200 OK
                            │ {"result": {"content": [...]}}
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (React)                           │
│                                                                 │
│  ToolResult.tsx renders response →                             │
│  Save to localStorage (toolHistory) →                          │
│  Show success toast →                                          │
│  Display execution time                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Timing:** ~100-200ms for simple tools (50ms network + 50-150ms execution)

---

## LLM Chat Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER TYPES MESSAGE                           │
│              "Explain quantum computing"                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              FRONTEND (LLMPlayground.tsx)                       │
│                                                                 │
│  State Update:                                                  │
│  messages = [...messages, {role: 'user', content: '...'}]     │
│                                                                 │
│  API Call:                                                      │
│  apiClient.chatCompletion({                                    │
│    model: "llama-2-70b",                                       │
│    messages: messages,                                         │
│    temperature: 0.7,                                           │
│    max_tokens: 1000                                            │
│  })                                                            │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ POST /api/llm/v1/chat/completions
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              GATEWAY (management.py)                            │
│                                                                 │
│  unified_chat_completions():                                   │
│  1. Extract model_id from body                                 │
│  2. Look up in ModelsManager                                   │
│  3. Get provider type (vllm/replicate/ollama)                 │
│  4. Route to appropriate handler                               │
│                                                                 │
└──────────────┬────────────────────────────┬─────────────────────┘
               │                            │
               │ If vLLM                    │ If Replicate
               ▼                            ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│   vLLM (Local Server)    │    │  Replicate (Cloud API)   │
│   Port: 8001             │    │                          │
│                          │    │  POST /v1/predictions    │
│   POST /v1/chat/         │    │  - Create prediction     │
│   completions            │    │  - Poll until complete   │
│                          │    │  - Extract output        │
│   GPU-accelerated        │    │                          │
│   inference              │    │  Pay-per-use             │
│   Local data             │    │  No GPU required         │
└────────────┬─────────────┘    └────────────┬─────────────┘
             │                               │
             │ OpenAI format response        │
             │                               │
             └───────────────┬───────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  GATEWAY (management.py)                        │
│                                                                 │
│  Format Response:                                               │
│  {                                                              │
│    "choices": [{                                                │
│      "message": {                                               │
│        "role": "assistant",                                     │
│        "content": "Quantum computing uses..."                  │
│      }                                                          │
│    }],                                                          │
│    "usage": {                                                   │
│      "prompt_tokens": 10,                                       │
│      "completion_tokens": 50,                                   │
│      "total_tokens": 60                                         │
│    }                                                            │
│  }                                                              │
│                                                                 │
│  Record Metrics: Tokens, latency, success/error                │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ HTTP 200 OK
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              FRONTEND (LLMPlayground.tsx)                       │
│                                                                 │
│  Update State:                                                  │
│  messages = [...messages, {                                     │
│    role: 'assistant',                                           │
│    content: "Quantum computing uses..."                        │
│  }]                                                             │
│                                                                 │
│  Render: Display message in chat UI                            │
│  Save: Store in localStorage (history)                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration Resolution Flow

```
                    CLI Command
                        │
                        ▼
        ┌───────────────────────────────┐
        │   config_resolver.py          │
        │   resolve_from_file()         │
        └───────────┬───────────────────┘
                    │
       ┌────────────┴────────────┐
       │                         │
       ▼                         ▼
 Package String            Local File
 "Author/Pkg@1.0"         config.json
       │                         │
       │                         ├─ Direct config?
       │                         │  {"command": "npx", ...}
       │                         │  → Create temp metadata
       │                         │
       │                         ├─ GitHub repo?
       │                         │  {"github_repo": "owner/repo"}
       │                         │  → Clone to .fmcp-packages/
       │                         │
       │                         └─ Package string?
       │                            "Author/Pkg@1.0"
       │                            → Load from .fmcp-packages/
       │
       └─────────────┬────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  Normalized Config     │
        │  {                     │
        │    "mcpServers": {     │
        │      "name": {         │
        │        "command": "...",│
        │        "args": [...],  │
        │        "env": {...}    │
        │      }                 │
        │    }                   │
        │  }                     │
        └────────────┬───────────┘
                     │
                     ▼
              Launch Servers
```

---

## MCP Communication Protocol

### JSON-RPC Messages

**Tool List Request:**
```json
→ stdin:
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}

← stdout:
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "read_file",
        "description": "Read a file",
        "inputSchema": {...}
      }
    ]
  }
}
```

**Tool Execution Request:**
```json
→ stdin:
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": {
      "path": "/tmp/test.txt",
      "headers": {
        "authorization": "Bearer ...",
        "user-agent": "FluidMCP/1.0"
      }
    }
  }
}

← stdout:
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "File contents here..."
      }
    ]
  }
}
```

**Error Response:**
```json
← stdout:
{
  "jsonrpc": "2.0",
  "id": 2,
  "error": {
    "code": -32603,
    "message": "File not found: /tmp/test.txt",
    "data": {
      "errno": -2,
      "path": "/tmp/test.txt"
    }
  }
}
```

---

## Frontend State Management

```
┌─────────────────────────────────────────────────────────────────┐
│                     COMPONENT HIERARCHY                         │
└─────────────────────────────────────────────────────────────────┘

App.tsx (Router)
  │
  ├─ Dashboard.tsx
  │    └─ useServers() hook
  │         └─ apiClient.listServers()
  │              └─ State: servers[], loading, error
  │                   └─ ServerCard.tsx (per server)
  │
  ├─ ServerDetails.tsx
  │    └─ useServerDetails() hook
  │         └─ apiClient.getServerDetails()
  │              └─ State: server, tools[], logs[], status
  │
  ├─ ToolRunner.tsx
  │    ├─ useToolRunner() hook
  │    │    └─ apiClient.runTool()
  │    │         └─ State: result, loading, history
  │    │
  │    └─ JsonSchemaForm.tsx
  │         └─ React Hook Form + Zod validation
  │              └─ State: formData, errors
  │
  └─ LLMPlayground.tsx
       └─ useLLMModels() hook
            └─ apiClient.listLLMModels()
                 └─ State: models[], selectedModel, messages[]
```

**No global state library (Redux/Zustand)**  
**Each component manages its own state via custom hooks**

---

## Database Schema (MongoDB)

### Collections

**servers** Collection:
```json
{
  "_id": "filesystem",
  "config": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    "env": {}
  },
  "status": "running",
  "pid": 12345,
  "port": null,
  "created_at": "2026-03-24T10:00:00Z",
  "updated_at": "2026-03-24T10:05:00Z"
}
```

**llm_models** Collection:
```json
{
  "_id": "llama-2-70b",
  "config": {
    "type": "replicate",
    "model": "meta/llama-2-70b-chat",
    "api_key": "r8_...",
    "default_params": {
      "temperature": 0.7,
      "max_tokens": 1000
    }
  },
  "status": "healthy",
  "health": {
    "last_check": "2026-03-24T10:10:00Z",
    "consecutive_failures": 0
  },
  "created_at": "2026-03-24T09:00:00Z"
}
```

**tool_cache** Collection:
```json
{
  "server_id": "filesystem",
  "tool_name": "read_file",
  "schema": {
    "name": "read_file",
    "description": "...",
    "inputSchema": {...}
  },
  "cached_at": "2026-03-24T10:05:00Z"
}
```

---

## Security Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       CLIENT REQUEST                            │
│  HTTP Request with "Authorization: Bearer <token>"              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GATEWAY SECURITY LAYERS                      │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 1: CORS Middleware                                 │ │
│  │  - Check Origin header                                    │ │
│  │  - Validate against FMCP_ALLOWED_ORIGINS                  │ │
│  │  - Default: Deny all (secure by default)                  │ │
│  └───────────────────────────┬───────────────────────────────┘ │
│                               ▼                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 2: Request Size Limiter                            │ │
│  │  - Check Content-Length header                            │ │
│  │  - Reject if > 10MB (configurable)                        │ │
│  │  - Prevent DoS via large payloads                         │ │
│  └───────────────────────────┬───────────────────────────────┘ │
│                               ▼                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 3: Bearer Token Auth (Optional)                    │ │
│  │  - Extract token from Authorization header                │ │
│  │  - Compare with FMCP_BEARER_TOKEN                         │ │
│  │  - Return 401 if invalid                                  │ │
│  │  - Skipped if FMCP_BEARER_TOKEN not set                   │ │
│  └───────────────────────────┬───────────────────────────────┘ │
│                               ▼                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 4: Rate Limiting (Optional - Redis)                │ │
│  │  - Composite key: (token + IP)                            │ │
│  │  - Limits: 60 req/min (inference)                         │ │
│  │  -        10 req/min (registration)                       │ │
│  │  -        20 req/min (updates)                            │ │
│  │  - Return 429 if exceeded                                 │ │
│  └───────────────────────────┬───────────────────────────────┘ │
│                               ▼                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 5: Input Validation                                │ │
│  │  - Pydantic model validation                              │ │
│  │  - JSON Schema validation (for tools)                     │ │
│  │  - Type checking                                          │ │
│  └───────────────────────────┬───────────────────────────────┘ │
│                               ▼                                 │
│                      ROUTE HANDLER                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Additional Security:**
- **Command sanitization:** Redacts API keys in logs
- **Environment filtering:** Only allowlisted env vars passed to subprocesses
- **Log file permissions:** `0o600` (owner read/write only)
- **Path sanitization:** Prevents directory traversal attacks
- **Process isolation:** Each MCP server in separate subprocess

---

## Monitoring & Observability

```
┌─────────────────────────────────────────────────────────────────┐
│                       METRICS COLLECTION                        │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│  Request Arrives │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────┐
│  RequestTimer Context Manager   │
│  - Start timestamp              │
│  - Generate request_id          │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Execute Handler                │
│  - Route logic                  │
│  - MCP/LLM call                 │
│  - Error handling               │
└────────┬────────────────────────┘
         │
         │ Success or Exception?
         │
    ┌────┴────┐
    ▼         ▼
 Success   Exception
    │         │
    │         ▼
    │    ┌─────────────────────┐
    │    │ Record Error        │
    │    │ - Status code       │
    │    │ - Error type        │
    │    └─────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Record Metrics                 │
│  - Request count++              │
│  - Latency histogram            │
│  - Token usage (if LLM)         │
│  - End timestamp                │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Prometheus Endpoint            │
│  GET /metrics                   │
│  - fluidmcp_requests_total      │
│  - fluidmcp_request_duration    │
│  - fluidmcp_errors_total        │
│  - fluidmcp_llm_tokens_total    │
│  - fluidmcp_servers_active      │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Grafana Dashboard (Optional)   │
│  - Request rate graphs          │
│  - Latency percentiles          │
│  - Error rate charts            │
│  - Token usage tracking         │
└─────────────────────────────────┘
```

**Key Metrics:**
- `fluidmcp_requests_total{endpoint, status}` - Total requests
- `fluidmcp_request_duration_seconds{endpoint}` - Latency histogram
- `fluidmcp_errors_total{endpoint, status}` - Error counts
- `fluidmcp_llm_tokens_total{model, type}` - Token usage
- `fluidmcp_servers_active` - Number of running servers

---

## File System Layout

```
~/.fluidmcp/                           # User data directory
├── logs/                              # All log files
│   ├── {server_id}_stderr.log        # MCP server errors
│   ├── {server_id}_stdout.log        # MCP server output
│   └── llm_{model_id}_stderr.log     # LLM model logs
│
└── packages/                          # Installed packages (alias)
    └── (symlink to .fmcp-packages)

.fmcp-packages/                        # Package installation root
├── Author/                            # Package by author
│   └── Package/                       # Package name
│       └── 1.0/                       # Version
│           ├── metadata.json          # MCP server config
│           ├── package.json           # npm package (if Node)
│           └── ...                    # Package files
│
├── owner/                             # GitHub repos
│   └── repo/                          # Repo name
│       └── main/                      # Branch
│           ├── metadata.json          # Extracted or existing
│           ├── README.md              # Source for auto-extraction
│           └── ...                    # Repo files
│
└── .temp_servers/                     # Temporary direct configs
    └── server_abc123/                 # Generated ID
        └── metadata.json              # Created from direct config
```

---

## Error Handling & Recovery

### LLM Error Recovery

```
┌─────────────────┐
│  LLM Process    │
│  Running        │
└────────┬────────┘
         │
         │ Health check every 30s
         ▼
┌─────────────────────────────┐
│  HTTP GET /health or        │
│  /v1/models                 │
└─────────┬───────────────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
 Success     Failure
    │           │
    │           ▼
    │      ┌─────────────────────┐
    │      │ Consecutive         │
    │      │ failures++          │
    │      └─────┬───────────────┘
    │            │
    │            │ >= threshold (2)?
    │            │
    │            ▼
    │      ┌─────────────────────┐
    │      │ Trigger Restart     │
    │      │ 1. SIGTERM          │
    │      │ 2. Wait 5s          │
    │      │ 3. SIGKILL          │
    │      │ 4. Spawn new process│
    │      │ 5. Exponential      │
    │      │    backoff delay    │
    │      └─────┬───────────────┘
    │            │
    │            │ restart_count++
    │            │
    │            │ < max_restarts (3)?
    │            │
    │            ▼
    │     ┌──────────────────────┐
    │     │ Continue Monitoring  │
    │     └──────────────────────┘
    │
    └────────► Continue ────────────┐
                                    │
                              ┌─────▼──────┐
                              │   RUNNING  │
                              └────────────┘
```

**Restart Policies:**
- `"on-failure"` - Restart only on non-zero exit
- `"always"` - Restart on any termination
- `"no"` - No automatic restart (default)

---

## Data Flow Summary

### User Action → Response

```
1. USER CLICKS BUTTON
   ↓
2. React Component Handler
   ↓
3. Custom Hook (e.g., useToolRunner)
   ↓
4. API Client (api.ts)
   ↓
5. HTTP Request (fetch)
   ↓
6. FastAPI Gateway (management.py)
   ↓
7. Route Handler
   ↓
8a. MCP Server (stdio)         8b. LLM Model (HTTP)
   ↓                            ↓
9. JSON-RPC Response           9. OpenAI Response
   ↓                            ↓
10. Gateway Processing (metrics, formatting)
   ↓
11. HTTP Response
   ↓
12. API Client Parsing
   ↓
13. Hook State Update
   ↓
14. Component Re-render
   ↓
15. USER SEES RESULT
```

---

## Port Usage Reference

| Port | Service | Mode | Configurable |
|------|---------|------|--------------|
| `8090` | Single package server | `fmcp run author/pkg` | Via `MCP_CLIENT_SERVER_PORT` |
| `8099` | Unified gateway + frontend | `fmcp run all` / `fmcp serve` (dev & prod) | Via `MCP_CLIENT_SERVER_ALL_PORT` / `--port` |
| `8001` | vLLM server (example) | LLM inference | Via `--port` in vLLM args |
| `11434` | Ollama server | LLM inference | Ollama default |
| `27017` | MongoDB | Persistence (localhost only) | MongoDB default / `MONGODB_URI` in Railway |

---

## Useful Environment Variables

```bash
# S3 Credentials (for --master mode)
export S3_BUCKET_NAME="my-bucket"
export S3_ACCESS_KEY="..."
export S3_SECRET_KEY="..."
export S3_REGION="us-east-1"

# Registry Access
export MCP_FETCH_URL="https://registry.fluidmcp.com/fetch-mcp-package"
export MCP_TOKEN="your-registry-token"

# GitHub Access
export FMCP_GITHUB_TOKEN="ghp_..."
export GITHUB_TOKEN="ghp_..."  # Alternative

# Replicate API
export REPLICATE_API_TOKEN="r8_..."

# MongoDB
export MONGODB_URI="mongodb://localhost:27017"

# FluidMCP Server
export FMCP_BEARER_TOKEN="your-secure-token"  # Auth token
export FMCP_ALLOWED_ORIGINS="https://app.example.com"  # CORS
export MCP_CLIENT_SERVER_PORT="8090"           # Single mode port
export MCP_CLIENT_SERVER_ALL_PORT="8099"       # Unified port
export MCP_PORT_RELEASE_TIMEOUT="5"            # Port release wait
```

---

**For detailed explanations, see:** [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md)
