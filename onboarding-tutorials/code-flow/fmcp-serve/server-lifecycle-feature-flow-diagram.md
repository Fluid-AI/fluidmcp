# MCP Server Lifecycle — Feature Flow Diagram

> End-to-end flow for registering an MCP server configuration (POST /api/servers) and then starting it as a live subprocess (POST /api/servers/{id}/start), including auth, persistence, process spawning, and background health monitoring.

## Overview

The lifecycle splits into two sequential API calls. Registration persists a server configuration into MongoDB (flat-to-nested schema conversion included). Start loads that config, acquires a per-server lock, spawns an OS subprocess, performs the MCP stdio/SSE handshake, saves running state, and hands off to the background MCPHealthMonitor which polls every 30 seconds and auto-restarts on failure.

---

## Part 1: Server Registration (POST /api/servers)

```
HTTP Client
    │
    │  POST /api/servers
    │  { id, name, command, args, env, ... }
    ▼
┌─────────────────────────────────────────────┐
│  1. Route handler                            │
│  fluidmcp/cli/api/management.py             │
│  add_server()  @router.post("/servers")     │
└─────────────────────────────────────────────┘
    │
    │  FastAPI Depends(get_token)
    ▼
┌─────────────────────────────────────────────┐
│  2. Auth check                               │
│  fluidmcp/cli/auth.py                       │
│  verify_token() / get_token()               │
└─────────────────────────────────────────────┘
    │
    < FMCP_SECURE_MODE == "true"? >
    │                          │
   [yes]                      [no]
    │                          │
    < token matches            │ (pass-through,
      FMCP_BEARER_TOKEN? >     │  user_id = "anonymous")
    │            │             │
   [yes]        [no] ─────────────────────────► 401 HTTPException
    │                                           {"WWW-Authenticate": "Bearer"}
    │◄─────────── (public mode joins here) ─────┘
    ▼
┌─────────────────────────────────────────────┐
│  3. Input sanitization                       │
│  fluidmcp/cli/api/management.py             │
│  sanitize_input(config)                     │
│  ↳ strips MongoDB $-operators and dots       │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  4. Field validation                         │
│  fluidmcp/cli/api/management.py             │
│  validate_server_config(config)             │
│  ↳ checks "id" and "name" required fields   │
│  ↳ validates command allowlist              │
│  ↳ validates env vars (format, length)      │
└─────────────────────────────────────────────┘
    │
    < "id" and "name" present? >
    │                    │
   [yes]                [no] ────────────────► 400 HTTPException
    ▼                                          "Server id/name is required"
┌─────────────────────────────────────────────┐
│  5. Duplicate check                          │
│  fluidmcp/cli/api/management.py             │
│  manager.configs.get(id)                    │
│  + await manager.db.get_server_config(id)   │
└─────────────────────────────────────────────┘
    │
    < server id already exists? >
    │                    │
   [no]                 [yes] ───────────────► 400/409 HTTPException
    ▼                                          "Server already exists"
┌─────────────────────────────────────────────┐
│  6. Persist to MongoDB                       │
│  fluidmcp/cli/repositories/database.py      │
│  DatabaseManager.save_server_config(config) │
│  ↳ calls _nest_config_for_storage()         │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  7. Schema migration (inside save)           │
│  fluidmcp/cli/repositories/database.py      │
│  DatabaseManager._nest_config_for_storage() │
│  ↳ lifts command/args/env into              │
│    nested mcp_config: { command, args, env }│
│  ↳ sets defaults: description, enabled,     │
│    restart_window_sec, tools, created_by    │
│  ↳ MongoDB upsert with $setOnInsert for     │
│    created_at timestamp                     │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  8. Store in-memory                          │
│  fluidmcp/cli/api/management.py             │
│  manager.configs[id] = config               │
│  ↳ immediate access without DB round-trip   │
└─────────────────────────────────────────────┘
    │
    ▼
  201 { message, id, name }
  ──────────────────────────► HTTP Client
```

---

## Part 2: Server Start (POST /api/servers/{id}/start)

