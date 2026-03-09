# FluidMCP MCP Inspector - Detailed Implementation Plan (Phase 1)

## 📋 Quick Reference for Implementers

**When to Start**: After pending PRs merge
**Estimated Time**: 12-16 hours for Phase 1 MVP
**Backend Work**: ✅ None required (reuse existing endpoints)
**Frontend Work**: 🔨 New page + 4 components

**Phase 1 MVP Deliverables:**
- ✅ View servers with status badges
- ✅ Browse tools from running servers
- ✅ Execute tools with JSON input (Monaco Editor)
- ✅ View JSON output with syntax highlighting
- ✅ Basic error handling and loading states
- ✅ URL persistence (?server=x&tool=y)

**Critical Don'ts:**
- ❌ No new backend endpoints
- ❌ No `react-jsonschema-form`
- ❌ No complex form generation (Phase 1)
- ❌ No `sandbox="allow-same-origin"`
- ❌ No comprehensive tests initially

**Key Files to Create:**
```
pages/mcp/Inspector/
  ├── index.tsx (main orchestration)
  ├── components/
  │   ├── ServerList.tsx
  │   ├── ToolList.tsx
  │   ├── ExecutionPanel.tsx
  │   └── OutputViewer.tsx
  └── types.ts
```

---

## Overview
Build an MCP Inspector similar to mcpjam.com inside FluidMCP to allow users to discover, inspect, and execute tools from configured MCP servers. This is Phase 1 - no agent loop integration, focus on core inspector functionality.

**Status**: Waiting for pending PRs to merge before implementation
**Backend API**: ✅ Already complete (85% done) - reuse existing endpoints
**Frontend**: 🔨 New page + 4 components needed

---

## 🔥 Key Architectural Decisions (Post-Senior Review)

**This plan has been reviewed and refined by senior architecture review. Key decisions:**

1. **✅ Backend Reuse**: No new API router - reuse existing endpoints (EXCELLENT decision)
2. **📁 Directory**: Use `pages/mcp/Inspector/` for better scaling
3. **🚀 Ship Strategy**: Phase 1 MVP (JSON only) → Phase 1.5 (UI rendering) → Phase 1.75 (forms)
4. **⚠️ No Heavy Libs**: Do NOT use `react-jsonschema-form` - too heavy for Phase 1
5. **🔒 Security**: `sandbox="allow-scripts"` ONLY + blob URL (not `allow-same-origin`)
6. **📊 Logs**: "Server Logs" only (not tool execution logs)
7. **🧪 Testing**: Basic tests only - ship first, harden later
8. **🔗 URL State**: Persist selection in URL params for deep linking
9. **⏱️ Timeline**: Phase 1 MVP in 12-16 hours (achievable)

**Philosophy**: Ship basic working inspector quickly, validate with users, then iterate.

---

## Backend Changes (Minimal - Already 85% Done)

### ✅ **No New API Router Required**
The following endpoints already exist in `fluidmcp/cli/api/management.py`:
- `GET /api/servers` (line 777) - List all configured servers
- `GET /api/servers/{id}` (line 798) - Get single server config
- `GET /api/servers/{id}/tools` (line 1451) - Get cached tools from server
- `POST /api/servers/{id}/tools/{tool_name}/run` (line 1481) - Execute tool
- `GET /api/servers/{id}/status` (line 1196) - Get server status
- `GET /api/servers/{id}/logs` (line 1217) - Get server logs

**What these endpoints do:**
- Tools are automatically discovered when servers start
- Tool schemas are cached in MongoDB under `tools` field
- Tool execution sends JSON-RPC `tools/call` request to running process
- 30-second timeout for tool execution
- Full error handling with truncated error messages

### 🔨 **File: `fluidmcp/cli/api/management.py`** (OPTIONAL Enhancement)

**Changes Required:**
- **OPTIONAL**: Add `GET /api/inspector/summary` endpoint to return inspector-specific data:
  - Running server count
  - Available tool count across all servers
  - Recently executed tools (if we add execution history tracking)

**Reasoning**: Current endpoints are sufficient, but a summary endpoint could improve UX by showing stats on the inspector landing page.

### 🔨 **File: `fluidmcp/cli/repositories/base.py`** (OPTIONAL Enhancement)

**Changes Required:**
- **OPTIONAL**: Add `get_servers_with_tools()` method that returns only servers where `tools` array is populated
- **OPTIONAL**: Add `log_tool_execution()` method to track tool execution history

**Reasoning**: These are nice-to-have for better filtering and audit trail, but not required for Phase 1.

---

## Frontend Changes (Main Implementation Work)

### 📁 **New Directory: `fluidmcp/frontend/src/pages/mcp/Inspector/`**

**IMPORTANT**: Use `mcp/Inspector/` structure for better organization (groups all MCP features together)

Create new page directory with following structure:
```
pages/
  mcp/
    Inspector/
      ├── index.tsx                    # Main inspector page layout
      ├── components/
      │   ├── ServerList.tsx          # Left panel: server selection
      │   ├── ToolList.tsx            # Left panel: tool browsing
      │   ├── ExecutionPanel.tsx      # Right panel: JSON input only (Phase 1)
      │   └── OutputViewer.tsx        # Right panel: output display
      └── types.ts                     # TypeScript interfaces
```

