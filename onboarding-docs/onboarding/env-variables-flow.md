# Environment Variables Flow (UI)

**Scope:** How environment variables for a running MCP server are viewed and edited through the UI — from the ServerDetails "Environment" tab down to the backend and back.

---

## Entry Path

```
/ui  →  Dashboard  →  click "View Details" on a server
     →  ServerDetails (/servers/:serverId)  →  "Environment" tab
```

---

## Data Model

Each env var returned from the backend is not just a plain key-value pair — it carries metadata:

```typescript
// src/types/server.ts
interface EnvMetadata {
  present:     boolean;        // Is a value set on the running instance?
  required:    boolean;        // Is this var required for the server to work?
  masked:      string | null;  // "****" if present, null if not set
  description: string;         // Help text shown in the UI
}

// The full response is a map of key → metadata
interface ServerEnvMetadataResponse {
  [key: string]: EnvMetadata;
}
```

The actual value is never sent to the frontend — only the masked representation. This prevents secrets from appearing in browser DevTools or logs.

---

## Read Flow (page load / tab switch)

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — ServerDetails mounts, "Environment" tab activated        │
│                                                                     │
│  useServerEnv(serverId) initialises:                                │
│    → loadEnv() called immediately via useEffect                     │
│    → setLoading(true)                                               │
│    → apiClient.getServerInstanceEnv(serverId)                       │
│         GET /api/servers/:id/instance/env                           │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP GET
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY                                                    │
│    → validates bearer token (if secure mode)                        │
│    → loads server config from ServerManager / MongoDB               │
│    → builds env metadata response:                                  │
│        for each declared env key in server config:                  │
│          present     = key is set in running instance               │
│          required    = key marked required in metadata              │
│          masked      = "****" if present, else null                 │
│          description = from metadata.json env field description     │
│    → returns { KEY: { present, required, masked, description }, ... }
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP 200
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — useServerEnv resumes                                     │
│    → setEnvMetadata(response)                                       │
│    → setLoading(false)                                              │
│                                                                     │
│  ServerDetails renders <ServerEnvForm envMetadata={envMetadata} />  │
│    → each key shown as a row:                                       │
│        KEY_NAME   [required badge]   ****   [Edit]                  │
│        description text below                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Write Flow (user edits a value)

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — user types new value in ServerEnvForm + clicks Save      │
│                                                                     │
│  ServerEnvForm calls updateEnv(newEnv):                             │
│    newEnv = { API_KEY: "new-value", OTHER_KEY: "..." }              │
│                                                                     │
│  useServerEnv.updateEnv(newEnv):                                    │
│    → setLoading(true)                                               │
│    → apiClient.updateServerInstanceEnv(serverId, newEnv)            │
│         PUT /api/servers/:id/instance/env                           │
│         Body: { "API_KEY": "new-value", "OTHER_KEY": "..." }        │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP PUT
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY                                                    │
│    → validates bearer token                                         │
│    → validates and filters env vars (removes placeholders)          │
│    → persists to MongoDB (fluidmcp_server_instances collection)     │
│    → if server is running: automatically restarts it to apply       │
│      new env vars (with rollback on restart failure)                │
│    → returns { message: "...", env_updated: true }                  │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP 200
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — useServerEnv resumes                                     │
│    → on success: calls loadEnv() to refetch fresh metadata          │
│        (UI shows updated masked values / present flags)             │
│    → on error: setError(message), re-throws so form can handle it   │
│    → setLoading(false)                                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Files

| File | Role in this flow |
|---|---|
| `src/pages/ServerDetails.tsx` | Hosts the three tabs (Tools, Logs, Environment); passes `serverId` to hooks |
| `src/hooks/useServerEnv.ts` | Fetches env metadata on mount; exposes `updateEnv()` |
| `src/components/ServerEnvForm.tsx` | Renders the env var table, edit inputs, save button |
| `src/services/api.ts` | `getServerInstanceEnv()` — GET; `updateServerInstanceEnv()` — PUT |
| `src/types/server.ts` | `EnvMetadata`, `ServerEnvMetadataResponse`, `UpdateEnvResponse` types |

---

## Important Behaviours

**Values are never shown in plain text.**  
The backend only returns masked values (`"****"`). The frontend never has access to the actual secret. When a user edits a field and saves, the new value is sent once over HTTPS and immediately masked again in the response.

**Env edits are persisted to MongoDB and survive restarts.**  
`PUT /api/servers/:id/instance/env` saves the env vars to the `fluidmcp_server_instances` collection in MongoDB. These values persist across server restarts and are merged with the base config env vars (from `fluidmcp_servers` collection) when the server starts. Instance env vars take precedence over config template env vars.

**Updating env vars automatically restarts running servers.**  
When you update env vars via `PUT /api/servers/:id/instance/env`, if the server is currently running, it will be automatically restarted to apply the new environment variables. If the restart fails, the changes are rolled back to prevent the server from being left in a broken state.

**Two-layer env var storage.**  
- **Config template env** (`fluidmcp_servers` collection): Set when adding/editing server via ManageServers form
- **Instance env** (`fluidmcp_server_instances` collection): Set via Environment tab, persists across restarts, takes precedence

**Required vs optional.**  
Fields marked `required: true` show a badge in the UI. If a required var is not `present`, the UI surfaces it visually so the user knows the server may not work correctly.
