# FluidMCP Frontend — Setup & Details

**Target audience:** New developers joining the FluidMCP project  
**Scope:** React frontend — tech stack, directory layout, local setup, backend connection, build & deploy

---

## What Is the Frontend?

The FluidMCP frontend is a **React Single Page Application (SPA)** served by the FastAPI gateway. It is accessible at the `/ui` path (e.g. `https://<your-host>/ui`). Note that `/docs` is the Swagger API docs — a separate route served by FastAPI itself. It provides the web UI for:

- Browsing and managing MCP servers
- Running MCP tools interactively
- Managing and chatting with LLM models
- Viewing logs and server status
- Reading embedded documentation

The frontend lives entirely inside `fluidmcp/frontend/` and is built to a static `dist/` folder that the Python backend serves directly — no separate frontend server in production.

---

## Tech Stack

| Layer | Library | Version | Purpose |
|---|---|---|---|
| Framework | React | 19.2.0 | UI components |
| Language | TypeScript | 5.9.3 | Type safety |
| Build tool | Vite | latest | Dev server + production build |
| Routing | React Router DOM | 7.11.0 | Client-side navigation |
| Styling | Tailwind CSS | 3.4.19 | Utility-first CSS |
| Components | Radix UI + shadcn/ui | — | Accessible primitives |
| Icons | Lucide React | — | Icon library |
| Forms | React Hook Form | 7.71.1 | Form state management |
| Validation | Zod | 3.25.76 | Schema validation |
| State | Custom hooks (no Redux/Zustand) | — | Per-feature state |

---

## Directory Structure

```
fluidmcp/frontend/
├── src/
│   ├── App.tsx                  # Router setup — defines all 9 routes
│   ├── main.tsx                 # React entry point, mounts <App />
│   ├── index.css                # Global CSS imports
│   ├── styles/
│   │   └── globals.css          # CSS variables and base styles
│   │
│   ├── pages/                   # One file per route/page (9 total)
│   │   ├── Dashboard.tsx        # / or /servers — server overview cards
│   │   ├── Status.tsx           # /status — active server monitoring
│   │   ├── ServerDetails.tsx    # /servers/:id — tools, logs, env tabs
│   │   ├── ToolRunner.tsx       # /servers/:id/tools/:tool — execute tools
│   │   ├── ManageServers.tsx    # /servers/manage — add/edit/delete servers
│   │   ├── LLMModels.tsx        # /llm/models — LLM model list
│   │   ├── LLMModelDetails.tsx  # /llm/models/:id — model health & logs
│   │   ├── LLMPlayground.tsx    # /llm/playground — chat interface
│   │   └── Documentation.tsx   # /documentation — embedded docs
│   │
│   ├── components/              # Reusable UI components
│   │   ├── ui/                  # shadcn/ui primitives (Button, Dialog, etc.)
│   │   ├── form/                # Dynamic JSON Schema form components
│   │   │   ├── JsonSchemaForm.tsx   # Auto-generates forms from tool schemas
│   │   │   ├── SchemaFieldRenderer.tsx
│   │   │   ├── StringInput.tsx
│   │   │   ├── NumberInput.tsx
│   │   │   ├── BooleanInput.tsx
│   │   │   ├── ArrayInput.tsx
│   │   │   ├── ObjectInput.tsx
│   │   │   └── SelectInput.tsx
│   │   ├── result/              # Tool result display components
│   │   │   ├── ToolResult.tsx       # Top-level result renderer (auto-detects format)
│   │   │   ├── JsonResultView.tsx
│   │   │   ├── TableResultView.tsx
│   │   │   ├── TextResultView.tsx
│   │   │   └── McpContentView.tsx
│   │   ├── Navbar.tsx           # Top navigation bar
│   │   ├── Footer.tsx           # Footer
│   │   ├── ServerCard.tsx       # Individual server status card
│   │   ├── ServerForm.tsx       # Add/edit server form
│   │   ├── ServerEnvForm.tsx    # Environment variable editor
│   │   ├── LLMModelCard.tsx     # LLM model card
│   │   ├── LLMModelForm.tsx     # Add/edit LLM model form
│   │   ├── CloneFromGithubForm.tsx  # Clone server from GitHub form
│   │   ├── DeleteConfirmationModal.tsx
│   │   ├── ErrorBoundary.tsx
│   │   ├── LoadingSpinner.tsx
│   │   └── Pagination.tsx
│   │
│   ├── hooks/                   # Custom React hooks (all data/logic lives here)
│   │   ├── useServers.ts            # Server list, start/stop actions
│   │   ├── useServerDetails.ts      # Single server data + polling
│   │   ├── useServerManagement.ts   # Server CRUD (add/edit/delete)
│   │   ├── useServerEnv.ts          # Env variable CRUD for a server
│   │   ├── useServerFiltering.ts    # Client-side search + filter for server list
│   │   ├── useActiveServerFiltering.ts  # Filtering for status/active view
│   │   ├── useServerPolling.ts      # Periodic status refresh
│   │   ├── useLLMModels.ts          # LLM model list and management
│   │   ├── useToolRunner.ts         # Tool execution + history
│   │   ├── usePolling.ts            # Generic interval polling utility
│   │   ├── useDebounce.ts           # Debounce input for search
│   │   ├── use-toast.ts             # Toast notification hook
│   │   └── use-mobile.tsx           # Mobile viewport detection
│   │
│   ├── services/                # Non-React utilities
│   │   ├── api.ts               # Singleton ApiClient — all HTTP calls go here
│   │   ├── toolHistory.ts       # localStorage-based tool execution history
│   │   └── toast.ts             # Toast helper functions
│   │
│   ├── types/                   # TypeScript type definitions
│   │   ├── server.ts            # Server, Tool, EnvVar types
│   │   └── llm.ts               # LLMModel, ChatMessage types
│   │
│   ├── lib/
│   │   └── utils.ts             # cn() utility for conditional classNames
│   │
│   └── assets/
│       └── react.svg
│
├── public/                      # Static assets (not processed by Vite)
├── dist/                        # Production build output (gitignored)
├── package.json                 # npm dependencies
├── tsconfig.json                # TypeScript config
├── vite.config.ts               # Vite build config (includes proxy setup)
├── tailwind.config.js           # Tailwind config
└── index.html                   # HTML entry point for Vite
```

