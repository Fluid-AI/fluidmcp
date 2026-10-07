# FluidMCP — Data Flow Diagram

> Traces how server configuration data flows from HTTP request through API, DatabaseManager, and ServerManager to running MCP server processes.

## Overview

This diagram shows the complete data flow when a user adds and starts an MCP server via the REST API. Data enters as JSON, gets validated, transformed between flat/nested formats, persisted to MongoDB, and finally used to spawn a process.

## Data Flow

```
╔══ INPUT ═══════════════════════════════════════════════════════════════╗
║                                                                         ║
║  [ HTTP POST /api/servers ]  ──►  [ AddServerRequest JSON ]           ║
║  fluidmcp/cli/api/management.py · add_server()                         ║
║                                                                         ║
║  {                                                                      ║
║    "server_id": "filesystem",                                          ║
║    "config": {                                                         ║
║      "command": "npx",                                                 ║
║      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],║
║      "env": {}                                                         ║
║    }                                                                   ║
║  }                                                                     ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝
                              │
                              ▼
╔══ VALIDATION ═══════════════════════════════════════════════════════════╗
║                                                                         ║
║  ┌──────────────────────────────────┐                                  ║
║  │  authenticate_request()          │                                  ║
║  │  management.py:security          │                                  ║
║  └──────────────────────────────────┘                                  ║
║                    │                                                    ║
║         < bearer token valid? >                                        ║
║         [yes] │       [no] ──► 401 HTTPException                       ║
║               │                                                         ║
║               ▼                                                         ║
║  ┌──────────────────────────────────┐                                  ║
║  │  validate_server_config()        │                                  ║
║  │  validators.py                   │                                  ║
║  └──────────────────────────────────┘                                  ║
║                    │                                                    ║
║         < config valid? >                                              ║
║         [yes] │       [no] ──► 422 HTTPException                       ║
║               │                                                         ║
╚═══════════════╪════════════════════════════════════════════════════════╝
                │
                ▼
╔══ TRANSFORM ════════════════════════════════════════════════════════════╗
║                                                                         ║
║  [ Flat Config Format ]  ──►  [ Nested mcp_config Format ]            ║
║  management.py                DatabaseManager.save_server_config()     ║
║                                                                         ║
║  Flat (ServerManager uses this):                                       ║
║  {                                                                      ║
║    "id": "filesystem",                                                 ║
║    "command": "npx",                                                   ║
║    "args": [...],                                                      ║
║    "env": {}                                                           ║
║  }                                                                     ║
║                                                                         ║
║  Nested (MongoDB stores this):                                         ║
║  {                                                                      ║
║    "server_id": "filesystem",                                          ║
║    "mcp_config": {                                                     ║
║      "command": "npx",                                                 ║
║      "args": [...],                                                    ║
║      "env": {}                                                         ║
║    }                                                                   ║
║  }                                                                     ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝
                              │
                              ▼
╔══ PERSISTENCE ══════════════════════════════════════════════════════════╗
║                                                                         ║
║  ┌──────────────────────────────────┐                                  ║
║  │  DatabaseManager.save_           │                                  ║
║  │  server_config()                 │                                  ║
║  │  repositories/database.py        │                                  ║
║  └──────────────────────────────────┘                                  ║
║                    │                                                    ║
║                    ▼                                                    ║
║  [ MongoDB Collection: fluidmcp_servers ]                              ║
║  motor async driver · async insert_one()                               ║
║                                                                         ║
║  Document structure:                                                    ║
║  {                                                                      ║
║    "_id": ObjectId(...),                                               ║
║    "server_id": "filesystem",                                          ║
║    "mcp_config": { /* nested format */ },                             ║
║    "created_at": ISODate(...),                                         ║
║    "updated_at": ISODate(...)                                          ║
║  }                                                                     ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝
                              │
                              ▼
╔══ REGISTRATION ═════════════════════════════════════════════════════════╗
║                                                                         ║
║  ┌──────────────────────────────────┐                                  ║
║  │  ServerManager.configs[id] =     │                                  ║
║  │  flat_config                     │                                  ║
║  │  server_manager.py               │                                  ║
║  └──────────────────────────────────┘                                  ║
║                                                                         ║
║  In-memory registry (Dict[str, Dict[str, Any]]):                      ║
║  {                                                                      ║
║    "filesystem": {                                                     ║
║      "id": "filesystem",                                               ║
║      "command": "npx",                                                 ║
║      "args": [...],                                                    ║
║      "env": {}                                                         ║
║    }                                                                   ║
║  }                                                                     ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝
                              │
                              │ (if autostart=true or explicit /start)
                              ▼
╔══ PROCESS LAUNCH ═══════════════════════════════════════════════════════╗
║                                                                         ║
║  ┌──────────────────────────────────┐                                  ║
║  │  ServerManager.start()           │                                  ║
║  │  server_manager.py               │                                  ║
║  └──────────────────────────────────┘                                  ║
║                    │                                                    ║
║                    ▼                                                    ║
║  [ Build subprocess command from flat config ]                         ║
║                    │                                                    ║
║                    ▼                                                    ║
║  ┌──────────────────────────────────┐                                  ║
║  │  subprocess.Popen(                │                                  ║
║  │    cmd=["npx", "-y", "..."],     │                                  ║
║  │    env={...},                    │                                  ║
║  │    stdin=PIPE, stdout=PIPE       │                                  ║
║  │  )                               │                                  ║
║  │  Python subprocess module        │                                  ║
║  └──────────────────────────────────┘                                  ║
║                    │                                                    ║
║                    ▼                                                    ║
║  [ Running MCP Server Process ]                                        ║
║  PID: 12345                                                            ║
║  stdin/stdout: JSON-RPC over stdio                                     ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝
                              │
                              ▼
╔══ INITIALIZATION ═══════════════════════════════════════════════════════╗
║                                                                         ║
║  ┌──────────────────────────────────┐                                  ║
║  │  initialize_mcp_server()         │                                  ║
║  │  package_launcher.py             │                                  ║
║  └──────────────────────────────────┘                                  ║
║                    │                                                    ║
║     < transport type? >                                                ║
║                    │                                                    ║
║      ┌─────────────┴─────────────┐                                     ║
║      │                           │                                     ║
║    [stdio]                     [sse/http]                              ║
║      │                           │                                     ║
║      ▼                           ▼                                     ║
║  JSON-RPC                    TCP port poll                             ║
║  handshake                   (asyncio.open_connection)                 ║
║      │                           │                                     ║
║      └─────────────┬─────────────┘                                     ║
║                    │                                                    ║
║                    ▼                                                    ║
║  [ Server Initialized ]                                                ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝
                              │
                              ▼
╔══ OUTPUT ═══════════════════════════════════════════════════════════════╗
║                                                                         ║
║  [ HTTP Response 201 ]                                                 ║
║  management.py · add_server() return                                   ║
║                                                                         ║
║  {                                                                      ║
║    "message": "Server added successfully",                             ║
║    "server_id": "filesystem",                                          ║
║    "status": "running",                                                ║
║    "pid": 12345                                                        ║
║  }                                                                     ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝
```