**Rationale**: Grouping by domain (mcp/, llm/) scales better as FluidMCP grows into a platform.

---

### 🔨 **File: `fluidmcp/frontend/src/pages/mcp/Inspector/index.tsx`** (NEW)

**Purpose**: Main inspector page with resizable two-panel layout

**Key Features to Implement:**
- Two-column layout using `react-resizable-panels` (recommended over CSS Grid)
- Left panel: Server list + Tool list (scrollable)
- Right panel: Execution panel + Output viewer (stacked)
- **State management (CRITICAL - Centralized Orchestration):**
  - Selected server ID
  - Selected tool object
  - **Tool execution state** (owned by parent, NOT ExecutionPanel):
    ```typescript
    const [execution, setExecution] = useState<ToolExecution | null>(null);
    // ToolExecution includes: serverId, toolName, arguments, status, result, error, timing
    ```
  - Cached tool lists (Map<serverId, Tool[]>)
- Error boundaries for graceful error handling
- Loading states with skeletons
- **URL state persistence with fail-safe**:
  - Store `?server=<id>&tool=<name>` in URL for deep linking
  - **Fail-safe behavior**: If tool no longer exists on server, clear `tool` param from URL
  - Prevents broken deep links

**Dependencies:**
- Import all child components
- Use React hooks: `useState`, `useEffect`, `useCallback`, `useMemo`
- Import `apiClient` from `../../../api/client`
- Use React Query or SWR for data fetching (if already in project)
- Use `useSearchParams` from `react-router-dom` for URL state

**Execution Flow (Parent Orchestration):**
1. ExecutionPanel triggers `onExecute(arguments)` callback
2. Parent (Inspector) handles:
   - API call to `POST /api/servers/{serverId}/tools/{toolName}/run`
   - Execution timing (start/end timestamps)
   - Status updates (idle → loading → success/error)
   - Result/error storage
3. Parent passes execution state to OutputViewer
4. **WHY parent owns execution state:**
   - OutputViewer needs execution metadata (timing, status)
   - Logs tab depends on serverId
   - URL persistence may reload tool
   - Future execution history depends on parent-level control

**URL State Fail-Safe Logic:**
```typescript
// When loading URL params on mount
const serverIdFromUrl = searchParams.get('server');
const toolNameFromUrl = searchParams.get('tool');

// Validate tool exists
if (toolNameFromUrl && selectedServer) {
  const tools = await fetchTools(selectedServer.id);
  const toolExists = tools.find(t => t.name === toolNameFromUrl);

  if (!toolExists) {
    // Clear broken tool param
    searchParams.delete('tool');
    setSearchParams(searchParams);
  }
}
```

**Performance Considerations:**
- Cache tool lists by server ID in component state (avoid refetching on reselect)
- Memoize tool filtering/search with `useMemo`
- Debounce tool search input (300ms)
- **Memoize JSON output to avoid Monaco re-renders:**
  ```typescript
  const jsonOutput = useMemo(() =>
    JSON.stringify(execution?.result, null, 2),
    [execution?.result]
  );
  ```
- If 50+ servers: Consider virtualization with `react-window` (optional)

**Layout Structure:**
```
┌─────────────────────────────────────────┐
│  MCP Inspector                          │
├───────────────┬─────────────────────────┤
│  ServerList   │  ExecutionPanel         │
│               │  ┌───────────────────┐  │
│  ToolList     │  │ Tool Params       │  │
│               │  └───────────────────┘  │
│               │  ┌───────────────────┐  │
│               │  │ OutputViewer      │  │
│               │  │ [JSON|UI|Logs]    │  │
│               │  └───────────────────┘  │
└───────────────┴─────────────────────────┘
```

---

### 🔨 **File: `fluidmcp/frontend/src/pages/mcp/Inspector/components/ServerList.tsx`** (NEW)

**Purpose**: Display all configured MCP servers with status indicators

**Key Features to Implement:**
- Fetch servers from `GET /api/servers` on component mount
- Display server list in scrollable container
- Show server metadata:
  - Server ID (name)
  - Status badge: 🟢 Running / 🔴 Stopped / 🟡 Starting
  - Tool count (from cached tools array)
  - Server type icon (filesystem, database, etc.)
- Click handler to select server and load its tools
- Active state styling for selected server
- Empty state: "No servers configured. Go to Servers page to add."
- Error state: Display fetch errors with retry button
- Refresh button to reload server list

**Data Fetching:**
- Call `apiClient.get('/servers')` on mount
- **NO auto-refresh in Phase 1** - manual refresh button only
- **Rationale**: Inspector is dev tool, avoid silent re-renders during tool editing
- Handle loading/error states

**UI Components:**
- List container with virtualization if 50+ servers (use `react-window`)
- Server card/row with:
  - Icon (based on server type)
  - Name (bold)
  - Status badge
  - Tool count badge
  - "Start" button for stopped servers (calls `POST /api/servers/{id}/start`)