---

## Local Development Setup

### Prerequisites

- Node.js 18+ and npm
- Python backend running (`fmcp serve --port 8099`)

### Steps

```bash
# 1. Install dependencies
cd fluidmcp/frontend
npm install

# 2. Build the frontend (outputs to dist/)
npm run build

# 3. Start the backend — it serves the built frontend
cd ../..
fmcp serve --allow-insecure --allow-all-origins --port 8099

# 4. Open in browser
```

Most development happens on **GitHub Codespaces**, not localhost. Use the URL that matches your environment:

| Environment | Frontend UI | API docs |
|---|---|---|
| GitHub Codespace | `https://<codespace-name>-8099.app.github.dev/ui` | `https://<codespace-name>-8099.app.github.dev/docs` |
| Localhost | `http://localhost:8099/ui` | `http://localhost:8099/docs` |
| Railway (production) | `https://<your-app>.railway.app/ui` | `https://<your-app>.railway.app/docs` |

> **Note:** The frontend is served at `/ui`, not at the root. The root `/` is the FastAPI info endpoint, and `/docs` is the Swagger UI for the backend API.

> **Active frontend development:** You can run `npm run dev` (Vite dev server on port 5173) which hot-reloads changes instantly. It proxies API calls to the backend via `vite.config.ts`. Run `npm run build` only when you want to test the production-bundled version.

### Environment Variables

The frontend reads one Vite env variable:

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `window.location.origin` | Backend base URL |

If not set, the frontend uses the same origin it is served from (which is correct for the default setup where frontend + backend are on the same port).

To override during dev:
```bash
# .env.local (inside fluidmcp/frontend/)
VITE_API_BASE_URL=https://<codespace-name>-8099.app.github.dev
```

---

## How the Frontend Talks to the Backend

All API calls go through a **single singleton** — `services/api.ts`.

### ApiClient structure

