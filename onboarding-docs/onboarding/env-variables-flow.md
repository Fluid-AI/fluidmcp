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
│    → updates env vars on the running server instance in             │
│      ServerManager (in-memory) + persists to MongoDB                │
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

**Env edits apply to the running instance only — the stored config is not changed.**  
`PUT /api/servers/:id/instance/env` patches the in-memory state of the running process. The config saved in MongoDB (added via ManageServers) is left untouched. If the server is stopped and restarted, the original env values from the stored config are used again and any instance edits are lost.

**Updating env vars does not restart the server.**  
The update patches the in-memory config only. For the new values to take effect in the MCP subprocess, the server needs to be restarted separately (via the Stop → Start buttons on ServerDetails or ManageServers).

**Required vs optional.**  
Fields marked `required: true` show a badge in the UI. If a required var is not `present`, the UI surfaces it visually so the user knows the server may not work correctly.