**Interaction Flow:**
1. User clicks server → Trigger `onServerSelect(server)` callback
2. Parent component fetches tools for selected server
3. Selected server gets highlighted styling

---

### 🔨 **File: `fluidmcp/frontend/src/pages/mcp/Inspector/components/ToolList.tsx`** (NEW)

**Purpose**: Display available tools from selected server

**Key Features to Implement:**
- Receives `serverId` prop from parent
- Fetch tools from `GET /api/servers/{serverId}/tools`
- Display tools in categorized/grouped list (if tools have categories)
- Show tool metadata:
  - Tool name
  - Description (truncated to 2 lines)
  - Parameter count indicator
  - Required parameters badge (red dot if any required params)
- Search/filter bar to find tools by name or description
- Click handler to select tool and load execution panel
- Empty state: "No tools available. Server may need to be restarted."
- Collapsible tool details:
  - Full description
  - Input schema preview
  - Output schema preview (if available)

**Data Fetching:**
- Call `apiClient.get(\`/servers/\${serverId}/tools\`)` when serverId changes
- Cache tool schemas in component state
- Parse JSON Schema to extract parameter info

**UI Components:**
- Search input with debounced filtering
- Tool card/row with:
  - Tool icon (generic gear icon)
  - Name (bold)
  - Description (truncated)
  - Parameter count badge ("3 params")
  - Expand/collapse icon for details
- Expandable section showing:
  - Full description
  - Input schema table (param name, type, required, description)
  - Example usage (if available in schema)

**Interaction Flow:**
1. User clicks tool → Trigger `onToolSelect(tool)` callback
2. Parent component loads ExecutionPanel with tool schema
3. Selected tool gets highlighted styling

---

### 🔨 **File: `fluidmcp/frontend/src/pages/mcp/Inspector/components/ExecutionPanel.tsx`** (NEW)

**Purpose**: JSON-based tool parameter input (Phase 1: SIMPLIFIED)

**⚠️ PHASE 1 SCOPE: JSON MODE ONLY**
- Do NOT build form generation in Phase 1
- Do NOT use `react-jsonschema-form` (heavy dependency, overkill)
- JSON mode with Monaco Editor is sufficient and provides escape hatch for all schemas

**Key Features to Implement:**
- Receives `tool` object with JSON Schema
- Display tool metadata:
  - Tool name (header)
  - Description
  - Input schema reference (expandable, shows raw schema)
- **Tool Schema Parsing (Phase 1 - Minimal)**:
  - **Supported**: `type: object`, `properties`, `required` array
  - **Ignored**: `oneOf`, `anyOf`, nested object recursion, array of objects
  - **Rationale**: JSON mode handles all complexity, schema display is informational only
- **JSON Editor** (Monaco Editor):
  - JSON syntax highlighting
  - Line numbers
  - Real-time syntax validation
  - Error squiggles for invalid JSON
  - Pre-populate with empty object `{}` or schema defaults (if simple)
- Button group:
  - "Execute" button (primary, disabled during execution)
  - "Clear" button (secondary, resets to `{}`)
  - "Load Example" button (if schema has examples)
- Loading spinner during execution
- Error display below editor

**UI Components:**
- Tool info header (collapsible)
- Monaco Editor (reuse from ChatPlayground)
- Button toolbar
- Error banner (red, appears on execution failure)

**Execution Flow:**
1. User enters JSON in Monaco Editor
2. Click "Execute" → Validate JSON syntax
3. Call `apiClient.post(\`/servers/\${serverId}/tools/\${toolName}/run\`, JSON.parse(input))`
4. Show loading spinner (disable execute button)
5. On success → Pass result to OutputViewer
6. On error → Show error message below editor

**State Management:**
- JSON input string
- Execution status (idle/loading/success/error)
- Error message

**Phase 1.5 (Future):**
- Add simple form generation for primitives only (string, number, boolean, enum)
- Keep JSON mode as fallback for complex schemas

---

### 🔨 **File: `fluidmcp/frontend/src/pages/mcp/Inspector/components/OutputViewer.tsx`** (NEW)

**Purpose**: Display tool execution results in multiple formats

**Key Features to Implement:**
- Tabbed interface with 3 tabs:
  - **JSON Tab** (default): Formatted JSON output
  - **Rendered UI Tab**: If output contains HTML/UI elements (Phase 1.5)
  - **Server Logs Tab**: Server process logs (not tool-specific execution logs)
- JSON Tab features:
  - Monaco Editor in read-only mode
  - Syntax highlighting
  - Copy to clipboard button
  - Download as JSON file button
  - Simple view (no need for tree view in Phase 1)
- Rendered UI Tab features (Phase 1.5):
  - Sandboxed iframe for HTML rendering
  - **SECURITY**: `sandbox="allow-scripts"` ONLY (do NOT add `allow-same-origin`)
  - Use blob URL instead of inline HTML (safer)
  - Empty state if no UI content