```typescript
// services/api.ts
class ApiClient {
  private baseUrl: string;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_BASE_URL || window.location.origin;
  }

  // Private: all requests flow through here
  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const controller = new AbortController();
    // Sets a 30s timeout (120s for GitHub operations)
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      signal: options?.signal ?? controller.signal,
      headers: { 'Content-Type': 'application/json', ...options?.headers }
    });
    if (!response.ok) throw new ApiHttpError(await response.text(), response.status);
    return response.json();
  }

  // Public typed methods (30+ total), e.g.:
  listServers()                          // GET  /api/servers
  startServer(id)                        // POST /api/servers/:id/start
  runTool(serverId, toolName, params)    // POST /:serverId/mcp/tools/call
  chatCompletion(payload)                // POST /api/llm/v1/chat/completions
}

export default new ApiClient();  // Singleton — import this everywhere
```

### Usage pattern (hook → api → component)

```
Page/Component
    └── calls custom hook   (e.g. useServers)
            └── calls apiClient method   (e.g. apiClient.listServers())
                    └── fetch() to FastAPI backend
                            └── returns typed response to hook
                                    └── hook updates state → re-render
```

### Error handling

```typescript
// ApiHttpError carries the HTTP status code
export class ApiHttpError extends Error {
  constructor(public message: string, public status: number) {
    super(message);
  }
}

// In hooks — catch and surface to UI
try {
  const data = await apiClient.listServers();
  setServers(data.servers);
} catch (err) {
  if (err instanceof ApiHttpError) {
    setError(`Server error ${err.status}: ${err.message}`);
  }
}
```

---

## Production Build & Serve

### Railway (primary — where FluidMCP is deployed)

FluidMCP is deployed on **Railway**. Railway auto-detects the `Dockerfile` in the repo root and builds + deploys the full app (frontend + backend) as one container. You do not run `npm run build` manually for Railway — the Dockerfile handles it.

Key Railway environment variables to set:

| Variable | Notes |
|---|---|
| `MONGODB_URI` | Auto-provided by the Railway MongoDB service |
| `FMCP_BEARER_TOKEN` | **Must set manually.** Railway containers are ephemeral — if not set, a new token is generated on every restart, breaking auth. Generate with `openssl rand -hex 32`. |
| `PORT` | Auto-assigned by Railway |

> For full Railway setup steps, secrets management, and troubleshooting see **[docs/RAILWAY_DEPLOYMENT.md](../../docs/RAILWAY_DEPLOYMENT.md)**.

### Docker (alternative)

The repo includes a `Dockerfile` that can also be used outside Railway for self-hosted deployments. It runs a two-stage build — Node builds the frontend into `dist/`, then the Python image copies that and starts `fmcp serve`.

```bash
docker build -t fluidmcp:latest .
docker run -d -p 8099:8099 \
  -e MONGODB_URI="mongodb://host.docker.internal:27017" \
  -e FMCP_BEARER_TOKEN="your-token-here" \
  fluidmcp:latest
# UI at http://localhost:8099/ui
```

### How the backend serves the frontend

`fluidmcp/cli/api/frontend.py` mounts the `dist/` folder as a Starlette `StaticFiles` mount under `/ui` and adds a catch-all that returns `index.html` for any path under `/ui/*` — enabling client-side routing to work correctly.

| Request path | Served by |
|---|---|
| `/ui` and `/ui/*` | React SPA (`dist/index.html` + static assets) |
| `/api/*` | FastAPI route handlers |
| `/docs` | Swagger UI (FastAPI built-in) |
| `/health` | FastAPI health endpoint |

---

## Adding a New Page (Quick Reference)

1. **Create the page** in `src/pages/MyPage.tsx`
2. **Add the route** in `src/App.tsx`:
   ```tsx
   <Route path="/my-page" element={<MyPage />} />
   ```
3. **Add nav link** in `src/components/Navbar.tsx`
4. **Create a hook** in `src/hooks/useMyFeature.ts` if the page needs API data
5. **Rebuild**: `npm run build` then restart the backend

---

## Key Files at a Glance

| File | What it does |
|---|---|
| `src/App.tsx` | Route definitions for all 9 pages |
| `src/main.tsx` | React app entry point |
| `src/services/api.ts` | All HTTP calls — the only file that calls `fetch()` |
| `src/types/server.ts` | TypeScript types for servers, tools, env vars |
| `src/types/llm.ts` | TypeScript types for LLM models and chat |
| `vite.config.ts` | Build config + dev proxy to backend |
| `package.json` | npm dependencies |
