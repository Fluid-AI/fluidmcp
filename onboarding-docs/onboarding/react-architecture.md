# FluidMCP Frontend — React Architecture

**Target audience:** New developers joining the FluidMCP project  
**Scope:** All 9 pages at a glance, deep-dive on 4 key pages, hooks overview

---

## Accessing the UI

The frontend is always entered at **`/ui`**:

```
https://<codespace-name>-8099.app.github.dev/ui   # GitHub Codespace
http://localhost:8099/ui                           # local dev
https://<your-app>.railway.app/ui                  # Railway production
```

The Python backend mounts the built frontend at `/ui` using Starlette `StaticFiles(html=True)`. This means `/ui` and any sub-path under it (e.g. `/ui/servers`) all serve `index.html` — React Router then takes over and renders the correct page client-side.

**You cannot deep-link directly to routes like `/servers` or `/llm/models` from outside the app** — they are not served by the backend. Always start from `/ui` and navigate within the SPA.

---

## All Pages at a Glance

Defined in `src/App.tsx`. Every unknown path falls back to `/` via `<Navigate to="/" />`.

| Page | Route | Hook(s) used | What it does |
|---|---|---|---|
| **Dashboard** | `/` or `/servers` | `useServers` | Grid of all MCP server cards with search, filter, sort, pagination, and quick start action |
| **Status** | `/status` | `useServers`, `useActiveServerFiltering` | Lists only running/starting servers; quick stop/restart actions |
| **ServerDetails** | `/servers/:serverId` | `useServerDetails`, `useServerPolling` | Three-tab view: Tools list, live Logs, Environment variables |
| **ToolRunner** | `/servers/:serverId/tools/:toolName` | `useToolRunner` | Auto-generated form from JSON Schema, executes tool, shows result, keeps localStorage history |
| **ManageServers** | `/servers/manage` | `useServerManagement` | Table CRUD: add (manual or GitHub clone), edit, delete/disable servers |
| **LLMModels** | `/llm/models` | `useLLMModels`, `useDebounce` | Grid of LLM model cards (vLLM, Ollama, Replicate) with health status, add/edit modal |
| **LLMModelDetails** | `/llm/models/:modelId` | `useLLMModels` | Single model: health status, uptime, logs, restart/stop actions |
| **LLMPlayground** | `/llm/playground` | — (local state only) | Chat interface: model selector, temperature/max_tokens controls, message history |
| **Documentation** | `/documentation` | — (static content) | Embedded docs with collapsible sidebar navigation and search |

---

## Deep Dive: Key Pages

### 1. Dashboard (`src/pages/Dashboard.tsx`)

**Route:** `/` and `/servers`  
**Hook:** `useServers`

The landing page. Shows all configured MCP servers as cards with status badges.

**What it does:**
- Fetches all servers on mount via `useServers`
- Client-side filtering by status (`running` / `stopped` / `error`), search by name, and sorting (name A-Z, name Z-A, status, recent)
- Pagination at 9 cards per page; scrolls back to top of list on page change
- "Start" button triggers `startServer(id)` from `useServers` with toast feedback
- "View Details" navigates to `/servers/:id`
- Uses `AOS` (Animate On Scroll) for card entrance animations
- Skeleton loading state matches the card grid layout

**Hook wiring:**
```
Dashboard
  └── useServers()
        ├── servers[]          → filtered/sorted/paginated → ServerCard[]
        ├── activeServers[]    → subtitle count "N running"
        ├── loading            → skeleton grid
        ├── error              → ErrorMessage + retry
        ├── startServer(id)    → POST /api/servers/:id/start → refetch
        └── refetch()          → "Refresh" button
```

**Key local state:**
```typescript
const [searchQuery, setSearchQuery] = useState("");
const [sortBy, setSortBy]   = useState<'name-asc'|'name-desc'|'status'|'recent'>('name-asc');
const [filterBy, setFilterBy] = useState<'all'|'running'|'stopped'|'error'>('all');
const [currentPage, setCurrentPage] = useState(1);
const [actionState, setActionState] = useState<{ serverId, type }>({ serverId: null, type: null });
```

`actionState` prevents double-clicking start while a request is in flight.

---

### 2. ManageServers (`src/pages/ManageServers.tsx`)

**Route:** `/servers/manage`  
**Hook:** `useServerManagement`

The CRUD control panel for server configurations. Intentionally separate from Dashboard — Dashboard is for monitoring, ManageServers is for configuration.

**What it does:**
- Fetches all servers including disabled ones (`enabled_only: false`)
- Table layout (not cards): name, command, status, Edit/Delete actions
- "Add Server" opens a modal with two tabs:
  - **Manual Config** → `ServerForm` (name, command, args, env vars)
  - **Clone from GitHub** → `CloneFromGithubForm` (calls `POST /api/servers/from-github`)
- Editing a running server is blocked with an alert — must stop first
- Delete shows `DeleteConfirmationModal` with two options: soft-delete (disable) or hard delete
- "Deleted" toggle shows soft-deleted servers for admin recovery
- Search by name or ID, filter by status, paginated at 10 per page

**Hook wiring:**
```
ManageServers
  └── useServerManagement(showDeleted)
        ├── servers[]        → filtered/paginated table rows
        ├── loading          → spinner
        ├── createServer()   → POST /api/servers → refetch
        ├── updateServer()   → PUT /api/servers/:id → refetch
        ├── deleteServer()   → DELETE /api/servers/:id → refetch
        └── refetch()        → called after showDeleted toggle
```

**Notable pattern — edit guard:**
```typescript
const handleEdit = (server: Server) => {
  if (server.status?.state === 'running') {
    alert('Cannot edit running server. Stop it first.');
    return;
  }
  setEditingServer(server);
  setShowForm(true);
};
```

