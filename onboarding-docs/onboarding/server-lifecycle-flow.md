# Server Lifecycle Flow (UI)

**Scope:** How an MCP server is added, edited, deleted, started, stopped, and restarted through the UI — from the ManageServers / Dashboard pages down to the backend subprocess and back.

---

## Entry Paths

```
Add server:
/ui  →  ManageServers (/servers/manage)  →  "Add Server" form  →  Save

Edit server:
/ui  →  ManageServers (/servers/manage)  →  "Edit" on a row  →  Save

Disable / Delete server:
/ui  →  ManageServers (/servers/manage)  →  "Delete" on a row  →  choose Disable or Delete in modal

Start / Stop / Restart:
/ui  →  Dashboard (/)                    →  server card action buttons
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
│        id: "my-server",                                             │
│        name: "My Server",                                           │
│        command: "npx",                                              │
│        args: ["-y", "@package/server"],                             │
│        env: {}                                                      │
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

## Edit Server Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — ManageServers, user clicks "Edit", updates form, saves   │
│                                                                     │
│  useServerManagement().updateServer(serverId, config):              │
│    → setLoading(true)                                               │
│    → apiClient.updateServer(serverId, {                             │
│        command: "npx",                                              │
│        args: ["-y", "@package/server"],                             │
│        env: {}                                                      │
│      })                                                             │
│         PUT /api/servers/:id                                        │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP PUT
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY  (management.py → update_server())                 │
│    → validates bearer token                                         │
│    → validates new config structure                                 │
│    → DatabaseManager.update_server_config()                         │
│        overwrites the stored mcp_config in MongoDB                  │
│    → updates ServerManager.configs (in-memory)                     │
│    → returns { server_id, status: current status }                 │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP 200
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — useServerManagement resumes                              │
│    → refreshes server list                                          │
│    → row shows updated config                                       │
└─────────────────────────────────────────────────────────────────────┘
```

> **Note:** Editing a running server updates the stored config but does not restart the process. The running subprocess continues using the old config until it is restarted.

---

## Delete / Disable Flow

Clicking "Delete" on a server row opens a `DeleteConfirmationModal` with two distinct options:

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — user clicks "Delete" on a row                            │
│    → DeleteConfirmationModal opens with two choices:                │
│                                                                     │
│      🔒 Disable   (yellow)  — hide for now, re-enable later        │
│      🗑️ Delete    (red)     — permanent, admin recovery only        │
└──────────────────┬───────────────────────┬──────────────────────────┘
                   │                       │
         user picks Disable      user picks Delete
                   │                       │ (extra confirm step shown)
                   ▼                       ▼
```

### Option A — Disable (hidden, reversible)

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — user clicks "Disable"                                    │
│                                                                     │
│  handleDisable():                                                   │
│    → apiClient.updateServer(serverId, { enabled: false, ...config })│
│         PUT /api/servers/:id                                        │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP PUT
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY  (management.py → update_server())                 │
│    → sets enabled: false in MongoDB document                        │
│    → no deleted_at set — record stays fully intact                  │
│    → updates ServerManager.configs (in-memory)                     │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP 200
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — modal closes, list refreshes                             │
│    → server disappears from Dashboard (enabled_only=true by default)│
│    → server still visible in ManageServers with "Disabled" badge    │
│    → re-enable anytime by editing and setting enabled: true         │
└─────────────────────────────────────────────────────────────────────┘
```

### Option B — Delete (soft delete, admin-recoverable)

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — user clicks "Delete" → second confirmation screen shown  │
│    "Warning: Irreversible Action / Only admins can recover"         │
│    → user clicks "Confirm Delete"                                   │
│                                                                     │
│  handleDelete():                                                    │
│    → apiClient.deleteServer(serverId)                               │
│         DELETE /api/servers/:id                                     │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP DELETE
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY  (management.py → delete_server())                 │
│    → if server is running: stops process first (SIGTERM → SIGKILL)  │
│    → DatabaseManager.soft_delete_server_config()                    │
│        sets deleted_at: <timestamp> + enabled: false in MongoDB     │
│        (document is NOT removed from DB)                            │
│    → removes config from ServerManager.configs (in-memory)         │
│    → returns { message: "Server deleted", deleted_at: "..." }      │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP 200
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — modal closes, list refreshes                             │
│    → server gone from ManageServers table (default view)            │
│    → admin can reveal it via "Show Deleted" toggle                  │
│        (calls GET /api/servers?include_deleted=true)                │
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

Restart is a sequential Stop → Start. The base config is re-read from the in-memory registry (originally loaded from MongoDB), then merged with any persisted instance-level env vars from the `fluidmcp_server_instances` collection. Instance env vars persist across restarts and take precedence over the config template env vars.

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
| Edit on unknown `server_id` | 404 | Server not found in DB |
| Delete on unknown `server_id` | 404 | Server not found in DB |
| Delete on already-deleted server | 410 | `deleted_at` already set in MongoDB |
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
| `src/hooks/useServerManagement.ts` | `addServer()`, `updateServer()`, `deleteServer()` — CRUD operations |
| `src/components/DeleteConfirmationModal.tsx` | Two-step modal: Disable (PUT enabled:false) vs Delete (DELETE soft) |
| `src/services/api.ts` | `addServer()` — POST; `updateServer()` — PUT; `deleteServer()` — DELETE; `startServer()` / `stopServer()` — POST |

---

## Important Behaviours

**Config is stored once at Add time.**  
Start/Stop/Restart reuse the same base config from MongoDB. The only way to change the persisted base config is to edit it via the ManageServers form (PUT `/api/servers/:id`).

**Instance env vars persist across restarts.**  
Env vars edited through the Environment tab are persisted to the `fluidmcp_server_instances` collection in MongoDB and survive restarts. When a server starts, instance env vars are merged with (and take precedence over) the base config env vars. See [env-variables-flow.md](env-variables-flow.md) for details.

**Status polling.**  
Dashboard cards call `GET /api/servers` on a short polling interval so the status badge stays current without a manual refresh.
