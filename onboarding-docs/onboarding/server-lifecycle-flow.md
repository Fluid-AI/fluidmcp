# Server Lifecycle Flow (UI)

**Scope:** How an MCP server is added, started, stopped, and restarted through the UI — from the ManageServers / Dashboard pages down to the backend subprocess and back.

---

## Entry Paths

```
Add server:
/ui  →  ManageServers (/servers/manage)  →  "Add Server" form  →  Save

Start / Stop / Restart:
/ui  →  Dashboard (/)               →  server card action buttons
     →  ManageServers (/servers/manage)  →  row action buttons
```

---

## Add Server Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — ManageServers, user fills "Add Server" form              │
│                                                                     │
│  useServerManagement().addServer(config):                           │
│    → setLoading(true)                                               │
│    → apiClient.addServer({                                          │
│        server_id: "my-server",                                      │
│        config: { command, args, env }                               │
│      })                                                             │
│         POST /api/servers                                           │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP POST
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY  (management.py → add_server())                    │
│    → validates bearer token                                         │
│    → validates config structure (command + args required)           │
│    → checks for duplicate server_id → 409 if exists                │
│    → DatabaseManager.save_server_config()                           │
│        converts flat config → nested mcp_config in MongoDB         │
│    → registers config in ServerManager.configs (in-memory)         │
│    → returns { server_id, status: "stopped" }                      │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP 201
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — useServerManagement resumes                              │
│    → refreshes server list                                          │
│    → new server appears in ManageServers table with status Stopped  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Start Server Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — user clicks "Start" on a server card or row             │
│                                                                     │
│  useServers().startServer(serverId):                                │
│    → setActionLoading(serverId, true)                               │
│    → apiClient.startServer(serverId)                                │
│         POST /api/servers/:id/start                                 │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP POST
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY  (management.py → start_server())                  │
│    → validates bearer token                                         │
│    → calls server_manager.start_server(server_id)                  │
│                                                                     │
│  ServerManager:                                                     │
│    1. loads flat config from in-memory registry (read from DB)     │
│    2. builds command: [command] + args                              │
│    3. subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, env=env)      │
│    4. runs MCP initialization handshake (or TCP poll for SSE):     │
│                                                                     │
│       stdio (default):                                              │
│         → writes JSON-RPC "initialize" to stdin                     │
│         → reads response from stdout (30s timeout)                  │
│         → sends "notifications/initialized"                         │
│                                                                     │
│       sse/http:                                                     │
│         → polls TCP port via asyncio.open_connection()              │
│         → waits until uvicorn accepts connections                   │
│                                                                     │
│    5. fetches tools/list → caches tools in MongoDB                  │
│    6. stores PID in ServerManager.processes dict                    │
│    → updates status to "running"                                    │
│    → returns { status: "running", pid: ... }                       │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP 200
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — useServers resumes                                       │
│    → refreshes server list                                          │
│    → card status badge switches to green "Running"                  │
│    → Start button replaced by Stop + Restart buttons                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Stop Server Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — user clicks "Stop"                                       │
│                                                                     │
│  useServers().stopServer(serverId):                                 │
│    → apiClient.stopServer(serverId)                                 │
│         POST /api/servers/:id/stop                                  │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP POST
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY  (management.py → stop_server())                   │
│    → server_manager.stop_server(server_id)                          │
│                                                                     │
│  ServerManager:                                                     │
│    1. sends SIGTERM to process                                      │
│    2. waits up to 5 seconds for graceful exit                       │
│    3. sends SIGKILL if still running                                │
│    4. removes PID from ServerManager.processes dict                 │
│    → updates status to "stopped"                                    │
│    → returns { status: "stopped" }                                  │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP 200
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — card status badge switches to grey "Stopped"             │
│    Stop + Restart buttons replaced by Start button                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Restart Flow

Restart is a sequential Stop → Start on the same config. The config is re-read from the in-memory registry (originally loaded from MongoDB), so any instance-level env edits made via the Environment tab are discarded on restart.

```
POST /api/servers/:id/restart
  → stop_server()       (SIGTERM → wait → SIGKILL)
  → start_server()      (Spawn → Initialize → Ready)
```

---

## State Transitions

```
[Stopped] ──── Start ────► [Starting] ──── initialized ────► [Running]
                               │                                  │
                               │ spawn / init failure             │
                               ▼                                  │
                           [Error]                                │
                                                                  │
[Stopped] ◄─────────────────── Stop ──────────────────────────────┘

[Running] ──── Restart ───► [Stopping] ──► [Starting] ──► [Running]
```

---

## Error Cases

| Error | HTTP code | Cause |
|---|---|---|
| Duplicate `server_id` on Add | 409 | Server with that ID already in DB |
| Invalid config (missing `command`) | 422 | Validation failure in `validators.py` |
| Command not found at spawn | 500 | `npx`/`python` not on PATH |
| Init timeout (30 s) | 500 | MCP subprocess didn't respond to handshake |
| Stop on non-running server | 400 | Server not in running state |

---

## Key Files

| File | Role in this flow |
|---|---|
| `src/pages/ManageServers.tsx` | Add/Edit/Delete server configs; Start/Stop buttons |
| `src/pages/Dashboard.tsx` | Server cards with Start/Stop/Restart quick actions |
| `src/hooks/useServers.ts` | `startServer()`, `stopServer()` — calls API, refreshes list |
| `src/hooks/useServerManagement.ts` | `addServer()`, `deleteServer()` — CRUD operations |
| `src/services/api.ts` | `addServer()` — POST; `startServer()` / `stopServer()` — POST |

---

## Important Behaviours

**Config is stored once at Add time.**  
Start/Stop/Restart reuse the same config from MongoDB. The only way to change the persisted config is to edit it via the ManageServers form (PUT `/api/servers/:id`).

**Restart resets instance env edits.**  
Env vars edited through the Environment tab are applied to the running instance only and are lost on restart. See [env-variables-flow.md](env-variables-flow.md) for details.

**Status polling.**  
Dashboard cards call `GET /api/servers` on a short polling interval so the status badge stays current without a manual refresh.