- **Server Logs Tab** features:
  - **IMPORTANT**: These are server process logs, NOT tool execution logs
  - Label clearly: "Server Logs (Process Output)"
  - **Add info tooltip**: "These logs are from the MCP server process, not specific tool executions"
  - Fetch logs from `GET /api/servers/{serverId}/logs`
  - Manual refresh button (no auto-refresh in Phase 1)
  - Monospace font display
  - Auto-scroll to bottom
  - Header format: "Server Logs - {serverName}" (shows which server's logs)
- Execution metadata bar:
  - Execution time (duration in ms)
  - Timestamp
  - Success/failure status icon
  - Error message (if failed)

**UI Components (Phase 1 - Simplified):**
- Tab navigation bar
- **JSON Tab**:
  - Monaco Editor component (reuse from ChatPlayground)
  - Toolbar: Copy | Download
  - No tree view needed (Phase 1)
- **Rendered UI Tab** (Phase 1.5 - defer for now):
  - Iframe container with blob URL rendering
  - Empty state: "This tool did not return UI content"
- **Server Logs Tab**:
  - Header: "Server Logs - {serverName}"
  - Log viewer with monospace font (simple `<pre>` tag)
  - Refresh button
  - Auto-scroll to bottom (always on)

**Data Handling:**
- Receives `output` prop from parent
- Format JSON with proper indentation
- For Phase 1: Focus on JSON output only
- Phase 1.5: Add HTML detection and rendering

**Security Considerations (Phase 1.5):**
- Iframe must use `sandbox="allow-scripts"` ONLY (no `allow-same-origin`)
- Render HTML via blob URL instead of inline srcDoc
- HTML content must be sanitized with DOMPurify before blob creation
- Never allow `allow-same-origin` with `allow-scripts` together (XSS risk)

---

### 🔨 **File: `fluidmcp/frontend/src/pages/mcp/Inspector/types.ts`** (NEW)

**Purpose**: TypeScript interfaces for Inspector components

**Interfaces to Define:**
```typescript
// Server types
interface Server {
  id: string;
  server_id: string;
  config: ServerConfig;
  status: 'running' | 'stopped' | 'starting' | 'error';
  tools?: Tool[];
  created_at?: string;
  updated_at?: string;
}

interface ServerConfig {
  command: string;
  args: string[];
  env?: Record<string, string>;
}

// Tool types
interface Tool {
  name: string;
  description?: string;
  inputSchema: JSONSchema;
  outputSchema?: JSONSchema;
}

interface JSONSchema {
  type: string;
  properties?: Record<string, JSONSchemaProperty>;
  required?: string[];
  description?: string;
}

interface JSONSchemaProperty {
  type: string;
  description?: string;
  enum?: string[];
  default?: any;
  minimum?: number;
  maximum?: number;
  pattern?: string;
}

// Execution types
interface ToolExecution {
  server_id: string;
  tool_name: string;
  arguments: Record<string, any>;
  status: 'idle' | 'loading' | 'success' | 'error';
  result?: ToolExecutionResult;
  error?: string;
  started_at?: Date;
  completed_at?: Date;
  duration_ms?: number;
}

interface ToolExecutionResult {
  content?: any[];
  isError?: boolean;
  _meta?: {
    progressToken?: string;
  };
}

// UI types
interface ViewportSize {
  width: number;
  height: number;
  label: string;
}

interface LogEntry {
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  message: string;
}
```

**Export all interfaces for use across components**

---

### 🔨 **File: `fluidmcp/frontend/src/api/client.ts`** (MODIFY)

**Purpose**: Add API methods for inspector endpoints

**Changes Required:**
Add the following methods to the existing `ApiClient` class:

```typescript
// Inspector-specific methods
async getInspectorServers(): Promise<{servers: Server[]}>
  - Calls GET /api/servers
  - Returns list of all configured servers

async getInspectorServerStatus(serverId: string): Promise<{status: string}>
  - Calls GET /api/servers/{serverId}/status
  - Returns current server status

async getInspectorTools(serverId: string): Promise<{server_id: string, tools: Tool[], count: number}>
  - Calls GET /api/servers/{serverId}/tools
  - Returns cached tools from MongoDB

async runInspectorTool(serverId: string, toolName: string, arguments: Record<string, any>): Promise<any>
  - Calls POST /api/servers/{serverId}/tools/{toolName}/run
  - Sends tool arguments as request body
  - Returns tool execution result

async getInspectorLogs(serverId: string, limit?: number): Promise<{logs: string[]}>
  - Calls GET /api/servers/{serverId}/logs?limit={limit}
  - Returns recent server logs

async startServer(serverId: string): Promise<void>
  - Calls POST /api/servers/{serverId}/start
  - Used by ServerList to start stopped servers
```

**No changes to authentication** - existing bearer token handling works for all endpoints.

---

### 🔨 **File: `fluidmcp/frontend/src/App.tsx`** (MODIFY)

**Purpose**: Add inspector route to application

**Changes Required:**
1. Import new Inspector page:
   ```typescript
   import Inspector from './pages/mcp/Inspector';
   ```

2. Add route in router configuration:
   ```typescript
   <Route path="/mcp/inspector" element={<Inspector />} />
   ```

**Location**: Add after existing routes (around line 50-100 depending on current structure)

---

### 🔨 **File: `fluidmcp/frontend/src/components/Layout/Sidebar.tsx`** (MODIFY)
**OR**
### 🔨 **File: `fluidmcp/frontend/src/components/Navbar.tsx`** (MODIFY)

**Purpose**: Add navigation link to MCP Inspector

**Changes Required:**
Add navigation item to sidebar/navbar:
- Label: "MCP Inspector" or "Inspector"
- Icon: 🔍 or use appropriate icon from your icon library
- Link: `/mcp/inspector`
- Position: After "MCP Servers" menu item

**Example structure:**
```
- Dashboard
- MCP Servers
- MCP Inspector  ← NEW
- LLM Models
- Chat Playground
```

---

## Dependencies to Install

### 🔨 **File: `fluidmcp/frontend/package.json`** (MODIFY)

**New Dependencies to Add:**

**Required (Phase 1):**
- `react-resizable-panels` - Resizable panel layout (if not already installed)

**Required (Phase 1.5 - UI Rendering):**
- `dompurify` - HTML sanitization for iframe rendering
- `@types/dompurify` - TypeScript types

**Optional (Only if needed):**
- `react-window` - Virtualized list (only if 50+ servers cause performance issues)

**Already Available (Verify):**
- `@monaco-editor/react` - Already used in ChatPlayground
- `react-router-dom` - Already in project
- Icon library (e.g., `lucide-react`, `react-icons`)

**⚠️ DO NOT INSTALL:**
- ❌ `react-jsonschema-form` - Too heavy, large bundle size, not needed for Phase 1
- ❌ `react-json-view` - Not needed, Monaco Editor is sufficient

**Installation Command (Phase 1):**
```bash
cd fluidmcp/frontend
npm install react-resizable-panels
```

**Installation Command (Phase 1.5 - when adding UI rendering):**
```bash
npm install dompurify @types/dompurify
```

---

## Testing Strategy (Simplified)

### 🔨 **New Test Files to Create (Phase 1 - Keep It Simple):**

**⚠️ IMPORTANT**: Do NOT overinvest in tests initially. Ship first, harden later.

1. **`fluidmcp/frontend/src/pages/mcp/Inspector/__tests__/Inspector.test.tsx`**
   - Test page renders without crashing
   - Test basic server selection flow
   - Test basic tool execution flow

2. **`fluidmcp/frontend/src/pages/mcp/Inspector/components/__tests__/ServerList.test.tsx`**
   - Test server list renders
   - Test empty state

3. **`fluidmcp/frontend/src/pages/mcp/Inspector/components/__tests__/ToolList.test.tsx`**
   - Test tool list renders
   - Test empty state

4. **`fluidmcp/frontend/src/pages/mcp/Inspector/components/__tests__/ExecutionPanel.test.tsx`**
   - Test JSON input renders
   - Test execute button triggers API call

5. **`fluidmcp/frontend/src/pages/mcp/Inspector/components/__tests__/OutputViewer.test.tsx`**
   - Test JSON tab renders output
   - Test tab switching works

**Testing Framework:**
- Use existing Jest + React Testing Library setup
- Mock API calls with MSW (Mock Service Worker) if available, otherwise simple mocks
- Focus on rendering tests, not deep interaction tests

**Note**: Do NOT write comprehensive schema validation tests or deep nested interaction tests in Phase 1.

---

## Documentation Updates

### 🔨 **File: `README.md`** (MODIFY)

**Changes Required:**
Add section about MCP Inspector:
```markdown
## MCP Inspector

FluidMCP includes a built-in MCP Inspector for testing and debugging MCP servers.

Features:
- Browse all configured MCP servers
- Discover available tools from each server
- Execute tools with dynamic form generation
- View results in JSON or rendered UI format
- Monitor server logs in real-time

Access at: http://localhost:3000/mcp/inspector
```

### 🔨 **File: `CLAUDE.md`** (MODIFY)

**Changes Required:**
Add MCP Inspector section under "## Architecture":
```markdown
### MCP Inspector (`fluidmcp/frontend/src/pages/mcp/Inspector/`)
- Web-based tool inspector for testing MCP servers
- Reuses existing API endpoints from management.py
- JSON-based tool execution (Phase 1: Monaco Editor input)
- Supports JSON output viewing and server log monitoring
- Phase 1.5: Add UI rendering for HTML responses
```

### 🔨 **New File: `docs/MCP_INSPECTOR.md`** (NEW)

**Purpose**: User guide for MCP Inspector

**Content to Include:**
- Overview and purpose
- How to access the inspector
- How to select and inspect servers
- How to execute tools
- How to interpret results
- Troubleshooting common issues
- Security considerations for UI rendering
- Examples with screenshots (add later)

---

## Security Considerations (CRITICAL)

### **Platform Security Boundary (Phase 1)**

**IMPORTANT**: Inspector only works with servers already configured in MongoDB.
- **No arbitrary command execution from UI**
- **No direct user input to server process spawning**
- **Users can only execute tools on pre-configured, approved servers**
- **Rationale**: Protects platform from command injection and unauthorized access

**Phase 2 Note**: When adding "temporary server connections", security model changes:
- Temporary servers must be sandboxed
- Consider authentication/authorization for temporary servers
- Add clear warnings in UI: "Temporary server - not persisted"

### 🔨 **File: `fluidmcp/frontend/src/pages/mcp/Inspector/components/OutputViewer.tsx`**

**⚠️ IMPORTANT SECURITY MEASURES (Phase 1.5 - UI Rendering):**

1. **Iframe Sandboxing:**
   - **CORRECT**: Use `sandbox="allow-scripts"` ONLY
   - **WRONG**: Do NOT use `sandbox="allow-scripts allow-same-origin"`
   - **WHY**: If you allow both `allow-scripts` AND `allow-same-origin`, the iframe content can access cookies/localStorage (XSS attack vector)
   - Use blob URL for rendering instead of inline srcDoc

2. **HTML Sanitization:**
   - Use DOMPurify to sanitize all HTML before creating blob URL
   - Strip dangerous tags: `<script>`, `<iframe>`, `<object>`, `<embed>`
   - Remove inline event handlers: `onclick`, `onerror`, etc.
   - Sanitize BEFORE creating blob URL

3. **Blob URL Pattern (Safer than srcDoc):**
   ```typescript
   // Sanitize HTML first
   const clean = DOMPurify.sanitize(htmlContent);
   // Create blob URL
   const blob = new Blob([clean], { type: 'text/html' });
   const blobUrl = URL.createObjectURL(blob);
   // Use in iframe
   <iframe src={blobUrl} sandbox="allow-scripts" />
   // Clean up on unmount
   useEffect(() => () => URL.revokeObjectURL(blobUrl), [blobUrl]);
   ```

4. **Input Validation:**
   - Validate all tool arguments before execution
   - Prevent command injection in string parameters
   - Sanitize file paths in filesystem tools

**Threat Model**: Treat all MCP server tool outputs as untrusted/hostile.

---

## Strategic Value of MCP Inspector

**Why This Feature Matters:**

Once Inspector is complete, FluidMCP becomes a **complete AI infrastructure platform**:

| Feature | Status | Description |
|---------|--------|-------------|
| ✅ **MCP Server Management** | Live | Add, configure, start/stop servers |
| ✅ **LLM Management** | Live | Run vLLM, Ollama, Replicate models |
| ✅ **Chat Playground** | Live | Test LLM models with chat interface |
| ✅ **MCP Inspector** | **← YOU ARE HERE** | Discover and execute MCP tools |

**This positions FluidMCP as:**
- 🛠️ **Developer debugging tool** - Inspect and test MCP servers locally
- 🔍 **Tool explorer** - Discover what tools are available across servers
- 🎨 **UI renderer** - Render HTML/widget responses from MCP tools
- 📚 **MCP teaching interface** - Demo MCP capabilities to teams
- 🧪 **Internal QA environment** - Test tool integrations before production
- 🚀 **Production AI orchestration** - Unified MCP + LLM management

**Competitive Advantage:**
- Few tools combine **MCP + LLM + UI rendering** in one platform
- No CLI context switching - everything in web UI
- Single source of truth for all AI infrastructure
- Built-in observability (logs, metrics, execution traces)

**You're not building a feature - you're completing a platform.**

---

## Risk Assessment (Post-Review)

| Risk Category | Level | Mitigation Strategy |
|---------------|-------|---------------------|
| **Backend Complexity** | 🟢 Low | Reuse existing endpoints - no new API routes |
| **Security Risk** | 🟡 Medium | Iframe sandboxing + DOMPurify + blob URL (Phase 1.5) |
| **Scope Creep** | 🟢 Low | Clear phase boundaries, ship MVP first |
| **Performance Risk** | 🟢 Low | Monaco memoization, tool list caching |
| **Overengineering** | 🟢 Low | JSON-only in Phase 1, no heavy libraries |
| **URL Fail-Safe** | 🟢 Low | Validation logic prevents broken deep links |
| **State Management** | 🟢 Low | Centralized execution state in parent |

**Overall Risk Level**: 🟢 **LOW** (post-refinement)

All major architectural risks have been mitigated through design decisions.

---

## Phase 2 Future Enhancements (Out of Scope)

These features are planned for Phase 2 but NOT included in this implementation:

1. **Agent Loop Integration:**
   - LLM can autonomously decide which tools to call
   - Natural language to tool invocation
   - Multi-step reasoning with tool chaining

2. **Temporary Server Connections:**
   - Connect to external MCP servers without MongoDB persistence
   - Quick test mode for development

3. **Streaming Support:**
   - Real-time updates during long-running tool executions
   - WebSocket or SSE integration

4. **Advanced UI Features:**
   - Viewport testing (mobile/tablet/desktop)
   - Theme switching for rendered UIs
   - Screenshot capture of rendered UIs

5. **Execution History:**
   - Database table for tool execution logs
   - Replay previous executions
   - Export execution history

6. **Collaboration Features:**
   - Share tool executions with team
   - Collaborative debugging sessions

---

## Implementation Timeline (Phased Approach)

**Prerequisite:** Wait for pending PRs to merge

### **Phase 1 - MVP (Ship Basic Working Inspector)**
**Goal**: Get a functional inspector working quickly
**Estimated Time: 12-16 hours**

**Phase 1A - Foundation (4-5 hours):**
- Create `pages/mcp/Inspector/` directory structure
- Add types.ts with basic interfaces
- Update API client with inspector methods
- Add routing in App.tsx
- Add navigation link to sidebar

**Phase 1B - Core Components (6-8 hours):**
- Implement ServerList.tsx (basic list, status badges)
- Implement ToolList.tsx (basic list, tool selection)
- Implement ExecutionPanel.tsx (JSON mode ONLY - Monaco Editor)
- Implement OutputViewer.tsx (JSON tab ONLY - Monaco Editor)

**Phase 1C - Integration & Polish (2-3 hours):**
- Wire up state management in main Inspector page
- Add URL persistence (?server=x&tool=y)
- Error handling and loading states
- Basic styling to match existing design system

**✅ Ship Phase 1** - Basic JSON-based tool inspector is now usable

---

### **Phase 1.5 - Enhanced Features**
**Goal**: Add UI rendering and server logs
**Estimated Time: 8-10 hours**

**Phase 1.5A - UI Rendering (4-5 hours):**
- Install DOMPurify
- Add Rendered UI tab to OutputViewer
- Implement blob URL + sandboxed iframe rendering
- HTML detection logic

**Phase 1.5B - Logs & Refinements (4-5 hours):**
- Add Server Logs tab to OutputViewer
- Implement log fetching and display
- Add refresh button for logs
- Performance optimization (caching, memoization)

**✅ Ship Phase 1.5** - Inspector now supports UI rendering and log viewing

---

### **Phase 1.75 (Optional) - Form Generation**
**Goal**: Add simple form generation for common types
**Estimated Time: 6-8 hours**

- Add form mode to ExecutionPanel (primitives only: string, number, boolean, enum)
- Keep JSON mode as fallback
- Toggle between form/JSON modes

**✅ Ship Phase 1.75** - Inspector now has basic form generation

---

### **Phase 2 - Agent Integration (Future)**
**Goal**: LLM agent can autonomously call tools
**Estimated Time: TBD (see Phase 2 section)**

---

**Total Phase 1 Time: 12-16 hours**
**Total Phase 1 + 1.5 Time: 20-26 hours**
**Total Phase 1 + 1.5 + 1.75 Time: 26-34 hours**

**Recommendation**: Ship Phase 1 quickly, validate with users, then decide on Phase 1.5 vs Phase 2.

---

## Success Criteria

### **Phase 1 MVP Complete When:**

✅ User can view all configured MCP servers with status indicators
✅ User can see tools available on each running server
✅ User can execute tools with JSON input (Monaco Editor)
✅ User can view JSON results with syntax highlighting
✅ All components have basic error handling and loading states
✅ URL state persistence works (?server=x&tool=y)
✅ Basic tests pass (rendering tests)
✅ README and CLAUDE.md updated

### **Phase 1.5 Complete When:**

✅ User can view rendered UI results in sandboxed iframe (secure)
✅ User can view server logs
✅ No security vulnerabilities in UI rendering (DOMPurify + blob URL)
✅ Performance optimizations added (caching, memoization)

### **Phase 1.75 Complete When (Optional):**

✅ User can use simple form inputs for primitive types
✅ JSON mode still works as fallback

---

## Architectural Clarifications (Final Review)

### **1. Execution State Ownership (CRITICAL)**
- ✅ **Execution state lives in parent** (Inspector page), NOT ExecutionPanel
- ✅ ExecutionPanel only triggers `onExecute(arguments)` callback
- ✅ Parent handles: API call, timing, status updates, result storage
- ✅ **WHY**: OutputViewer needs metadata, logs depend on serverId, URL persistence needs parent control

### **2. URL State Fail-Safe**
- ✅ Validate tool exists when loading from URL params
- ✅ If tool doesn't exist, clear `tool` param from URL
- ✅ Prevents broken inspector deep links

### **3. Server Status Refresh**
- ✅ **NO auto-refresh in Phase 1** - manual refresh button only
- ✅ **Rationale**: Dev tool, avoid silent re-renders during editing

### **4. Tool Schema Parsing Rules**
- ✅ **Supported**: `type: object`, `properties`, `required`
- ✅ **Ignored**: `oneOf`, `anyOf`, nested recursion, array of objects
- ✅ **Rationale**: JSON mode handles complexity, prevents scope creep

### **5. Server Logs UX**
- ✅ Label: "Server Logs (Process Output)"
- ✅ Add tooltip: "These logs are from the MCP server process, not specific tool executions"
- ✅ Prevents user confusion

### **6. Security Boundary**
- ✅ **Inspector only works with MongoDB configured servers**
- ✅ **No arbitrary command execution from UI**
- ✅ Protects platform from unauthorized access

### **7. Performance Optimization**
- ✅ Memoize JSON output: `useMemo(() => JSON.stringify(result, null, 2), [result])`
- ✅ Avoid Monaco Editor re-renders (expensive)
- ✅ Cache tool lists by server ID

---

## Decisions Made (Based on Senior Review)

✅ **Directory Structure:**
   - **DECISION**: Use `pages/mcp/Inspector/` (not `pages/MCPInspector/`)
   - **RATIONALE**: Groups MCP features together, scales better long-term

✅ **Form Generation:**
   - **DECISION**: Phase 1 is JSON mode ONLY (no `react-jsonschema-form`)
   - **RATIONALE**: Heavy dependency, large bundle size, overkill for MVP
   - **FUTURE**: Phase 1.75 can add simple form for primitives only

✅ **Panel Layout:**
   - **DECISION**: Use `react-resizable-panels` for resizable two-panel layout
   - **RATIONALE**: Better UX than fixed 50/50 split

✅ **Iframe Security:**
   - **DECISION**: Use `sandbox="allow-scripts"` ONLY (remove `allow-same-origin`)
   - **RATIONALE**: Prevents XSS via cookie/localStorage access
   - **IMPLEMENTATION**: Use blob URL instead of inline srcDoc

✅ **Logs Tab:**
   - **DECISION**: Show server process logs, NOT tool execution logs
   - **RATIONALE**: Tool execution logs require new backend infrastructure
   - **LABEL**: Clearly label as "Server Logs" to avoid confusion

✅ **Testing Scope:**
   - **DECISION**: Basic rendering tests only in Phase 1
   - **RATIONALE**: Ship first, harden later. Don't overinvest in tests initially.

✅ **URL State:**
   - **DECISION**: Store selection in URL params (?server=x&tool=y)
   - **RATIONALE**: Enables deep linking, better UX for returning users

✅ **Heavy Libraries:**
   - **DECISION**: Avoid `react-jsonschema-form`, `react-json-view` in Phase 1
   - **RATIONALE**: Keep bundle size small, Monaco Editor is sufficient

✅ **Implementation Strategy:**
   - **DECISION**: Ship Phase 1 MVP quickly (12-16 hours), then iterate
   - **RATIONALE**: Get user feedback early, validate architecture

---

## Notes for Future Implementation

- Ensure all new components follow existing FluidMCP component patterns
- Reuse existing UI components where possible (buttons, inputs, cards)
- Match existing color scheme and design system
- Consider accessibility (ARIA labels, keyboard navigation)
- Test with various MCP servers (filesystem, database, API servers)
- Document any new environment variables needed
- Consider mobile responsiveness (though inspector is desktop-focused)
- Cache tool lists to avoid refetching (use `useMemo` or React Query)

---

## ⚠️ What NOT to Do (Critical Anti-Patterns)

**Do NOT do these things - they will derail the project:**

1. ❌ **Do NOT create new backend endpoints** - reuse existing `/api/servers` endpoints
2. ❌ **Do NOT install `react-jsonschema-form`** - too heavy, use Monaco Editor in Phase 1
3. ❌ **Do NOT build complex form generation** - JSON mode is sufficient for Phase 1
4. ❌ **Do NOT use `sandbox="allow-same-origin"`** - massive XSS vulnerability
5. ❌ **Do NOT write comprehensive tests initially** - basic rendering tests only
6. ❌ **Do NOT try to build all features at once** - ship Phase 1 MVP first
7. ❌ **Do NOT mix agent logic with inspector** - keep them separate (Phase 2)
8. ❌ **Do NOT add tool execution history database** - keep in memory for Phase 1
9. ❌ **Do NOT add real-time log streaming** - manual refresh in Phase 1
10. ❌ **Do NOT over-engineer** - simple is better, iterate based on user feedback

**Remember**: The goal is to ship a working inspector quickly, not to build the perfect inspector on day one.

---

---

## 🎯 Final Professional Verdict

**This plan is:**
- ✅ **Structured** - Clear phases with defined scope
- ✅ **Secure** - Multiple security layers (sandboxing, sanitization, platform boundary)
- ✅ **Incremental** - Ship MVP quickly, iterate based on feedback
- ✅ **Realistic** - 12-16 hours for Phase 1 is achievable
- ✅ **Strategically Aligned** - Completes FluidMCP as unified AI platform

**If implemented exactly as written, it will scale.**

**Key Success Factors:**
1. Backend reuse (no new routes) keeps complexity low
2. Phased approach enables fast feedback loops
3. JSON-only Phase 1 prevents premature optimization
4. Centralized state management enables future features
5. Security-first design protects production deployments

**Go/No-Go Decision**: 🟢 **GO** - All architectural risks mitigated

---

**Last Updated:** 2026-02-25 (Final revision with architectural clarifications)
**Plan Status:** ✅ Ready for implementation after PRs merge
**Phase Strategy:** 1 MVP → 1.5 Enhanced → 1.75 Forms → 2 Agent Integration
**Review Status:** ✅ Senior architecture review complete with final clarifications
**Risk Level:** 🟢 LOW
