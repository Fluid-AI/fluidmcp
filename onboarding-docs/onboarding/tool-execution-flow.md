# Tool Execution Flow (UI)

**Scope:** End-to-end trace of what happens when a user runs a tool from the ToolRunner page — from React component down to the MCP subprocess and back.

---

## Entry Path

The ToolRunner page is reached by navigating inside the SPA:

```
/ui  →  Dashboard  →  click server card "View Details"
     →  ServerDetails (/servers/:id)  →  Tools tab  →  click "Run" on a tool
     →  ToolRunner (/servers/:id/tools/:toolName)
```

---

## Full Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — ToolRunner mounts                                        │
│  Route: /servers/:serverId/tools/:toolName                          │
│                                                                     │
│  useParams() extracts serverId + toolName                           │
│                                                                     │
│  useEffect on mount:                                                │
│    ├── apiClient.getServerDetails(serverId)                         │
│    │     GET /api/servers/:id          → server name, config        │
│    └── apiClient.getServerTools(serverId)                           │
│          GET /api/servers/:id/tools    → tools[] with inputSchema   │
│                                                                     │
│  Finds matching tool by name → sets tool state                      │
│  Renders <JsonSchemaForm schema={tool.inputSchema} />               │
│    → auto-generates form fields from JSON Schema                    │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ user fills form + clicks "Run Tool"
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  handleSubmit(values)  →  execute(values)  [from useToolRunner]     │
│                                                                     │
│  useToolRunner.execute():                                           │
│    1. setLoading(true), setError(null), setResult(null)             │
│    2. startTime = performance.now()                                 │
│    3. await apiClient.runTool(serverId, toolName, args)             │
│         POST /api/servers/:serverId/tools/:toolName/run             │
│         Body: { arguments: { ...formValues } }                      │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP POST
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY                                                    │
│  Handler in management.py                                           │
│    → validates bearer token (if secure mode)                        │
│    → looks up server in ServerManager                               │
│    → calls server_manager.run_tool(server_id, tool_name, args)      │
│                                                                     │
│  server_manager.py:                                                 │
│    → acquires per-server threading.Lock                             │
│    → builds JSON-RPC request:                                       │
│        {                                                            │
│          "jsonrpc": "2.0", "id": N,                                 │
│          "method": "tools/call",                                    │
│          "params": { "name": toolName, "arguments": args }          │
│        }                                                            │
│    → writes to process.stdin + flushes                              │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ JSON-RPC over stdio (subprocess pipe)
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MCP SUBPROCESS (e.g. npx @modelcontextprotocol/server-filesystem)  │
│    → reads JSON-RPC from stdin                                      │
│    → executes tool logic (e.g. fs.readFileSync)                     │
│    → writes JSON-RPC response to stdout:                            │
│        {                                                            │
│          "jsonrpc": "2.0", "id": N,                                 │
│          "result": {                                                 │
│            "content": [{ "type": "text", "text": "..." }]          │
│          }                                                          │
│        }                                                            │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ stdout readline
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI GATEWAY                                                    │
│    → reads response from process.stdout                             │
│    → releases threading.Lock                                        │
│    → returns HTTP 200 { result: ... }                               │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ HTTP 200
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER — useToolRunner.execute() resumes                          │
│    → endTime = performance.now()                                    │
│    → executionTime = (endTime - startTime) / 1000   (seconds)       │
│    → setResult(response)                                            │
│    → setExecutionTime(executionTime)                                │
│    → setLoading(false)                                              │
│                                                                     │
│  toolHistoryService.saveExecution({                                 │
│    serverId, serverName, toolName,                                  │
│    arguments: args,                                                 │
│    result: response, success: true,                                 │
│    executionTime                                                    │
│  })  →  written to localStorage                                     │
│                                                                     │
│  ToolRunner re-renders:                                             │
│    → layout switches from single-column to 2-column grid            │
│    → right column renders <ToolResult result={result} />            │
│    → "Execution History" button appears (badge shows count)         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Error Path

If the tool call fails (network error, MCP error, timeout):

```
useToolRunner.execute() catch block:
  → setError(errorMessage)
  → setExecutionTime(duration)       ← still recorded
  → setLoading(false)
  → toolHistoryService.saveExecution({ ..., success: false, error: errorMessage })

ToolRunner renders:
  → <ToolResult error={executionError} />  in the right column
  → history entry marked with red "✗ Failed" badge
```

---

## Key Files

| File | Role in this flow |
|---|---|
| `src/pages/ToolRunner.tsx` | Mounts, loads server + tool schema, renders form + result |
| `src/hooks/useToolRunner.ts` | Executes tool, tracks timing, manages localStorage history |
| `src/services/api.ts` | `runTool()` — POST `/api/servers/:id/tools/:name/run` |
| `src/components/form/JsonSchemaForm.tsx` | Auto-generates form fields from `tool.inputSchema` |
| `src/components/result/ToolResult.tsx` | Renders result — auto-detects JSON / Table / Text / MCP format |
| `src/services/toolHistory.ts` | Persists execution history in `localStorage` |
| `src/types/server.ts` | `ToolExecution`, `ToolExecutionResponse`, `JsonSchema` types |

---

## Result Format Detection (`ToolResult.tsx`)

`ToolResult` receives the raw response and picks a renderer automatically:

| Condition | Renderer |
|---|---|
| Response has MCP `content[]` array | `McpContentView` — handles text / image / resource blocks |
| Response is an array of objects | `TableResultView` — renders as a sortable table |
| Response is a plain object or complex JSON | `JsonResultView` — syntax-highlighted JSON |
| Response is a string or number | `TextResultView` — monospace text |

---

## Tool History (localStorage)

`toolHistoryService` (`src/services/toolHistory.ts`) stores executions per `serverId + toolName` key:

- Max entries per tool: 50 (LRU eviction)
- Stored as JSON in `localStorage`
- "Load Parameters" in the history drawer calls `loadFromHistory(id)` → re-populates the form with previous arguments
- History persists across browser sessions (until cleared or localStorage is wiped)