```
HTTP Client
    │
    │  POST /api/servers/{id}/start
    ▼
┌─────────────────────────────────────────────┐
│  1. Route handler                            │
│  fluidmcp/cli/api/management.py             │
│  start_server()                             │
│    @router.post("/servers/{id}/start")      │
└─────────────────────────────────────────────┘
    │
    │  FastAPI Depends(get_token)
    ▼
┌─────────────────────────────────────────────┐
│  2. Auth check                               │
│  fluidmcp/cli/auth.py                       │
│  verify_token() / get_token()               │
│  + get_current_user() → user_id             │
└─────────────────────────────────────────────┘
    │
    < token valid / secure mode? >
    │                   │
   [yes]               [no] ─────────────────► 401 HTTPException
    ▼
┌─────────────────────────────────────────────┐
│  3. Config lookup                            │
│  fluidmcp/cli/api/management.py             │
│  manager.configs.get(id)                    │
│  + await manager.db.get_server_config(id)   │
└─────────────────────────────────────────────┘
    │
    < config found? >
    │           │
   [yes]       [no] ──────────────────────────► 404 HTTPException
    ▼                                           "Server not found"
┌─────────────────────────────────────────────┐
│  4. Enabled check                            │
│  fluidmcp/cli/api/management.py             │
│  config.get("enabled", True)                │
└─────────────────────────────────────────────┘
    │
    < enabled? >
    │          │
   [yes]      [no] ──────────────────────────► 403 HTTPException
    ▼                                          "Server is disabled"
┌─────────────────────────────────────────────┐
│  5. Already-running guard                    │
│  fluidmcp/cli/api/management.py             │
│  manager.processes[id].poll() is None       │
└─────────────────────────────────────────────┘
    │
    < process already running? >
    │                    │
   [no]                 [yes] ───────────────► 400 HTTPException
    ▼                                          "Server already running"
┌─────────────────────────────────────────────┐
│  6. Acquire operation lock                   │
│  fluidmcp/cli/services/server_manager.py    │
│  ServerManager._get_operation_lock(id)      │
│  ↳ per-server asyncio.Lock                  │
│  ↳ fail-fast if lock already held           │
└─────────────────────────────────────────────┘
    │
    < lock already held? >
    │               │
   [no]            [yes] ──────────────────── returns False → 500
    ▼                                          "Failed to start server"
┌─────────────────────────────────────────────┐
│  7. Dispatch to start_server()               │
│  fluidmcp/cli/services/server_manager.py    │
│  ServerManager.start_server(id, config,     │
│                              user_id)        │
│  → delegates to _start_server_unlocked()    │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  8. Spawn MCP process (30 s timeout)         │
│  fluidmcp/cli/services/server_manager.py    │
│  ServerManager._spawn_mcp_process(id,       │
│                                   config)   │
│  ↳ resolves working_dir / install_path      │
│  ↳ auto-reclones GitHub repo if dir missing │
│  ↳ merges instance env vars from DB         │
│  ↳ opens stderr log file (0o600 perms)      │
│  ↳ subprocess.Popen(cmd_list, ...)          │
│  ↳ waits 0.5 s, checks process still alive │
└─────────────────────────────────────────────┘
    │
    < process still alive after 0.5 s? >
    │                           │
   [yes]                       [no] ─────────► returns None → 500
    ▼
┌─────────────────────────────────────────────┐
│  9. Transport-specific handshake             │
│  fluidmcp/cli/services/server_manager.py    │
│  _spawn_mcp_process() (continued)           │
└─────────────────────────────────────────────┘
    │
    < transport == "sse"? >
    │                  │
   [yes]              [no]  (stdio — default)
    │                  │
    ▼                  ▼
┌──────────────┐  ┌────────────────────────────┐
│  SSE branch  │  │  stdio branch               │
│  Poll HTTP   │  │  initialize_mcp_server()    │
│  /sse until  │  │  (MCP initialize handshake) │
│  200 (30 s)  │  │  → tools/list discovery     │
│  → tool disc │  │  → cache in MongoDB         │
│  via HTTP    │  └────────────────────────────┘
│  POST /msg/  │
└──────────────┘
    │                  │
    └──────┬───────────┘
           ▼
┌─────────────────────────────────────────────┐
│  10. Save instance state to MongoDB          │
│  fluidmcp/cli/repositories/database.py      │
│  DatabaseManager.save_instance_state({      │
│    server_id, state:"running", pid,         │
│    start_time, restart_count:0,             │
│    started_by: user_id,                     │
│    last_used_at: now })                     │
│  ↳ optimistic locking via expected_pid      │
│  ↳ upsert into fluidmcp_server_instances    │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  11. Record metrics + uptime                 │
│  fluidmcp/cli/services/metrics.py           │
│  MetricsCollector.set_server_status(2)      │
│  ↳ 2 = running                              │
│  ↳ start_times[id] = time.monotonic()       │
└─────────────────────────────────────────────┘
    │
    ▼
  200 { message: "started", pid: <pid> }
  ──────────────────────────► HTTP Client
    │
    │  (background — already running)
    ▼
┌─────────────────────────────────────────────┐
│  12. MCPHealthMonitor polls every 30 s       │
│  fluidmcp/cli/services/server_manager.py    │
│  MCPHealthMonitor._monitor_loop()           │
│  → _check_server(server_id, process)        │
│  ↳ process.poll() != None → process dead    │
└─────────────────────────────────────────────┘
    │
    < process still alive? >
    │                   │
   [yes]               [no]
    │                   │
    │ (reset restart    ▼
    │  count after    ┌─────────────────────────────────────────┐
    │  5 min uptime)  │  13. Evaluate restart policy             │
    │                 │  fluidmcp/cli/services/server_manager.py │
    │                 │  MCPHealthMonitor._check_server()        │
    │                 │  ↳ load config from DB                   │
    │                 │  ↳ check restart_policy and max_restarts │
    │                 └─────────────────────────────────────────┘
    │                   │
    │         < should_restart? >
    │         │                  │
    │        [yes]              [no]
    │         │                  │
    │         │                  ▼
    │         │       ┌──────────────────────────────┐
    │         │       │  Cleanup DB state only        │
    │         │       │  _cleanup_server(id, rc)      │
    │         │       │  ↳ state: "stopped"/"failed"  │
    │         │       │  ↳ save crash event if failed │
    │         │       └──────────────────────────────┘
    │         │
    │         ▼
    │  ┌─────────────────────────────────────────────┐
    │  │  14. Exponential backoff + restart           │
    │  │  fluidmcp/cli/services/server_manager.py    │
    │  │  MCPHealthMonitor._calculate_restart_delay  │
    │  │  ↳ delay = 5s * 2^min(count, 5)             │
    │  │  ↳ max delay = 5 * 32 = 160 s               │
    │  │  → acquire op lock                           │
    │  │  → _cleanup_server(id, exit_code)            │
    │  │  → _start_server_unlocked(id, config)        │
    │  │    (60 s timeout, same path as step 8-11)    │
    │  └─────────────────────────────────────────────┘
    │         │
    │         ▼
    │  restart_counts[id] += 1
    │  (loop continues every 30 s)
    │
    └──────────────────────────────────────────────── (monitor runs indefinitely)
```

