# MCP Server Lifecycle — Key Flow

> Shows the essential 6-step path from HTTP request to running MCP server process ready to handle requests.

**Key steps:** HTTP Request → Validate Config → Persist to MongoDB → Register in Memory → Spawn Process → Initialize → Ready

## Flow Diagram

```
  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
  │  1. Receive      │──►  │  2. Validate     │──►  │  3. Persist      │
  │  HTTP Request    │     │  & Authenticate  │     │  to MongoDB      │
  │  api/management  │     │  validators.py   │     │  database.py     │
  │  .py             │     │  + auth check    │     │  save_server_    │
  │  add_server()    │     │                  │     │  config()        │
  └──────────────────┘     └──────────────────┘     └──────────────────┘
                                                              │
                                                              ▼
  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
  │  6. Server Ready │◄──  │  5. Initialize   │◄──  │  4. Spawn        │
  │  Handle MCP      │     │  MCP Server      │     │  Subprocess      │
  │  Requests        │     │  package_        │     │  server_manager  │
  │  /api/servers/   │     │  launcher.py     │     │  .py             │
  │  {id}/mcp        │     │  initialize_mcp_ │     │  subprocess.     │
  │                  │     │  server()        │     │  Popen()         │
  └──────────────────┘     └──────────────────┘     └──────────────────┘
```

## Notes

- **Steps 1-3**: Configuration and persistence phase — server definition saved to MongoDB
- **Steps 4-5**: Process lifecycle phase — subprocess spawned and initialized
- **Step 6**: Operational phase — server ready to handle MCP requests via stdio or SSE

## Error Exits

- **Step 2**: Validation failure → 422 Unprocessable Entity (config invalid)
- **Step 2**: Auth failure → 401 Unauthorized (bearer token missing/invalid)
- **Step 3**: Duplicate server_id → 409 Conflict (already exists)
- **Step 4**: Process spawn failure → 500 Internal Server Error (command not found)
- **Step 5**: Initialization timeout → 500 Internal Server Error (server didn't respond within 30s)

## Step Summary

| Step | Name | File | Function | Role |
|------|------|------|----------|------|
| 1 | Receive Request | api/management.py | add_server() | Parse HTTP POST with server config |
| 2 | Validate & Auth | api/validators.py + management.py | validate_server_config() + security | Check config validity and bearer token |
| 3 | Persist to MongoDB | repositories/database.py | save_server_config() | Save nested config to fluidmcp_servers collection |
| 4 | Spawn Subprocess | services/server_manager.py | start() + subprocess.Popen() | Launch MCP server process (npx, python, etc.) |
| 5 | Initialize MCP | services/package_launcher.py | initialize_mcp_server() | JSON-RPC handshake or TCP port poll |
| 6 | Server Ready | api/management.py | return 201 + forward_to_mcp() | Server operational, ready for MCP requests |

## Decision Point

```
< transport type? >
  [stdio] ──► JSON-RPC handshake via stdin/stdout
  [sse/http] ──► TCP port poll (asyncio.open_connection)
```

This decision happens in Step 5 (`initialize_mcp_server()`). The transport type is detected from the server config:
- **stdio** (default): Traditional MCP servers that communicate via stdin/stdout JSON-RPC
- **sse/http**: Web-based MCP servers (uvicorn, starlette) that expose SSE or HTTP endpoints

## Detailed Step Breakdown

### 1. Receive HTTP Request
- **Input**: `POST /api/servers` with JSON body `{"server_id": "...", "config": {...}}`
- **Processing**: FastAPI endpoint receives request, parses JSON body into `AddServerRequest` Pydantic model
- **Output**: Validated request object passed to handler

### 2. Validate & Authenticate
- **Input**: Request object + Bearer token from `Authorization` header
- **Processing**:
  - Check bearer token against `FMCP_BEARER_TOKEN` environment variable
  - Validate config structure (required fields: `command`, `args`)
  - Check for duplicate `server_id` in database
- **Output**: Validated config or HTTP exception (401, 422, 409)

### 3. Persist to MongoDB
- **Input**: Validated flat config
- **Processing**:
  - Convert flat config to nested `mcp_config` format
  - Insert document into `fluidmcp_servers` collection
  - Add timestamps (`created_at`, `updated_at`)
- **Output**: MongoDB ObjectId confirming successful save

### 4. Spawn Subprocess
- **Input**: Flat config from in-memory registry
- **Processing**:
  - Build command array: `[command] + args`
  - Set environment variables from config
  - Call `subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, env=env)`
- **Output**: Process object with PID

### 5. Initialize MCP Server
- **Input**: Process object + config (including transport type)
- **Processing**:
  - **stdio**: Send JSON-RPC initialization request over stdin, wait for response on stdout
  - **sse/http**: Poll TCP port using `asyncio.open_connection()` until server accepts connections
  - Timeout after 30 seconds if initialization fails
- **Output**: Success (server initialized) or timeout error

### 6. Server Ready
- **Input**: Initialized server with PID
- **Processing**:
  - Store PID in `ServerManager.processes` dict
  - Record start time in `ServerManager.start_times` dict
  - Return HTTP 201 response with server details
- **Output**: Server operational, can receive MCP requests at `/api/servers/{id}/mcp`

## Common Patterns

### Normal Flow (Happy Path)
```
HTTP Request → Validate → Persist → Spawn → Initialize → Ready
                                                           ↓
                                                    Serve MCP requests
```

### Error Recovery Flow
```
HTTP Request → Validate → Persist → Spawn → Initialize → Timeout
                                                ↓
                                             Terminate process
                                                ↓
                                       Return 500 error to client
```

### Restart Flow
```
POST /api/servers/{id}/restart
    ↓
Stop existing process (SIGTERM)
    ↓
Remove from processes dict
    ↓
Re-run steps 4-6 (Spawn → Initialize → Ready)
```

## State Transitions

```
[Configured] ──start()──► [Starting] ──initialized──► [Running]
      ▲                        │                           │
      │                        │ spawn failure             │
      │                        ▼                           │
      │                   [Failed]                         │
      │                                                    │
      └───────────────────────stop()────────────────────────┘
                                │
                                ▼
                           [Stopped]
```

## Time Estimates

| Step | Typical Duration | Notes |
|------|------------------|-------|
| 1-3 | < 100ms | HTTP + DB operations (async) |
| 4 | 100-500ms | Process spawn varies by command |
| 5 | 1-10s | Depends on model loading time (vLLM can take 30s+) |
| Total | 1-10s | Typical successful server start |

For large LLM models (vLLM with 70B parameters), initialization (Step 5) can take 30+ seconds due to model loading into GPU memory.

## Critical Files

| File | Lines | Key Contribution |
|------|-------|------------------|
| `api/management.py` | 800+ | REST API endpoints, request routing |
| `services/server_manager.py` | 600+ | Process lifecycle orchestration |
| `repositories/database.py` | 400+ | MongoDB persistence layer |
| `services/package_launcher.py` | 200+ | MCP initialization logic |
| `api/validators.py` | 300+ | Config validation functions |

Start reading at `api/management.py:add_server()` and follow the call chain through these files to understand the complete flow.
