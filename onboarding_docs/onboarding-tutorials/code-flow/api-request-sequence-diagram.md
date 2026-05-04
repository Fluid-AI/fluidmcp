# FluidMCP API Request — Sequence Diagram

> Shows step-by-step interactions between Client, API, ServerManager, DatabaseManager, and subprocess when adding and starting an MCP server.

## Participants

| Actor | File | Key Function |
|-------|------|-------------|
| Client | — | HTTP caller (curl, browser, SDK) |
| API Layer | api/management.py | add_server(), start_server() |
| ServerManager | services/server_manager.py | start(), initialize() |
| DatabaseManager | repositories/database.py | save_server_config(), get_server_config() |
| Subprocess | — | MCP server process (npx, python, etc.) |

## Sequence

```
     Client              API Layer             ServerManager       DatabaseManager      Subprocess
                         api/management.py     services/           repositories/
                         add_server()          server_manager.py   database.py
        │                    │                      │                     │                  │
   1.   │──POST /api/servers─►│                      │                     │                  │
        │  (+ Bearer token)   │                      │                     │                  │
        │                     │                      │                     │                  │
        │                     ┌─────────────────────────────────┐         │                  │
        │                     │ NOTE: Auth check happens here    │         │                  │
        │                     │ HTTPBearer security validates    │         │                  │
        │                     │ FMCP_BEARER_TOKEN                │         │                  │
        │                     └─────────────────────────────────┘         │                  │
        │                     │                      │                     │                  │
   2.   │                     │──validate_server_config()──►               │                  │
        │                     │  (Pydantic + validators)         │         │                  │
        │                     │◄──── valid ─────────────────────│         │                  │
        │                     │                      │                     │                  │
   3.   │                     │──save_server_config()────────────────────►│                  │
        │                     │  (flat → nested transform)       │         ║                  │
        │                     │                      │                     ║──motor           │
        │                     │                      │                     ║  insert_one()    │
        │                     │                      │                     ║  MongoDB         │
        │                     │                      │                     ║                  │
   4.   │                     │◄──── ObjectId ──────────────────────────────║                  │
        │                     │                      │                     │                  │
   5.   │                     │──manager.configs[id] = flat_config────────►│                  │
        │                     │  (register in memory)            ║         │                  │
        │                     │                                  ║         │                  │
   6.   │                     │──start(server_id)────────────────►║         │                  │
        │                     │                                  ║         │                  │
   7.   │                     │                      ║──get_lock()          │                  │
        │                     │                      ║  (prevent concurrent │                  │
        │                     │                      ║   operations)        │                  │
        │                     │                      ║                      │                  │
   8.   │                     │                      ║──subprocess.Popen()──────────────────►│
        │                     │                      ║  cmd: ["npx", "-y", ...]             ║
        │                     │                      ║  stdin=PIPE, stdout=PIPE             ║
        │                     │                      ║                      │               ║
   9.   │                     │                      ║◄──── Process (PID) ──────────────────║
        │                     │                      ║  (process spawned)   │               ║
        │                     │                      ║                      │               ║
  10.   │                     │                      ║──initialize_mcp_server()─────────►( running )
        │                     │                      ║  (JSON-RPC handshake or port poll) │
        │                     │                      ║                      │               ║
        │                     ┌─────────────────────────────────┐          │               ║
        │                     │ NOTE: Transport detection:       │          │               ║
        │                     │ - stdio: JSON-RPC handshake      │          │               ║
        │                     │ - sse/http: TCP port poll        │          │               ║
        │                     └─────────────────────────────────┘          │               ║
        │                     │                      ║                      │               ║
  11.   │                     │                      ║◄──── success ────────────────────────║
        │                     │                      ║  (server initialized)│               ║
        │                     │                      ║                      │               ║
  12.   │                     │                      ║──store PID in processes[id]          ║
        │                     │                      ║  self.processes[id] = process        ║
        │                     │                      ║  self.start_times[id] = time()       ║
        │                     │                      ║                      │               ║
  13.   │                     │◄─── {"status": "running", "pid": 12345} ───║               ║
        │                     │                      │                      │               ║
  14.   │◄── 201 Created ─────│                      │                      │               ║
        │  {                  │                      │                      │               ║
        │    "message": "...", │                      │                      │               ║
        │    "server_id": ..., │                      │                      │               ║
        │    "pid": 12345      │                      │                      │               ║
        │  }                  │                      │                      │               ║
        │                     │                      │                      │               ║
        │                     │                      │         ( running MCP server )      ║
        │                     │                      │                      │               ║
  15.   │──POST /filesystem/mcp──►                   │                      │               │
        │  (JSON-RPC request) │                      │                      │               │
        │                     │──forward_to_mcp()────────────────────────────────────────►║
        │                     │  (via stdin pipe)    │                      │              ║
        │                     │                      │                      │              ║
  16.   │                     │◄──── JSON-RPC response ──────────────────────────────────────║
        │                     │  (via stdout pipe)   │                      │              ║
        │                     │                      │                      │              ║
  17.   │◄── 200 OK ══════════│                      │                      │              ║
        │  (MCP response)     │                      │                      │              ║
        │                     │                      │                      │              ║
```

## Notes

- **Steps 1-5**: Server configuration is added to the system (API → DB → in-memory registry)
- **Steps 6-12**: Server process is started and initialized
- **Steps 15-17**: Normal operation — client sends MCP requests, API forwards to server via stdio