---

## Key Decision Points

| Decision | Location | Yes path | No path |
|---|---|---|---|
| Secure mode enabled? | `auth.py · verify_token()` | Validate bearer token | Pass through (public) |
| Bearer token valid? | `auth.py · _validate_bearer_token()` | Continue | 401 HTTPException |
| `id` and `name` present? | `management.py · add_server()` | Continue | 400 HTTPException |
| Server id already exists? | `management.py · add_server()` | 400/409 HTTPException | Continue |
| Config found in DB/memory? | `management.py · start_server()` | Continue | 404 HTTPException |
| Server enabled? | `management.py · start_server()` | Continue | 403 HTTPException |
| Server already running? | `management.py · start_server()` | 400 HTTPException | Continue |
| Operation lock already held? | `server_manager.py · _get_operation_lock()` | Fail-fast (500) | Acquire lock |
| Process alive after 0.5 s? | `server_manager.py · _spawn_mcp_process()` | Proceed to handshake | Return None → 500 |
| Transport is SSE? | `server_manager.py · _spawn_mcp_process()` | SSE HTTP poll handshake | stdio MCP handshake |
| Process alive (monitor check)? | `server_manager.py · MCPHealthMonitor._check_server()` | No action (healthy) | Evaluate restart policy |
| Restart policy allows restart? | `server_manager.py · MCPHealthMonitor._check_server()` | Backoff + restart | Cleanup DB state only |
| Max restarts reached? | `server_manager.py · MCPHealthMonitor._check_server()` | No restart (log warning) | Proceed with restart |