---

### 3. LLMModels (`src/pages/LLMModels.tsx`)

**Route:** `/llm/models`  
**Hooks:** `useLLMModels`, `useDebounce`

The equivalent of Dashboard but for LLM models. Supports three model types: `process` (vLLM/Ollama local), `replicate` (cloud API).

**What it does:**
- Fetches all models on mount via `useLLMModels`
- Debounced search (300ms) via `useDebounce` to avoid excessive API filtering
- Filtering: all / running / stopped / healthy / unhealthy / process / replicate
- Sorting: name A-Z, name Z-A, health score, uptime
- "Add Model" opens `LLMModelForm` modal (create mode)
- Clicking a card navigates to `/llm/models/:id`
- "Try LLMs" button navigates to `/llm/playground`
- Shows summary stats: `N models, N running, N healthy`

**Hook wiring:**
```
LLMModels
  └── useLLMModels()
        ├── models[]               → filteredModels → sortedModels → paginatedModels → LLMModelCard[]
        ├── runningModels[]        → subtitle count
        ├── healthyModels[]        → subtitle count
        ├── loading                → skeleton grid
        ├── error                  → ErrorMessage + retry
        └── refetch()             → after create/update

  └── useDebounce(searchQuery, 300)
        └── debouncedSearchQuery   → passed to memoized filter
```

**Key difference from Dashboard:** filtering logic is `useMemo`-memoized here (Dashboard does it inline). Also uses `useDebounce` — Dashboard does not.

---

### 4. Documentation (`src/pages/Documentation.tsx`)

**Route:** `/documentation`  
**Hooks:** none (static content, local state only)

A self-contained embedded documentation page. All content is hardcoded in the component — no API calls.

**What it does:**
- Left sidebar with collapsible section groups (Introduction, Setup, Usage, API Reference, etc.)
- Each sidebar item maps to a section `id` — clicking scrolls to the matching `<div id="...">` via `scrollIntoView`
- URL hash navigation: `useLocation()` reads the hash on mount and scrolls to the matching section
- Search filters sidebar items client-side
- Collapse/expand sidebar toggle (mobile-friendly)
- "Back to top" floating button appears on scroll
- Copy buttons on all code blocks

**Why it has no hooks:** the content is static — no server data needed. All state is local (`useState` for active section, sidebar open state, scroll position).

---

## Hooks Overview

All hooks live in `src/hooks/`. They are the only place that calls `apiClient` methods.

| Hook | Used by | What it manages |
|---|---|---|
| `useServers` | Dashboard, Status | Server list; `startServer`, `stopServer`, `restartServer`; AbortController on unmount |
| `useServerManagement` | ManageServers | Server CRUD — `createServer`, `updateServer`, `deleteServer`; includes disabled/deleted servers |
| `useServerDetails` | ServerDetails | Single server data, tools list, logs, env vars |
| `useServerEnv` | ServerDetails (Env tab) | Env var CRUD: add, update, delete key-value pairs |
| `useServerPolling` | ServerDetails | Periodic status refresh for a single server |
| `useActiveServerFiltering` | Status | Client-side filtering of running/starting servers |
| `useServerFiltering` | Dashboard | Client-side search + status filter for server list |
| `useLLMModels` | LLMModels, LLMModelDetails | LLM model list; `restartModel`, `stopModel`, `triggerHealthCheck` |
| `useToolRunner` | ToolRunner | Tool execution via `apiClient.runTool`; localStorage history |
| `usePolling` | (utility) | Generic `setInterval` wrapper with cleanup; used by `useServerPolling` |
| `useDebounce` | LLMModels | Delays state update by N ms; prevents excessive re-filters on keystroke |

### Common patterns across all hooks

**1. AbortController + isMountedRef** — prevents state updates after unmount:
```typescript
const isMountedRef = useRef(true);
const abortControllerRef = useRef<AbortController | null>(null);

useEffect(() => {
  isMountedRef.current = true;
  fetchData();
  return () => {
    isMountedRef.current = false;
    abortControllerRef.current?.abort();
  };
}, [fetchData]);
```

**2. Refetch after mutation** — every write operation (create/update/delete/start/stop) calls `fetchData()` at the end to keep UI in sync with the server:
```typescript
const createServer = async (config) => {
  await apiClient.addServer(config);
  await fetchServers(); // always re-sync
};
```

**3. `useCallback` on fetch functions** — prevents `useEffect` dependency loops:
```typescript
const fetchServers = useCallback(async () => { ... }, []);
useEffect(() => { fetchServers(); }, [fetchServers]);
```

---

## Key Files Reference

| File | Purpose |
|---|---|
| `src/App.tsx` | Route definitions — the single source of truth for all URLs |
| `src/pages/Dashboard.tsx` | Landing page, server grid |
| `src/pages/ManageServers.tsx` | Server CRUD table |
| `src/pages/LLMModels.tsx` | LLM model grid |
| `src/pages/Documentation.tsx` | Embedded static docs |
| `src/hooks/useServers.ts` | Core hook for server list and lifecycle actions |
| `src/hooks/useServerManagement.ts` | Hook for server CRUD operations |
| `src/hooks/useLLMModels.ts` | Hook for LLM model list and actions |
| `src/hooks/useToolRunner.ts` | Hook for tool execution and history |
| `src/services/api.ts` | Singleton `ApiClient` — all `fetch()` calls centralised here |
| `src/types/server.ts` | `Server`, `Tool`, `EnvVar` TypeScript types |
| `src/types/llm.ts` | `LLMModel`, `ReplicateModel`, `ChatMessage` types |