## Error Paths

### Error Path 1: Auth Failure (Step 1)
```
     Client              API Layer
        │                    │
   1.   │──POST /api/servers─►│
        │  (missing/invalid   │
        │   Bearer token)     ║
        │                     ║──verify_bearer_token()
        │                     ║  (check against FMCP_BEARER_TOKEN)
        │                     ║
   2.   │◄── 401 Unauthorized │
        │  {                  │
        │    "detail": "..."  │
        │  }                  │
        │                     │
```

### Error Path 2: Validation Failure (Step 2)
```
     Client              API Layer
        │                    │
   1.   │──POST /api/servers─►│
        │  { invalid config } │
        │                     ║──validate_server_config()
        │                     ║  (missing 'command' field)
        │                     ║
   2.   │◄── 422 Unprocessable Entity ─│
        │  {                  │
        │    "detail": [      │
        │      "command is required" │
        │    ]                │
        │  }                  │
        │                     │
```

### Error Path 3: Process Spawn Failure (Step 8)
```
     Client         API Layer       ServerManager
        │               │                 │
   1.   │──POST ...start─►│               │
        │               │──start()───────►║
        │               │                 ║──subprocess.Popen()
        │               │                 ║  (command not found)
        │               │                 ║
        │               │                 ║  ✗ FileNotFoundError
        │               │                 ║
   2.   │               │◄─── HTTPException(500) ───║
        │               │  "Failed to start server" │
        │               │                 │
   3.   │◄── 500 Error ─│                 │
        │  {            │                 │
        │    "detail": "Failed to start..." │
        │  }            │                 │
        │               │                 │
```

### Error Path 4: Initialization Timeout (Step 10-11)
```
     Client         API Layer       ServerManager        Subprocess
        │               │                 │                    │
   1.   │──POST ...start─►│               │                    │
        │               │──start()───────►║──subprocess.Popen()─────►│
        │               │                 ║                          ║
        │               │                 ║──initialize_mcp_server()  ║
        │               │                 ║  (wait for handshake)    ║
        │               │                 ║                          ║
        │               │                 ║  ... 30s timeout ...     ║
        │               │                 ║                          ║
        │               │                 ║  ✗ TimeoutError           ║
        │               │                 ║──terminate()─────────────►│
        │               │                 ║                          ✗
        │               │                 ║                    (killed)
   2.   │               │◄─── HTTPException(500) ───║
        │               │  "Server failed to initialize" │
        │               │                 │
   3.   │◄── 500 Error ─│                 │
        │  {            │                 │
        │    "detail": "Server failed..." │
        │  }            │                 │
        │               │                 │
```

## Interaction Summary

| Step | From | To | Call | Returns |
|------|------|----|------|---------|
| 1 | Client | api/management.py | POST /api/servers | — |
| 2 | API | validators.py | validate_server_config() | valid/invalid |
| 3 | API | database.py | save_server_config() | ObjectId |
| 4 | database.py | MongoDB | motor insert_one() | ObjectId |
| 5 | API | ServerManager | configs[id] = flat_config | — |
| 6 | API | ServerManager | start(server_id) | — |
| 7 | ServerManager | asyncio.Lock | get_lock() | Lock |
| 8 | ServerManager | subprocess | Popen(cmd, stdin=PIPE, stdout=PIPE) | Process |
| 9 | subprocess | ServerManager | Process object (PID) | — |
| 10 | ServerManager | package_launcher | initialize_mcp_server() | success/timeout |
| 11 | package_launcher | ServerManager | initialization result | bool |
| 12 | ServerManager | self.processes | store PID + timestamp | — |
| 13 | ServerManager | API | {"status": "running", "pid": ...} | — |
| 14 | API | Client | 201 Created | — |
| 15 | Client | API | POST /filesystem/mcp (JSON-RPC) | — |
| 16 | API | Subprocess | forward via stdin | JSON-RPC response via stdout |
| 17 | API | Client | 200 OK (MCP response) | — |

## Critical Synchronization Points

### Operation Lock (Step 7)
```python
# Prevents concurrent start/stop operations on same server
async with self._operation_locks[server_id]:
    # Only one operation at a time per server
    process = subprocess.Popen(...)
```

### Process Registry (Step 12)
```python
# In-memory tracking of running processes
self.processes[server_id] = process  # Popen object
self.configs[server_id] = flat_config  # Config for restarts
self.start_times[server_id] = time.monotonic()  # Uptime tracking
```

### Database Persistence (Step 3-4)
```python
# Async MongoDB insert via motor
await self.db.fluidmcp_servers.insert_one({
    "server_id": server_id,
    "mcp_config": nested_config,
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow()
})
```

## Transport-Specific Flows

### stdio Transport (Default)
```
ServerManager ──subprocess.Popen()──► Process
      │                                   │
      │──write JSON-RPC to stdin──────►  │
      │                                   │
      │◄───read response from stdout─────│
      │                                   │
```

### SSE/HTTP Transport
```
ServerManager ──subprocess.Popen()──► Process (uvicorn)
      │                                   │
      │──poll TCP port (8000)──────────► │ (listening)
      │                                   │
      │◄───connection success───────────  │
      │  (no stdin/stdout handshake)      │
```

For SSE servers, `initialize_mcp_server()` uses `asyncio.open_connection()` to check if the port is accepting connections instead of attempting stdio JSON-RPC handshake.