---

## Side Effects

| Step | Side Effect | Where |
|---|---|---|
| Registration — save config | MongoDB upsert into `fluidmcp_servers` collection; flat `command/args/env` promoted to nested `mcp_config` | `database.py · save_server_config()` |
| Registration — in-memory | `manager.configs[id] = config` for zero-latency access | `management.py · add_server()` |
| Spawn — stderr log | Opens `~/.fluidmcp/logs/mcp_{id}_stderr.log` with `0o600` permissions; rotates at 10 MB | `server_manager.py · _open_stderr_log()` |
| Spawn — auto-reclone | If `source == "github"` and working_dir missing, re-clones repo and re-saves config to DB | `server_manager.py · _spawn_mcp_process()` |
| Spawn — instance env merge | Loads per-instance env overrides from `db.get_instance_env(id)` and merges over config env | `server_manager.py · _spawn_mcp_process()` |
| Start — instance state | MongoDB upsert into `fluidmcp_server_instances` with `state:"running"`, PID, `started_by`, `last_used_at` | `database.py · save_instance_state()` |
| Start — tool discovery | Sends `tools/list` JSON-RPC; caches result back to `fluidmcp_servers.tools[]` | `server_manager.py · _discover_and_cache_tools()` |
| Start — metrics | `MetricsCollector.set_server_status(2)` (running); `start_times[id]` written | `server_manager.py + metrics.py` |
| Health monitor — restart | `restart_counts[id]` incremented; DB state set `"failed"` then `"running"` after restart | `server_manager.py · MCPHealthMonitor` |
| Health monitor — crash event | On non-intentional stop, `db.save_crash_event({exit_code, stderr_tail, uptime_seconds})` | `server_manager.py · _cleanup_server()` |

---

## Error Paths

| Trigger | Response | Code |
|---|---|---|
| Missing or invalid bearer token | `{"detail": "Invalid or missing authorization token"}` + `WWW-Authenticate: Bearer` | 401 |
| `FMCP_BEARER_TOKEN` not set in secure mode | `{"detail": "Server misconfiguration: FMCP_BEARER_TOKEN not set in secure mode"}` | 500 |
| Missing `id` field in registration payload | `{"detail": "Server id is required"}` | 400 |
| Missing `name` field in registration payload | `{"detail": "Server name is required"}` | 400 |
| Server id already exists (in-memory or DB) | `{"detail": "Server with id '...' already exists"}` | 400 |
| MongoDB raises DuplicateKeyError on save | `{"detail": "Server with id '...' already exists"}` | 409 |
| Server id not found at start time | `{"detail": "Server '...' not found"}` | 404 |
| Server is disabled at start time | `{"detail": "Cannot start server '...': Server is disabled"}` | 403 |
| Server process already running | `{"detail": "Server '...' is already running (PID: ...)"}` | 400 |
| Operation lock already held | `start_server()` returns False → `{"detail": "Failed to start server '...'"}` | 500 |
| `_spawn_mcp_process()` returns None | `start_server()` returns False → `{"detail": "Failed to start server '...'"}` | 500 |
| Spawn startup 30 s timeout | `save_instance_state({state:"failed", last_error:"..."})`, returns False → 500 | 500 |
| MCP stdio handshake fails | Process killed, stderr captured, returns None → 500 | 500 |
| SSE server not ready within 30 s | Process killed, returns None → 500 | 500 |
| Max auto-restarts reached (monitor) | Log warning, no restart; DB state remains `"failed"` | — |

