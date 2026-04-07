// import React from "react";
import { useState, useEffect, useRef } from "react";

// Compact collapsible result bubble for chat mode
function ChatResultBubble({ result }: { result: unknown }) {
  const [expanded, setExpanded] = useState(true);
  const [viewMode, setViewMode] = useState<"formatted" | "raw">("formatted");
  const isMcp = typeof result === "object" && result !== null &&
    "content" in result && Array.isArray((result as any).content);
  const isMcpArray = Array.isArray(result) && result.length > 0 &&
    (result as any[]).every((i: any) => typeof i === "object" && i !== null && "type" in i);
  const preview = typeof result === "object" && result !== null
    ? `{${Object.keys(result as object).length} keys}`
    : String(result).slice(0, 60);

  const tabStyle = (active: boolean) => ({
    padding: "0.2rem 0.5rem", borderRadius: "0.25rem", border: "none",
    fontSize: "0.75rem", fontWeight: 500 as const, cursor: "pointer",
    background: active ? "#fff" : "transparent",
    color: active ? "#000" : "rgba(255,255,255,0.6)"
  });

  return (
    <div style={{ fontSize: "0.8rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <button
          onClick={() => setExpanded(v => !v)}
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: "#22c55e", fontWeight: 600, padding: "0.25rem 0",
            fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.3rem"
          }}
        >
          {expanded ? "▼" : "▶"} Result:{!expanded && <span style={{ color: "rgba(255,255,255,0.6)", fontWeight: 400, marginLeft: "0.3rem" }}>{preview}</span>}
        </button>
        {expanded && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <div style={{ display: "flex", background: "rgba(0,0,0,0.3)", borderRadius: "0.25rem", padding: "0.15rem", gap: "0.15rem" }}>
              <button style={tabStyle(viewMode === "formatted")} onClick={() => setViewMode("formatted")}>Formatted</button>
              <button style={tabStyle(viewMode === "raw")} onClick={() => setViewMode("raw")}>Raw JSON</button>
            </div>
            <button
              onClick={() => navigator.clipboard.writeText(JSON.stringify(result, null, 2))}
              style={{ ...tabStyle(false), border: "1px solid rgba(63,63,70,0.5)", borderRadius: "0.25rem" }}
              title="Copy to clipboard"
            >
              Copy
            </button>
          </div>
        )}
      </div>
      {expanded && (
        <div style={{
          maxHeight: "260px", overflowY: "auto", overflowX: "hidden",
          background: "rgba(0,0,0,0.3)",
          border: "1px solid rgba(63,63,70,0.5)",
          borderRadius: "0.5rem",
          padding: "0.75rem",
          marginTop: "0.25rem",
          width: "100%", boxSizing: "border-box",
        }}>
          {viewMode === "raw"
            ? <pre style={{ margin: 0, fontSize: "0.75rem", color: "#e5e7eb", whiteSpace: "pre-wrap", wordBreak: "break-all", fontFamily: "ui-monospace, monospace", width: "100%", boxSizing: "border-box" as const }}>{JSON.stringify(result, null, 2)}</pre>
            : <div style={{ minWidth: 0, width: "100%", overflow: "hidden" }}>
                {(isMcp || isMcpArray)
                  ? <McpContentView content={isMcpArray ? result as any : (result as any).content} />
                  : <JsonResultView data={result} />
                }
              </div>
          }
        </div>
      )}
    </div>
  );
}
// ── Animated thinking indicator ──────────────────────────────────────────────
function ThinkingDots() {
  return (
    <span style={{ display: "inline-flex", gap: "3px", alignItems: "center", marginLeft: "4px" }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: "4px", height: "4px", borderRadius: "50%",
          background: "rgba(255,255,255,0.55)", display: "inline-block",
          animation: `thinking-blink 1.4s infinite ${i * 0.2}s`,
        }} />
      ))}
    </span>
  );
}

// ── Group flat chat messages into standalone + run blocks ─────────────────────
type DisplayGroup =
  | { kind: "standalone"; msg: ChatMessage }
  | { kind: "run"; runId: string; steps: ChatMessage[]; run?: ExecutionRun }

function groupMessages(messages: ChatMessage[], execHistory: ExecutionRun[]): DisplayGroup[] {
  const runMap = new Map(execHistory.map(r => [r.runId, r]));
  const seen = new Set<string>();
  return messages.reduce<DisplayGroup[]>((acc, msg) => {
    if (!msg.runId) {
      acc.push({ kind: "standalone", msg });
    } else if (!seen.has(msg.runId)) {
      seen.add(msg.runId);
      acc.push({
        kind: "run",
        runId: msg.runId,
        steps: messages.filter(m => m.runId === msg.runId),
        run: runMap.get(msg.runId),
      });
    }
    return acc;
  }, []);
}