## Phase Breakdown

### Input
Raw HTTP POST request with JSON body containing `server_id` and `config`. Request arrives at FastAPI endpoint `/api/servers`.

### Validation
1. **Authentication**: Bearer token checked against `FMCP_BEARER_TOKEN` (if secure mode enabled)
2. **Schema Validation**: Pydantic models validate request structure
3. **Config Validation**: `validate_server_config()` checks required fields (`command`, `args`)
4. **Duplicate Check**: Verify `server_id` doesn't already exist in database

Failures result in HTTP 401 (auth failure), 422 (validation failure), or 409 (duplicate).

### Transform
DatabaseManager converts between two config formats:
- **Flat format**: Used by ServerManager for process spawning (`id`, `command`, `args`, `env` at top level)
- **Nested format**: Stored in MongoDB (`server_id` + `mcp_config` wrapper)

This transformation is **critical** — ServerManager always expects flat format, MongoDB always stores nested format.

### Persistence
Data is saved to MongoDB collection `fluidmcp_servers` using motor async driver. Document includes:
- `_id`: MongoDB ObjectId
- `server_id`: Unique server identifier
- `mcp_config`: Nested config structure
- `created_at`, `updated_at`: Timestamps

DatabaseManager handles async insert and error handling (e.g., duplicate key errors).

### Registration
After DB save succeeds, flat config is stored in ServerManager's in-memory registry (`self.configs` dict). This registry is used for all subsequent process operations (start/stop/restart).

### Process Launch
When server is started (autostart or explicit `/start` call):
1. ServerManager builds subprocess command from flat config
2. `subprocess.Popen()` spawns the MCP server process
3. Process tracked in `self.processes` dict with PID
4. stdin/stdout pipes opened for JSON-RPC communication (if stdio transport)

### Initialization
`initialize_mcp_server()` verifies the server is ready:
- **stdio transport**: Performs JSON-RPC handshake over stdin/stdout
- **sse/http transport**: Polls TCP port using `asyncio.open_connection()`

Initialization timeout (default 30s) prevents hanging on failed servers.

### Output
HTTP 201 response returned with server details including `server_id`, `status`, and `pid`. Client can now use the server via `/api/servers/{server_id}/mcp` endpoint.

## Data Flow Summary

| Step | Component | File | Function | Data In | Data Out |
|------|-----------|------|----------|---------|----------|
| 1 | API Endpoint | api/management.py | add_server() | AddServerRequest JSON | — |
| 2 | Authentication | api/management.py | security check | Bearer token | 401 or continue |
| 3 | Validation | api/validators.py | validate_server_config() | config dict | bool, error |
| 4 | Transform | repositories/database.py | save_server_config() | flat config | nested config |
| 5 | Database | repositories/database.py | motor insert_one() | nested config | ObjectId |
| 6 | Registry | services/server_manager.py | self.configs[id] = ... | flat config | — |
| 7 | Process Launch | services/server_manager.py | start() | flat config | Popen object |
| 8 | Initialization | services/package_launcher.py | initialize_mcp_server() | Popen, config | success/failure |
| 9 | Response | api/management.py | return JSONResponse | server state | HTTP 201 JSON |

## Key Transformations

### Flat → Nested (Database Save)
```python
# Input (flat, from API):
{
  "id": "filesystem",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
  "env": {}
}

# Output (nested, to MongoDB):
{
  "server_id": "filesystem",
  "mcp_config": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    "env": {}
  }
}
```

### Nested → Flat (Database Load)
```python
# Input (nested, from MongoDB):
{
  "server_id": "filesystem",
  "mcp_config": {
    "command": "npx",
    "args": [...],
    "env": {}
  }
}

# Output (flat, to ServerManager):
{
  "id": "filesystem",
  "command": "npx",
  "args": [...],
  "env": {}
}
```

## Error Paths

| Error | Where | Response |
|-------|-------|----------|
| Missing bearer token | API auth check | 401 Unauthorized |
| Invalid JSON schema | Pydantic validation | 422 Unprocessable Entity |
| Missing required fields | validate_server_config() | 422 with details |
| Duplicate server_id | MongoDB insert | 409 Conflict |
| Process spawn failure | subprocess.Popen() | 500 with sanitized error |
| Initialization timeout | initialize_mcp_server() | 500 "Server failed to initialize" |

All errors logged via loguru with sanitized messages (no credential leakage).