---

## Step Reference

| Step | Name | File | Function | Notes |
|---|---|---|---|---|
| P1-1 | Route handler | `fluidmcp/cli/api/management.py` | `add_server()` | Decorated `@router.post("/servers")` |
| P1-2 | Auth check | `fluidmcp/cli/auth.py` | `verify_token()` / `get_token()` | FastAPI `Depends`; constant-time compare via `secrets.compare_digest` |
| P1-3 | Input sanitization | `fluidmcp/cli/api/management.py` | `sanitize_input()` | Strips MongoDB `$`-prefixed keys and dots |
| P1-4 | Config validation | `fluidmcp/cli/api/validators.py` | `validate_server_config()` | Command allowlist + env format checks |
| P1-5 | Duplicate check | `fluidmcp/cli/api/management.py` | `add_server()` | Checks in-memory `manager.configs` then DB |
| P1-6 | Persist config | `fluidmcp/cli/repositories/database.py` | `DatabaseManager.save_server_config()` | MongoDB upsert on `fluidmcp_servers` |
| P1-7 | Schema migration | `fluidmcp/cli/repositories/database.py` | `DatabaseManager._nest_config_for_storage()` | Flat → nested `mcp_config`; PDF spec defaults |
| P1-8 | In-memory store | `fluidmcp/cli/api/management.py` | `add_server()` | `manager.configs[id] = config` |
| P2-1 | Route handler | `fluidmcp/cli/api/management.py` | `start_server()` | Decorated `@router.post("/servers/{id}/start")` |
| P2-2 | Auth + user ID | `fluidmcp/cli/auth.py` | `get_token()` + `get_current_user()` | `user_id` is SHA-256 of token in secure mode |
| P2-3 | Config lookup | `fluidmcp/cli/api/management.py` | `start_server()` | In-memory first, DB fallback |
| P2-4 | Enabled check | `fluidmcp/cli/api/management.py` | `start_server()` | `config.get("enabled", True)` |
| P2-5 | Already-running guard | `fluidmcp/cli/api/management.py` | `start_server()` | `manager.processes[id].poll() is None` |
| P2-6 | Acquire lock | `fluidmcp/cli/services/server_manager.py` | `ServerManager._get_operation_lock()` | Per-server `asyncio.Lock`; fail-fast |
| P2-7 | Delegate start | `fluidmcp/cli/services/server_manager.py` | `ServerManager.start_server()` | Wrapper that holds lock and calls `_start_server_unlocked()` |
| P2-8 | Spawn process | `fluidmcp/cli/services/server_manager.py` | `ServerManager._spawn_mcp_process()` | `subprocess.Popen`; 30 s startup timeout |
| P2-9 | Transport handshake | `fluidmcp/cli/services/server_manager.py` | `_spawn_mcp_process()` / `_handshake_sse_subprocess()` | stdio: MCP init + tools/list; SSE: HTTP poll + POST /messages/ |
| P2-10 | Save instance state | `fluidmcp/cli/repositories/database.py` | `DatabaseManager.save_instance_state()` | Optimistic locking; upsert into `fluidmcp_server_instances` |
| P2-11 | Record metrics | `fluidmcp/cli/services/metrics.py` | `MetricsCollector.set_server_status(2)` | Status 2 = running; `start_times[id]` set |
| P2-12 | Health monitor loop | `fluidmcp/cli/services/server_manager.py` | `MCPHealthMonitor._monitor_loop()` | Runs every 30 s; checks `process.poll()` |
| P2-13 | Restart policy eval | `fluidmcp/cli/services/server_manager.py` | `MCPHealthMonitor._check_server()` | Reads `restart_policy` + `max_restarts` from DB config |
| P2-14 | Backoff restart | `fluidmcp/cli/services/server_manager.py` | `MCPHealthMonitor._check_server()` | `5s * 2^count`; max 160 s; timeout 60 s per restart attempt |