// ── Timeline block for one agent turn (thinking → tool_call → tool_result) ───
function ExecutionRunBlock({ steps, run, sessionId }: { steps: ChatMessage[]; run?: ExecutionRun; sessionId?: string }) {
  const [collapsed, setCollapsed] = useState(false);
  const thinking  = steps.find(s => s.type === "thinking");
  const toolCall  = steps.find(s => s.type === "tool_call");
  const toolResult = steps.find(s => s.type === "tool_result");
  const errorStep = steps.find(s => s.type === "error");
  const isActive  = !toolResult && !errorStep; // run still in progress

  const totalMs    = run?.endTime ? run.endTime - run.startTime : null;
  const thinkingMs = (toolCall?.perfMark && thinking?.perfMark)
    ? Math.round(toolCall.perfMark - thinking.perfMark) : null;
  const toolMs     = (toolResult?.perfMark && toolCall?.perfMark)
    ? Math.round(toolResult.perfMark - toolCall.perfMark) : null;

  const dot = (color: string) => (
    <div style={{ width: "7px", height: "7px", borderRadius: "50%", background: color, marginTop: "4px", flexShrink: 0 }} />
  );

  return (
    <div style={{ maxWidth: "90%", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "10px", overflow: "hidden" }}>
      {/* Header */}
      <div
        onClick={() => setCollapsed(v => !v)}
        style={{
          display: "flex", alignItems: "center", gap: "0.5rem",
          padding: "0.45rem 0.75rem",
          background: "rgba(255,255,255,0.04)", cursor: "pointer",
          borderBottom: collapsed ? "none" : "1px solid rgba(63,63,70,0.25)",
        }}
      >
        <span style={{ fontSize: "0.7rem", opacity: 0.45 }}>{collapsed ? "▶" : "▼"}</span>
        <span style={{ fontSize: "0.8rem", fontWeight: 600 }}>
          {toolCall ? `🔧 ${toolCall.toolName}` : errorStep ? "❌ Error" : "🤖 Thinking"}
        </span>
        {isActive && <ThinkingDots />}
        {totalMs !== null && (
          <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "rgba(99,102,241,0.7)", fontFamily: "monospace" }}>
            {totalMs}ms
          </span>
        )}
      </div>

      {!collapsed && (
        <div style={{ padding: "0.6rem 0.75rem", display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {/* Thinking step */}
          {thinking && (
            <div style={{ display: "flex", gap: "0.6rem" }}>
              {dot("#3b82f6")}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "0.72rem", color: "#60a5fa", fontWeight: 600, display: "flex", gap: "0.4rem", alignItems: "center" }}>
                  Thinking
                  {thinkingMs !== null && <span style={{ fontWeight: 400, opacity: 0.65 }}>{thinkingMs}ms</span>}
                  {isActive && <ThinkingDots />}
                </div>
                <div style={{ fontSize: "0.73rem", opacity: 0.6, fontStyle: "italic", marginTop: "0.15rem" }}>
                  {thinking.content}
                </div>
              </div>
            </div>
          )}

          {/* Tool call step */}
          {toolCall && (
            <div style={{ display: "flex", gap: "0.6rem" }}>
              {dot("#f59e0b")}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "0.72rem", color: "#fbbf24", fontWeight: 600 }}>
                  Tool: {toolCall.toolName}
                </div>
                <pre style={{
                  margin: "0.2rem 0 0", padding: "0.35rem 0.5rem",
                  background: "rgba(0,0,0,0.3)", borderRadius: "6px",
                  fontSize: "0.7rem", overflowX: "auto", whiteSpace: "pre-wrap",
                  wordBreak: "break-all", color: "#e5e7eb", fontFamily: "ui-monospace,monospace",
                }}>
                  {JSON.stringify(toolCall.params, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* Result step */}
          {toolResult && (
            <div style={{ display: "flex", gap: "0.6rem" }}>
              {dot("#22c55e")}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "0.72rem", color: "#4ade80", fontWeight: 600, display: "flex", gap: "0.4rem", alignItems: "center" }}>
                  Result
                  {toolMs !== null && <span style={{ fontWeight: 400, opacity: 0.65 }}>{toolMs}ms</span>}
                </div>
                <div style={{ marginTop: "0.2rem" }}>
                  <ChatResultBubble result={toolResult.result} />
                </div>
                {toolResult.resourceUri && sessionId && toolCall && (
                  <WidgetSandbox
                    sessionId={sessionId}
                    resourceUri={toolResult.resourceUri}
                    toolInput={toolCall.params || {}}
                    toolResult={toolResult.result}
                  />
                )}
              </div>
            </div>
          )}

          {/* Error step */}
          {errorStep && (
            <div style={{ display: "flex", gap: "0.6rem" }}>
              {dot("#ef4444")}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "0.72rem", color: "#fca5a5", fontWeight: 600 }}>Error</div>
                <div style={{ fontSize: "0.73rem", color: "#fca5a5", marginTop: "0.15rem" }}>
                  {errorStep.content}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { apiClient } from "@/services/api";
import { JsonSchemaForm } from '../components/form/JsonSchemaForm';
import { ToolResult } from '../components/result/ToolResult';
import { JsonResultView } from '../components/result/JsonResultView';
import { McpContentView } from '../components/result/McpContentView';
import { WidgetSandbox } from '../components/WidgetSandbox';
import { PanelGroup, Panel , PanelResizeHandle} from 'react-resizable-panels';

// Type for server object
interface MCPServer {
  id: string;
  session_id: string | null;
  server_info?: any;
  tools: any[];
  url: string;
  transport: string;
  status: 'connecting' | 'connected' | 'disconnected' | 'failed';
  error?: string;
  auth?: {
    type: "none" | "bearer" | "header"
    token?: string
    headerKey?: string
    headerValue?: string
  };
}

// Type for log entry
interface LogEntry {
  timestamp: string;
  type: 'connect' | 'disconnect' | 'tool_call' | 'tool_result' | 'tool_error' | 'chat';
  message: string;
}

type ChatMessage = {
  id: string
  runId?: string       // groups thinking + tool_call + tool_result for one agent turn
  type: "user" | "thinking" | "tool_call" | "tool_result" | "assistant" | "error"
  content?: string
  toolName?: string
  params?: any
  result?: any
  resourceUri?: string // set on tool_result when tool has _meta["ui/resourceUri"]
  timestamp: number
  perfMark?: number    // high-res mark for duration math (performance.now())
}

type ExecutionRun = {
  runId: string
  serverId: string
  startTime: number    // Date.now() — wall time
  endTime?: number     // set on completion or error
  steps: ChatMessage[] // thinking + tool_call + tool_result in order
}
// Helper to generate unique server IDs
const generateServerId = () => `server_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

export default function MCPInspector() {

  const [authType, setAuthType] = useState<"none" | "bearer" | "header">("none")

  const [token, setToken] = useState("")
  const [headerKey, setHeaderKey] = useState("")
  const [headerValue, setHeaderValue] = useState("")

  const [showAddModal, setShowAddModal] = useState(false);
  const [url, setUrl] = useState("");
  const [transport, setTransport] = useState("http");
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [connecting, setConnecting] = useState(false);
  const [selectedServerId, setSelectedServerId] = useState<string | null>(null);
  
  // Derived state: always fresh selectedServer from servers array
  const selectedServer = servers.find(s => s.id === selectedServerId) || null;

  const [selectedTool, setSelectedTool] = useState<any | null>(null)
  const [toolResult, setToolResult] = useState<any | null>(null)
  const [toolError, setToolError] = useState<string | null>(null)
  const [executing, setExecuting] = useState(false)
  const [executionTime, setExecutionTime] = useState<number | null>(null)
  // 3A-4: typed per-server execution history
  const [executionHistoryByServer, setExecutionHistoryByServer] = useState<Record<string, ExecutionRun[]>>({})
  const executionHistory = executionHistoryByServer[selectedServerId ?? ""] ?? []

  const [mode, setMode] = useState<"manual" | "chat">("manual")

  const [chatInput, setChatInput] = useState("")
  // 3A-2: Per-server logs
  const [logsByServer, setLogsByServer] = useState<Record<string, LogEntry[]>>({})
  const logs = logsByServer[selectedServerId ?? ""] ?? []

  // 3A-3: Per-server chat memory
  const [chatHistoryByServer, setChatHistoryByServer] = useState<Record<string, ChatMessage[]>>({})
  const chatHistory = chatHistoryByServer[selectedServerId ?? ""] ?? []

  // Helper to update chat for the currently selected server
  const updateChat = (updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
    if (!selectedServerId) return;
    setChatHistoryByServer(prev => ({
      ...prev,
      [selectedServerId]: typeof updater === "function"
        ? updater(prev[selectedServerId] ?? [])
        : updater
    }));
  };

  const [chatLoading, setChatLoading] = useState(false)
  const [panelSizes, setPanelSizes] = useState({
    left: 25,     // percentage (right auto-calculated as 100-left)
    logs: 35      // percentage of left panel height
  })
  const logsRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  const handleConnect = async () => {

    if (!url) return;
    if (authType === "bearer" && !token) {
      alert("Please enter bearer token")
      return
    }

    if (authType === "header" && (!headerKey || !headerValue)) {
      alert("Please enter header key and value")
      return
    }
    if (servers.some(s => s.url === url && s.status !== "failed")) {
      alert("Server already added");
      return;
    }

    // Disconnect any currently connected server before adding a new one
    const activeServer = servers.find(s => s.status === "connected" && s.session_id);
    if (activeServer) {
      try {
        await apiClient.disconnectInspectorServer(activeServer.session_id!);
        setServers(prev =>
          prev.map(s =>
            s.id === activeServer.id
              ? { ...s, session_id: null, tools: [], status: "disconnected" as const, error: undefined }
              : s
          )
        );
      } catch (err) {
        console.warn("Could not disconnect old server:", err);
        // Non-fatal — continue connecting the new one
      }
    }

    const serverId = generateServerId();

    const authConfig = {
      type: authType,
      token: token,
      headerKey: headerKey,
      headerValue: headerValue
    };

    try {
      setConnecting(true);

      setServers(prev => [
        ...prev.filter(s => !(s.url === url && s.status === "failed")),
        { id: serverId, session_id: null, url, transport, tools: [], status: "connecting" as const, auth : authConfig
        },
      ]);

      const payload: any = { url, transport }

      // Bearer Token
      if (authType === "bearer" && token) {
        payload.auth = {type: "bearer", token: token }
      }

      // Header Token
      if (authType === "header" && headerKey && headerValue) {
        payload.headers = { [headerKey]: headerValue }
      }

      const res = await apiClient.connectInspectorServer(payload)


      setServers(prev =>
        prev.map(s =>
          s.id === serverId
            ? { ...s, session_id: res.session_id, server_info: res.server_info, tools: res.tools || [], status: "connected" as const }
            : s
        )
      );

      setSelectedServerId(serverId);
      setSelectedTool(null);
      setToolResult(null);
      setToolError(null);

      // Set welcome message for this server (preserve other servers' histories)
      setChatHistoryByServer(prev => ({
        ...prev,
        [serverId]: [{
          id: crypto.randomUUID(),
          type: "assistant",
          content: `Connected to ${res.server_info?.name || "new server"}. Chat cleared — ready to go!`,
          timestamp: Date.now(),
        }]
      }));

      setAuthType("none")
      setToken("")
      setHeaderKey("")
      setHeaderValue("")
      setShowAddModal(false);
      setUrl("");
      setTransport("http");

    } catch (err: any) {
      console.error("Failed to connect", err);
      setServers(prev =>
        prev.map(s =>
          s.id === serverId
            ? { ...s, status: "failed" as const, error: err?.message || "Failed to connect to MCP server" }
            : s
        )
      );
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async (serverId: string) => {
    const server = servers.find((s) => s.id === serverId);
    if (!server?.session_id) return;

    try {
      await apiClient.disconnectInspectorServer(server.session_id);

      // Update server to disconnected state (keep in list)
      setServers((prev) =>
        prev.map((s) =>
          s.id === serverId
            ? {
                ...s,
                session_id: null,
                tools: [],
                status: 'disconnected' as const,
                error: undefined,
              }
            : s
        )
      );

      if (selectedServer?.id === serverId) {
        setSelectedServerId(null);
      }
    } catch (err) {
      console.error("Failed to disconnect", err);
      alert("Failed to disconnect from MCP server");
    }
  };

  const handleReconnect = async (serverId: string) => {
    const server = servers.find((s) => s.id === serverId);
    if (!server) return;
    
    // Prevent spamming reconnect button
    if (server.status === 'connecting') return;

    try {
      // Set to connecting state
      setServers((prev) =>
        prev.map((s) =>
          s.id === serverId
            ? { ...s, status: 'connecting' as const, error: undefined }
            : s
        )
      );
      // Build payload with auth
      const payload: any = {
        url: server.url,
        transport: server.transport,
      };

      // Bearer
      if (server.auth?.type === "bearer" && server.auth.token) {
        payload.auth = {
          type: "bearer",
          token: server.auth.token,
        };
      }

      // Header
      if (
        server.auth?.type === "header" &&
        server.auth.headerKey &&
        server.auth.headerValue
      ) {
        payload.headers = {
          [server.auth.headerKey]: server.auth.headerValue,
        };
      }
      
      const res = await apiClient.connectInspectorServer(payload);
      // Update with connected state and new session
      setServers((prev) =>
        prev.map((s) =>
          s.id === serverId
            ? {
                ...s,
                session_id: res.session_id,
                server_info: res.server_info,
                tools: res.tools || [],
                status: 'connected' as const,
              }
            : s
        )
      );
      // Append reconnect notice to existing chat history (don't wipe it)
      setChatHistoryByServer(prev => ({
        ...prev,
        [serverId]: [
          ...(prev[serverId] ?? []),
          {
            id: crypto.randomUUID(),
            type: "assistant" as const,
            content: `Reconnected to ${res.server_info?.name || "server"}.`,
            timestamp: Date.now(),
          }
        ]
      }));
    } catch (err: any) {
      console.error("Failed to reconnect", err);

      // Update with failed state
      setServers((prev) =>
        prev.map((s) =>
          s.id === serverId
            ? {
                ...s,
                status: 'failed' as const,
                error: err?.message || 'Failed to reconnect to MCP server',
              }
            : s
        )
      );
    }
  };

  const handleRemove = (serverId: string) => {
    setServers((prev) => prev.filter((s) => s.id !== serverId));
    // Clean up per-server state
    setLogsByServer(prev => { const n = { ...prev }; delete n[serverId]; return n; });
    setChatHistoryByServer(prev => { const n = { ...prev }; delete n[serverId]; return n; });
    setExecutionHistoryByServer(prev => { const n = { ...prev }; delete n[serverId]; return n; });
    if (selectedServerId === serverId) setSelectedServerId(null);
  };

  const runTool = async (params: any) => {
    if (!selectedServer?.session_id || !selectedTool || executing) return;

    try {
      setExecuting(true);
      setToolError(null);

      const start = performance.now();

      const res = await apiClient.runInspectorTool(
        selectedServer.session_id,
        selectedTool.name,
        params
      );

      const end = performance.now();

      setToolResult(res);
      setExecutionTime((end - start) / 1000);
      if (selectedServerId) {
        const runId = crypto.randomUUID();
        const run: ExecutionRun = {
          runId,
          serverId: selectedServerId,
          startTime: Date.now() - Math.round(end - start),
          endTime: Date.now(),
          steps: [
            { id: crypto.randomUUID(), runId, type: "tool_call", toolName: selectedTool.name, params, timestamp: Date.now(), perfMark: start },
            { id: crypto.randomUUID(), runId, type: "tool_result", result: res, timestamp: Date.now(), perfMark: end },
          ]
        };
        setExecutionHistoryByServer(prev => ({ ...prev, [selectedServerId]: [run, ...(prev[selectedServerId] ?? [])] }));
      }
    } catch (err: any) {
      console.error(err);
      setToolError(err?.message || "Tool execution failed");
    } finally {
      setExecuting(false);
    }
  };

  // Stable UUID helper — falls back for non-secure contexts (e.g. plain HTTP)
  const generateId = () =>
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `msg_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

 const runChatTool = async () => {
  // Guard against concurrent requests
  if (!chatInput || !selectedServer?.session_id || chatLoading || !selectedServerId) return

  const message = chatInput
  setChatInput("")

  const userMsg: ChatMessage = {
    id: generateId(),
    type: "user",
    content: message,
    timestamp: Date.now(),
    perfMark: performance.now()
  }

  // Capture history with userMsg before any state updates — used below to
  // send an accurate chat_history to the backend (avoids stale closure).
  const nextHistory = [...chatHistory, userMsg]

  updateChat(prev => [...prev, userMsg])

  // 3A-4: start an ExecutionRun for this agent turn
  const runId = crypto.randomUUID()
  const runStartTime = Date.now()
  const runSteps: ChatMessage[] = []
  const capturedServerId = selectedServerId

  try {
    setChatLoading(true)

    const thinkingMsg: ChatMessage = {
      id: crypto.randomUUID(),
      runId,
      type: "thinking",
      content: "Deciding which tool to use...",
      timestamp: Date.now(),
      perfMark: performance.now()
    }

    updateChat(prev => [...prev, thinkingMsg])
    runSteps.push(thinkingMsg)

    const res = await apiClient.chatWithInspector(
      selectedServer.session_id,
      {
        message,
        chat_history: nextHistory.slice(-8).map((m: ChatMessage) => ({
          type: m.type,
          content: m.content
        }))
      }
    )

    updateChat(prev => prev.filter((m: ChatMessage) => m.id !== thinkingMsg.id))

    if (res.clarification_needed) {
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        runId,
        type: "assistant",
        content: res.message,
        timestamp: Date.now(),
        perfMark: performance.now()
      }
      updateChat(prev => [...prev, assistantMsg])
      // save run (no tool call — just clarification)
      setExecutionHistoryByServer(prev => ({
        ...prev,
        [capturedServerId]: [{ runId, serverId: capturedServerId, startTime: runStartTime, endTime: Date.now(), steps: runSteps }, ...(prev[capturedServerId] ?? [])]
      }))
      return
    }

    const toolCallMsg: ChatMessage = {
      id: crypto.randomUUID(),
      runId,
      type: "tool_call",
      toolName: res.tool_name,
      params: res.params,
      timestamp: Date.now(),
      perfMark: performance.now()
    }

    updateChat(prev => [...prev, toolCallMsg])
    runSteps.push(toolCallMsg)

    const result = await apiClient.runInspectorTool(
      selectedServer.session_id,
      res.tool_name,
      res.params
    )

    // Check for UI widget resource — can be on the tool definition (tools/list)
    // or on the result itself (FastMCP puts _meta on the result, not the tool def)
    const toolDef = selectedServer.tools.find((t: any) => t.name === res.tool_name)
    const resourceUri: string | undefined =
      toolDef?._meta?.["ui/resourceUri"] ||
      toolDef?._meta?.ui?.resourceUri ||
      result?.result?._meta?.["ui/resourceUri"] ||
      result?.result?._meta?.ui?.resourceUri ||
      undefined

    const resultMsg: ChatMessage = {
      id: crypto.randomUUID(),
      runId,
      type: "tool_result",
      result,
      resourceUri,
      timestamp: Date.now(),
      perfMark: performance.now()
    }

    updateChat(prev => [...prev, resultMsg])
    runSteps.push(resultMsg)

    // save completed run
    setExecutionHistoryByServer(prev => ({
      ...prev,
      [capturedServerId]: [{ runId, serverId: capturedServerId, startTime: runStartTime, endTime: Date.now(), steps: runSteps }, ...(prev[capturedServerId] ?? [])]
    }))

  } catch (err: any) {

    const errorMsg: ChatMessage = {
      id: crypto.randomUUID(),
      runId,
      type: "error",
      content: err?.message || "Chat error",
      timestamp: Date.now(),
      perfMark: performance.now()
    }

    updateChat(prev => [...prev, errorMsg])
    runSteps.push(errorMsg)

    // save failed run
    setExecutionHistoryByServer(prev => ({
      ...prev,
      [capturedServerId]: [{ runId, serverId: capturedServerId, startTime: runStartTime, endTime: Date.now(), steps: runSteps }, ...(prev[capturedServerId] ?? [])]
    }))
  } finally {
    setChatLoading(false)
  }
}

  useEffect(() => {
    setToolResult(null)
    setToolError(null)
    setExecutionTime(null)
  }, [selectedTool])

  // ── Session persistence ────────────────────────────────────────────────────
  // Restore servers + selected server on mount (survives page navigation)
  useEffect(() => {
    const savedServers = sessionStorage.getItem('inspector-servers')
    const savedSelectedId = sessionStorage.getItem('inspector-selected-server-id')

    if (savedServers) {
      try {
        const parsed: MCPServer[] = JSON.parse(savedServers)
        // Any mid-connect server was interrupted — treat as disconnected on restore
        const restored = parsed.map(s =>
          s.status === 'connecting'
            ? { ...s, status: 'disconnected' as const, session_id: null }
            : s
        )
        setServers(restored)
      } catch {
        // ignore malformed storage
      }
    }

    if (savedSelectedId) setSelectedServerId(savedSelectedId)
  }, [])

  // Persist servers list whenever it changes
  useEffect(() => {
    sessionStorage.setItem('inspector-servers', JSON.stringify(servers))
  }, [servers])

  // Persist selected server ID whenever it changes
  useEffect(() => {
    if (selectedServerId) {
      sessionStorage.setItem('inspector-selected-server-id', selectedServerId)
    } else {
      sessionStorage.removeItem('inspector-selected-server-id')
    }
  }, [selectedServerId])

  useEffect(() => {
    const saved = sessionStorage.getItem('inspector-panel-sizes')
    if (saved) setPanelSizes(JSON.parse(saved))
  }, [])

  // Auto-scroll logs to bottom when new entries arrive
  useEffect(() => {
    logsRef.current?.scrollTo({ top: logsRef.current.scrollHeight });
  }, [logs]);

  // Auto-scroll chat to bottom when new messages arrive
  // Uses rAF so scroll runs after the DOM (including dynamic result content) has painted
  useEffect(() => {
    requestAnimationFrame(() => {
      chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
    });
  }, [chatHistoryByServer, selectedServerId]);

  // Fetch logs from the server (3A-2: stored per-server)
  const fetchLogs = async () => {
    if (!selectedServer?.session_id || !selectedServerId) return;
    try {
      const res = await apiClient.getInspectorLogs(selectedServer.session_id);
      setLogsByServer(prev => ({ ...prev, [selectedServerId]: res.logs || [] }));
    } catch (err) {
      console.error("Failed to fetch logs", err);
    }
  };

  // Poll for logs every 2 seconds when a session is active
  useEffect(() => {
    if (!selectedServer?.session_id) return;
    fetchLogs();
    const interval = setInterval(fetchLogs, 2000);
    return () => clearInterval(interval);
  }, [selectedServer?.session_id]);

  // Color mapping for log types
  const logColors: Record<string, string> = {
    connect: "#10b981",
    disconnect: "#6b7280",
    tool_call: "#3b82f6",
    tool_result: "#22c55e",
    tool_error: "#ef4444",
    chat: "#6366f1",
  };

  useEffect(() => {
    setToken("")
    setHeaderKey("")
    setHeaderValue("")
  }, [authType])

  return (
    <div
      className="dashboard"
      style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}
    >
      <style>{`@keyframes thinking-blink{0%,80%,100%{opacity:0}40%{opacity:1}}`}</style>
      <Navbar />

      <div style={{ paddingTop: "64px", flex: 1, display: "flex", flexDirection: "column" }}>
        <div
          style={{
            maxWidth: "1600px",
            width: "100%",
            margin: "0 auto",
            padding: "2rem",
            flex: 1,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* Page Header */}
          <div style={{ marginBottom: "1.5rem" }}>
            <h1 style={{ fontSize: "2rem", fontWeight: "bold" }}>
              MCP Inspector
            </h1>
            <p style={{ color: "rgba(255,255,255,0.6)", marginTop: "0.5rem" }}>
              Connect to any MCP server and inspect its tools.
            </p>
          </div>

          {/* Main Layout — fills remaining height */}
          <PanelGroup 
            direction="horizontal" 
            onLayout={(sizes) => {
              setPanelSizes(prev => {
                const updated = { ...prev, left: sizes[0] };
                sessionStorage.setItem('inspector-panel-sizes', JSON.stringify(updated));
                return updated;
              });
            }}
            style={{ 
              flex: 1,
              // Minimum height so it doesn't collapse
              minHeight: "calc(100vh - 220px)",
            }}
          >
            {/* ── LEFT PANEL (outer) ─────────────────────────────────────── */}
            <Panel 
              defaultSize={panelSizes.left} 
              minSize={18} 
              maxSize={50}
              style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}
            >
              {/* LEFT PANEL INNER: vertical split — Servers+Tools (top) / Logs (bottom) */}
              <PanelGroup 
                direction="vertical" 
                onLayout={(sizes) => {
                  setPanelSizes(prev => {
                    const updated = { ...prev, logs: sizes[1] };
                    sessionStorage.setItem('inspector-panel-sizes', JSON.stringify(updated));
                    return updated;
                  });
                }}
                style={{ flex: 1, height: "100%" }}
              >

                {/* ── TOP: Servers + Tools ────────────────────────────────── */}
                <Panel 
                  defaultSize={100 - panelSizes.logs} 
                  minSize={30}
                  style={{ overflow: "auto", display: "flex", flexDirection: "column" }}
                >
                  <div
                    style={{
                      border: "1px solid rgba(63,63,70,0.5)",
                      borderRadius: "0.75rem",
                      padding: "1.25rem",
                      background: "linear-gradient(to bottom right, rgba(39,39,42,0.9), rgba(24,24,27,0.9))",
                      height: "100%",
                      boxSizing: "border-box",
                      display: "flex",
                      flexDirection: "column",
                      overflow: "auto",
                    }}
                  >
                    {/* Header */}
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        flexShrink: 0,
                      }}
                    >
                      <h2 style={{ fontSize: "1.1rem", fontWeight: "600" }}>
                        Servers
                      </h2>

                      <button
                        style={{
                          background: "#fff",
                          color: "#000",
                          border: "none",
                          padding: "0.35rem 0.75rem",
                          borderRadius: "0.375rem",
                          fontSize: "0.8rem",
                          fontWeight: "600",
                          cursor: "pointer",
                        }}
                        onClick={() => setShowAddModal(true)}
                      >
                        + Add
                      </button>
                    </div>

                    {/* Servers List or Empty State */}
                    <div
                      style={{
                        marginTop: "1rem",
                        padding: servers.length === 0 ? "1rem" : "0",
                        border: servers.length === 0 ? "1px dashed rgba(63,63,70,0.6)" : "none",
                        borderRadius: "0.5rem",
                        textAlign: servers.length === 0 ? "center" : "left",
                        color: "rgba(255,255,255,0.6)",
                        flex: 1,
                        overflow: "auto",
                      }}
                    >
                      {servers.length === 0 ? (
                        <div>No servers connected</div>
                      ) : (
                        servers.map((server) => {
                          const statusConfig = {
                            connecting: { text: "Connecting...", bg: "rgba(59,130,246,0.2)", color: "#3b82f6" },
                            connected:  { text: "Connected",    bg: "rgba(16,185,129,0.2)",  color: "#10b981" },
                            disconnected: { text: "Disconnected", bg: "rgba(107,114,128,0.2)", color: "#6b7280" },
                            failed:     { text: "Failed",       bg: "rgba(239,68,68,0.2)",    color: "#ef4444" },
                          };

                          const statusInfo = statusConfig[server.status];
                          const isSelected = selectedServer?.id === server.id;

                          return (
                            <div
                              key={server.id}
                              onClick={() => {
                                if (selectedServerId === server.id) return;

                                setSelectedServerId(server.id);
                                setSelectedTool(null);
                                setToolResult(null);
                                setToolError(null);
                                // 3A-3: preserve chat history on switch (no reset)
                                
                              }}
                              style={{
                                marginTop: "0.75rem",
                                padding: "0.9rem",
                                border: "1px solid rgba(63,63,70,0.6)",
                                borderRadius: "0.6rem",
                                cursor: "pointer",
                                background: isSelected ? "rgba(255,255,255,0.08)" : "transparent",
                              }}
                            >
                              {/* HEADER */}
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ fontWeight: "600", fontSize: "0.9rem" }}>
                                  {server?.server_info?.name || "MCP Server"}
                                </div>
                                <span
                                  style={{
                                    fontSize: "0.7rem",
                                    padding: "0.2rem 0.5rem",
                                    borderRadius: "0.3rem",
                                    background: statusInfo.bg,
                                    color: statusInfo.color,
                                    flexShrink: 0,
                                  }}
                                >
                                  {statusInfo.text}
                                </span>
                              </div>

                              {/* URL */}
                              <div
                                style={{
                                  marginTop: "0.3rem",
                                  fontSize: "0.75rem",
                                  color: "rgba(255,255,255,0.5)",
                                  wordBreak: "break-all",
                                }}
                              >
                                {server.url}
                              </div>
                              <div style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.4)" }}>
                                transport: {server.transport}
                              </div>

                              {/* ERROR */}
                              {server.status === "failed" && server.error && (
                                <div
                                  style={{
                                    marginTop: "0.5rem",
                                    fontSize: "0.75rem",
                                    color: "#ef4444",
                                    padding: "0.4rem",
                                    background: "rgba(239,68,68,0.1)",
                                    borderRadius: "0.3rem",
                                    wordBreak: "break-word",
                                  }}
                                >
                                  {server.error}
                                </div>
                              )}

                              {/* ACTION BUTTONS */}
                              <div style={{ marginTop: "0.6rem", display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                                {server.status === "connected" && (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); handleDisconnect(server.id); }}
                                    style={{
                                      fontSize: "0.75rem", padding: "0.25rem 0.6rem",
                                      borderRadius: "0.35rem", border: "1px solid rgba(63,63,70,0.6)",
                                      background: "transparent", color: "#fff", cursor: "pointer",
                                    }}
                                  >
                                    Disconnect
                                  </button>
                                )}

                                {server.status === "disconnected" && (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); handleReconnect(server.id); }}
                                    style={{
                                      fontSize: "0.75rem", padding: "0.25rem 0.6rem",
                                      borderRadius: "0.35rem", border: "1px solid rgba(107,114,128,0.6)",
                                      background: "rgba(107,114,128,0.1)", color: "#fff", cursor: "pointer",
                                    }}
                                  >
                                    Reconnect
                                  </button>
                                )}

                                {server.status === "failed" && (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); handleReconnect(server.id); }}
                                    style={{
                                      fontSize: "0.75rem", padding: "0.25rem 0.6rem",
                                      borderRadius: "0.35rem", border: "1px solid rgba(239,68,68,0.6)",
                                      background: "rgba(239,68,68,0.1)", color: "#ef4444", cursor: "pointer",
                                    }}
                                  >
                                    Retry
                                  </button>
                                )}

                                {server.status !== "connecting" && (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); handleRemove(server.id); }}
                                    style={{
                                      fontSize: "0.75rem", padding: "0.25rem 0.4rem",
                                      borderRadius: "0.35rem", border: "1px solid rgba(63,63,70,0.6)",
                                      background: "transparent", color: "rgba(255,255,255,0.6)", cursor: "pointer",
                                    }}
                                    title="Remove server"
                                  >
                                    ✕
                                  </button>
                                )}
                              </div>

                              {/* TOOLS (only show when selected) */}
                              {isSelected && server?.tools?.map((tool: any) => (
                                <div
                                  key={tool.name}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedTool(tool);
                                    setToolResult(null);
                                    setToolError(null);
                                  }}
                                  style={{
                                    marginLeft: "0.5rem",
                                    marginTop: "0.4rem",
                                    fontSize: "0.82rem",
                                    cursor: "pointer",
                                    color: selectedTool?.name === tool.name ? "#fff" : "rgba(255,255,255,0.65)",
                                    padding: "0.2rem 0.4rem",
                                    borderRadius: "0.25rem",
                                    background: selectedTool?.name === tool.name ? "rgba(255,255,255,0.08)" : "transparent",
                                  }}
                                >
                                  • {tool.name}
                                </div>
                              ))}
                            </div>
                          );
                        })
                      )}
                    </div>

                  </div>
                </Panel>

                {/* ── Vertical resize handle ─────────────────────────────── */}
                <PanelResizeHandle
                  style={{
                    height: "5px",
                    cursor: "row-resize",
                    background: "rgba(63,63,70,0.4)",
                    flexShrink: 0,
                    transition: "background 0.15s",
                    borderRadius: "2px",
                  }}
                  onMouseEnter={(e: any) => { e.currentTarget.style.background = "rgba(99,102,241,0.6)"; }}
                  onMouseLeave={(e: any) => { e.currentTarget.style.background = "rgba(63,63,70,0.4)"; }}
                />

                {/* ── BOTTOM: Logs ─────────────────────────────────────────── */}
                <Panel 
                  defaultSize={panelSizes.logs} 
                  minSize={12}
                  style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}
                >
                  <div
                    style={{
                      border: "1px solid rgba(63,63,70,0.5)",
                      borderRadius: "0.75rem",
                      background: "linear-gradient(to bottom right, rgba(39,39,42,0.9), rgba(24,24,27,0.9))",
                      height: "100%",
                      boxSizing: "border-box",
                      display: "flex",
                      flexDirection: "column",
                      overflow: "hidden",
                    }}
                  >
                    {/* Logs header */}
                    <div style={{ padding: "0.75rem 1rem 0.5rem", flexShrink: 0, borderBottom: "1px solid rgba(63,63,70,0.3)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div>
                        <span style={{ fontSize: "0.8rem", fontWeight: "600", color: "rgba(255,255,255,0.7)", fontFamily: "monospace" }}>
                          LOGS
                        </span>
                        {logs.length > 0 && (
                          <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: "rgba(255,255,255,0.35)" }}>
                            {logs.length} entries
                          </span>
                        )}
                      </div>
                      {logs.length > 0 && selectedServerId && (
                        <button
                          onClick={() => setLogsByServer(prev => ({ ...prev, [selectedServerId]: [] }))}
                          style={{ fontSize: "0.7rem", background: "none", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "4px", color: "rgba(255,255,255,0.4)", cursor: "pointer", padding: "0.15rem 0.4rem" }}
                        >
                          Clear
                        </button>
                      )}
                    </div>

                    {/* Logs content */}
                    <div
                      ref={logsRef}
                      style={{
                        flex: 1,
                        overflowY: "auto",
                        overflowX: "hidden",
                        padding: "0.5rem 0.75rem",
                        fontFamily: "monospace",
                        fontSize: "0.78rem",
                      }}
                    >
                      {logs.length === 0 ? (
                        <div style={{
                          display: "flex", alignItems: "center", justifyContent: "center",
                          height: "100%", color: "rgba(255,255,255,0.35)", fontSize: "0.8rem",
                        }}>
                          {selectedServer?.session_id ? "No logs yet" : "Connect to a server to see logs"}
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          {[...logs].reverse().map((log, i) => {
                            const color = logColors[log.type] || "#9ca3af";
                            return (
                              <div
                                key={i}
                                style={{
                                  display: "grid",
                                  // Fixed columns: time | type | message
                                  // time ~70px, type ~90px, message gets rest
                                  gridTemplateColumns: "70px 90px 1fr",
                                  gap: "0.5rem",
                                  paddingBottom: "3px",
                                  borderBottom: "1px solid rgba(63,63,70,0.2)",
                                  alignItems: "start",
                                }}
                              >
                                {/* Time */}
                                <span style={{ opacity: 0.45, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                  {new Date(log.timestamp).toLocaleTimeString()}
                                </span>
                                {/* Type */}
                                <span style={{ color, fontWeight: "700", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                  {log.type.toUpperCase()}
                                </span>
                                {/* Message — grid child auto-constrains width, word-break works correctly */}
                                <span style={{ color: "rgba(255,255,255,0.75)", wordBreak: "break-word", overflowWrap: "break-word" }}>
                                  {log.message}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </Panel>

              </PanelGroup>
            </Panel>

            {/* ── Horizontal resize handle ───────────────────────────────── */}
            <PanelResizeHandle
              style={{
                width: "5px",
                cursor: "col-resize",
                background: "rgba(63,63,70,0.4)",
                flexShrink: 0,
                transition: "background 0.15s",
                borderRadius: "2px",
              }}
              onMouseEnter={(e: any) => { e.currentTarget.style.background = "rgba(99,102,241,0.6)"; }}
              onMouseLeave={(e: any) => { e.currentTarget.style.background = "rgba(63,63,70,0.4)"; }}
            />

            {/* ── RIGHT PANEL ───────────────────────────────────────────── */}
            <Panel 
              defaultSize={100 - panelSizes.left} 
              minSize={50}
              style={{ overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 0 }}
            >
              <div
                style={{
                  border: "1px solid rgba(63,63,70,0.5)",
                  borderRadius: "0.75rem",
                  padding: "1.5rem",
                  background: "linear-gradient(to bottom right, rgba(39,39,42,0.9), rgba(24,24,27,0.9))",
                  height: "100%",
                  boxSizing: "border-box",
                  display: "flex",
                  flexDirection: "column",
                  overflow: "hidden",
                  minHeight: 0,
                }}
              >
                <h2 style={{ fontSize: "1.1rem", fontWeight: "600", flexShrink: 0 }}>
                  Tool Execution
                </h2>

                {/* Mode tabs */}
                <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", flexShrink: 0 }}>
                  <button
                    onClick={() => setMode("manual")}
                    style={{
                      padding: "0.35rem 0.75rem", borderRadius: "0.35rem",
                      border: "1px solid rgba(63,63,70,0.6)",
                      background: mode === "manual" ? "#fff" : "transparent",
                      color: mode === "manual" ? "#000" : "#fff",
                      cursor: "pointer",
                    }}
                  >
                    Manual
                  </button>
                  <button
                    onClick={() => setMode("chat")}
                    style={{
                      padding: "0.35rem 0.75rem", borderRadius: "0.35rem",
                      border: "1px solid rgba(63,63,70,0.6)",
                      background: mode === "chat" ? "#fff" : "transparent",
                      color: mode === "chat" ? "#000" : "#fff",
                      cursor: "pointer",
                    }}
                  >
                    Chat
                  </button>
                </div>

                {/* ── MANUAL MODE ─── */}
                <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", marginTop: "1rem", minHeight: 0 }}>
                  {mode === "manual" && selectedServer && selectedTool && (
                    <div>
                      <h3 style={{ marginBottom: "1rem" }}>{selectedTool.name}</h3>

                      {selectedServer.status === "connected" ? (
                        <>
                          <JsonSchemaForm
                            schema={selectedTool.inputSchema}
                            onSubmit={runTool}
                            submitLabel="Run Tool"
                            loading={executing}
                          />

                          {(toolResult || toolError) && (
                            <div style={{ marginTop: "2rem" }}>
                              <ToolResult
                                result={toolResult}
                                error={toolError || undefined}
                                executionTime={executionTime}
                              />
                            </div>
                          )}
                        </>
                      ) : (
                        <div style={{
                          padding: "1rem", border: "1px dashed rgba(239,68,68,0.6)",
                          borderRadius: "0.5rem", textAlign: "center", color: "rgba(239,68,68,0.8)",
                        }}>
                          Server is not connected. Please reconnect to run tools.
                        </div>
                      )}
                    </div>
                  )}

                  {/* ── CHAT MODE ─── */}
                  {mode === "chat" && selectedServer && (
                    <div style={{ display: "grid", gridTemplateRows: "1fr auto", flex: 1, minHeight: 0, overflow: "hidden" }}>
                      {selectedServer.status === "connected" ? (
                        <>
                          {/* Chat History — grid row 1 (1fr = all remaining space) */}
                          <div
                            ref={chatRef}
                            style={{
                              overflowY: "auto",
                              minHeight: 0,
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.5rem",
                              padding: "0.5rem 0.5rem 0.75rem 0.25rem"
                            }}
                          >
                            {groupMessages(chatHistory, executionHistory).map((group) => {
                              if (group.kind === "run") {
                                return (
                                  <div key={group.runId} style={{ display: "flex", justifyContent: "flex-start" }}>
                                    <ExecutionRunBlock steps={group.steps} run={group.run} sessionId={selectedServer?.session_id ?? undefined} />
                                  </div>
                                );
                              }

                              const msg = group.msg;

                              if (msg.type === "user") {
                                return (
                                  <div key={msg.id} style={{ display: "flex", justifyContent: "flex-end" }}>
                                    <div style={{
                                      background: "#2563eb", color: "#fff",
                                      padding: "0.6rem 0.75rem",
                                      borderRadius: "12px 12px 4px 12px",
                                      maxWidth: "70%", fontSize: "0.9rem", lineHeight: 1.4
                                    }}>
                                      {msg.content}
                                    </div>
                                  </div>
                                );
                              }

                              if (msg.type === "assistant") {
                                return (
                                  <div key={msg.id} style={{ display: "flex", justifyContent: "flex-start" }}>
                                    <div style={{
                                      background: "rgba(99,102,241,0.15)",
                                      border: "1px solid rgba(99,102,241,0.3)",
                                      padding: "0.6rem 0.75rem",
                                      borderRadius: "12px 12px 12px 4px",
                                      maxWidth: "70%", fontSize: "0.9rem"
                                    }}>
                                      {msg.content}
                                    </div>
                                  </div>
                                );
                              }

                              return null;
                            })}
                            <div ref={chatBottomRef} />
                          </div>

                          {/* Chat Input — grid row 2 (auto height, always at bottom) */}
                          <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", paddingTop: "0.5rem" }}>
                          {chatHistory.length > 1 && selectedServerId && (
                            <div style={{ display: "flex", justifyContent: "flex-end" }}>
                              <button
                                onClick={() => setChatHistoryByServer(prev => ({ ...prev, [selectedServerId]: [] }))}
                                style={{ fontSize: "0.7rem", background: "none", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "4px", color: "rgba(255,255,255,0.4)", cursor: "pointer", padding: "0.15rem 0.4rem" }}
                              >
                                Clear Chat
                              </button>
                            </div>
                          )}
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <input
                              value={chatInput}
                              disabled={chatLoading}
                              onChange={(e) => setChatInput(e.target.value)}
                              placeholder="Ask something..."
                              onKeyDown={(e) => { 
                                if (e.key === "Enter" && !e.shiftKey && chatInput.trim()) {
                                  e.preventDefault(); 
                                  runChatTool();
                                } 
                              }}
                              style={{
                                flex: 1, minWidth: 0, padding: "0.5rem",
                                borderRadius: "0.35rem", border: "1px solid rgba(63,63,70,0.6)",
                                background: "#09090b", color: "#fff", opacity: chatLoading ? 0.6 : 1,
                              }}
                            />
                            <button
                              onClick={()=>{
                                if (chatInput.trim()) runChatTool();
                              }}
                              disabled={chatLoading || !chatInput.trim()}
                              style={{
                                padding: "0.5rem 0.75rem", borderRadius: "0.35rem",
                                background: "#fff", color: "#000", fontWeight: "600", flexShrink: 0,
                                opacity: chatLoading || !chatInput.trim() ? 0.6 : 1,
                                cursor: chatLoading || !chatInput.trim() ? "not-allowed" : "pointer"
                              }}
                            >
                              {chatLoading ? "Thinking..." : "Send"}
                            </button>
                          </div>
                          </div>
                        </>
                      ) : (
                        <div style={{
                          padding: "1rem", border: "1px dashed rgba(239,68,68,0.6)",
                          borderRadius: "0.5rem", textAlign: "center", color: "rgba(239,68,68,0.8)",
                        }}>
                          Server is not connected. Please reconnect to chat.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Empty states */}
                  {mode === "manual" && (!selectedServer || !selectedTool) && (
                    <div style={{
                      padding: "1rem", border: "1px dashed rgba(63,63,70,0.6)",
                      borderRadius: "0.5rem", textAlign: "center", color: "rgba(255,255,255,0.6)",
                    }}>
                      Select a tool to execute
                    </div>
                  )}
                  {mode === "chat" && (!selectedServer || selectedServer.status !== "connected") && (
                    <div style={{
                      padding: "1rem", border: "1px dashed rgba(63,63,70,0.6)",
                      borderRadius: "0.5rem", textAlign: "center", color: "rgba(255,255,255,0.6)",
                    }}>
                      {!selectedServer ? "Select a connected server to chat" : "Server is not connected. Please reconnect to chat."}
                    </div>
                  )}
                </div>
              </div>
            </Panel>

          </PanelGroup>
        </div>
      </div>

      {/* ── ADD SERVER MODAL ─────────────────────────────────────────────── */}
      {showAddModal && (
        <div
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
            display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "#18181b", padding: "2rem", borderRadius: "0.75rem",
              width: "420px", border: "1px solid rgba(63,63,70,0.6)",
            }}
          >
            <h2 style={{ fontSize: "1.3rem", marginBottom: "1rem" }}>Connect MCP Server</h2>

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <input
                placeholder="Server URL"
                style={{
                  padding: "0.6rem", borderRadius: "0.4rem",
                  border: "1px solid rgba(63,63,70,0.6)",
                  background: "#09090b", color: "#fff",
                }}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />

              <select
                value={transport}
                onChange={(e) => setTransport(e.target.value)}
                style={{
                  padding: "0.6rem", borderRadius: "0.4rem",
                  border: "1px solid rgba(63,63,70,0.6)",
                  background: "#09090b", color: "#fff",
                }}
              >
                <option value="http">HTTP</option>
                <option value="sse">SSE</option>
              </select>

              {/* Auth Type */}
              <div style={{ marginTop: "1rem" }}>
                <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)" }}>
                  Auth Type
                </label>

                <select
                  value={authType}
                  onChange={(e) => setAuthType(e.target.value as any)}
                  style={{
                    width: "100%",
                    marginTop: "0.3rem",
                    padding: "0.5rem",
                    borderRadius: "0.4rem",
                    background: "#18181b",
                    color: "#fff",
                    border: "1px solid rgba(63,63,70,0.6)"
                  }}
                >
                  <option value="none">None</option>
                  <option value="bearer">Bearer Token</option>
                  <option value="header">Header Token</option>
                </select>
              </div>

              {authType === "bearer" && (
                <div style={{ marginTop: "0.8rem" }}>
                  <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)" }}>
                    Token
                  </label>
                  <input
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="Enter bearer token"
                    style={{
                      width: "100%",
                      marginTop: "0.3rem",
                      padding: "0.5rem",
                      borderRadius: "0.4rem",
                      background: "#18181b",
                      color: "#fff",
                      border: "1px solid rgba(63,63,70,0.6)"
                    }}
                  />
                </div>
              )}

              {authType === "header" && (
                <div style={{ marginTop: "0.8rem" }}>
                  
                  <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)" }}>
                    Header Key
                  </label>
                  <input
                    value={headerKey}
                    onChange={(e) => setHeaderKey(e.target.value)}
                    placeholder="X-Api-Key"
                    style={{
                      width: "100%",
                      marginTop: "0.3rem",
                      padding: "0.5rem",
                      borderRadius: "0.4rem",
                      background: "#18181b",
                      color: "#fff",
                      border: "1px solid rgba(63,63,70,0.6)"
                    }}
                  />

                  <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)", marginTop: "0.5rem", display: "block" }}>
                    Header Value
                  </label>
                  <input
                    type="password"
                    value={headerValue}
                    onChange={(e) => setHeaderValue(e.target.value)}
                    placeholder="Enter token"
                    style={{
                      width: "100%",
                      marginTop: "0.3rem",
                      padding: "0.5rem",
                      borderRadius: "0.4rem",
                      background: "#18181b",
                      color: "#fff",
                      border: "1px solid rgba(63,63,70,0.6)"
                    }}
                  />
                </div>
              )}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                <button
                  onClick={() => setShowAddModal(false)}
                  style={{
                    background: "transparent", border: "1px solid rgba(63,63,70,0.6)",
                    padding: "0.5rem 1rem", borderRadius: "0.4rem", color: "#fff",
                  }}
                >
                  Cancel
                </button>

                <button
                  onClick={handleConnect}
                  disabled={connecting}
                  style={{
                    background: "#fff", color: "#000",
                    padding: "0.5rem 1rem", borderRadius: "0.4rem", fontWeight: "600",
                  }}
                >
                  {connecting ? "Connecting..." : "Connect"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}