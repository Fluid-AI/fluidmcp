import React, { useState, useEffect, useRef } from "react";

// Compact collapsible result bubble for chat mode
function ChatResultBubble({ result, initialView = "formatted", hideTabSwitcher = false }: { result: unknown; initialView?: "formatted" | "raw"; hideTabSwitcher?: boolean }) {
  const [expanded, setExpanded] = useState(true);
  const [viewMode, setViewMode] = useState<"formatted" | "raw">(initialView);
  useEffect(() => { setViewMode(initialView); }, [initialView]);
  const isMcp = typeof result === "object" && result !== null &&
    "content" in result && Array.isArray((result as any).content);
  const isMcpArray = Array.isArray(result) && result.length > 0 &&
    (result as any[]).every((i: any) => typeof i === "object" && i !== null && "type" in i);
  const preview = (() => {
    if (isMcp) {
      const texts = ((result as any).content || []).filter((c: any) => c.type === "text" && c.text);
      if (texts.length > 0) return String(texts[0].text).slice(0, 80);
      return `[${(result as any).content?.length || 0} items]`;
    }
    if (isMcpArray) {
      const texts = (result as any[]).filter((c: any) => c.type === "text" && c.text);
      if (texts.length > 0) return String(texts[0].text).slice(0, 80);
      return `[${(result as any[]).length} items]`;
    }
    if (typeof result === "object" && result !== null) return `{${Object.keys(result as object).length} keys}`;
    return String(result).slice(0, 60);
  })();

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
        {expanded && !hideTabSwitcher && (
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
          background: "rgba(0,0,0,0.3)",
          border: "1px solid rgba(63,63,70,0.5)",
          borderRadius: "0.5rem",
          padding: "0.75rem",
          marginTop: "0.25rem",
          width: "100%", boxSizing: "border-box",
          maxHeight: "350px",
          overflowY: "auto",
        }}>
          {viewMode === "raw"
            ? <pre style={{ margin: 0, fontSize: "0.75rem", color: "#e5e7eb", whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "ui-monospace, monospace", width: "100%", boxSizing: "border-box" as const }}>{JSON.stringify(result, null, 2)}</pre>
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
    <span style={{ fontStyle: "italic", color: "rgba(255,255,255,0.4)", fontSize: "0.72rem" }}>
      Thinking
      <span style={{ display: "inline-flex", gap: "1px" }}>
        {[0, 1, 2].map(i => (
          <span key={i} style={{ animation: `thinking-blink 1.4s ease-in-out ${i * 0.2}s infinite` }}>.</span>
        ))}
      </span>
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
function ExecutionRunBlock({ steps, run }: { steps: ChatMessage[]; run?: ExecutionRun }) {
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
    <div style={{ width: "100%", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "10px" }}>
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
                {toolCall.params && Object.keys(toolCall.params).length > 0 ? (
                  <div style={{ marginTop: "0.25rem", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                    {Object.entries(toolCall.params).map(([k, v]) => (
                      <div key={k} style={{ display: "flex", gap: "0.4rem", alignItems: "baseline", fontSize: "0.7rem" }}>
                        <span style={{ color: "#fbbf24", opacity: 0.7, fontFamily: "monospace", flexShrink: 0 }}>{k}</span>
                        <span style={{ color: "rgba(255,255,255,0.2)", flexShrink: 0 }}>→</span>
                        <span style={{
                          background: "rgba(0,0,0,0.25)", borderRadius: "4px",
                          padding: "0.05rem 0.35rem", color: "#e5e7eb", fontFamily: "monospace",
                          wordBreak: "break-all",
                        }}>
                          {typeof v === "string" ? v : JSON.stringify(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.3)", fontStyle: "italic" }}>no params</span>
                )}
              </div>
            </div>
          )}

          {/* Result step */}
          {toolResult && (
            <div style={{ display: "flex", gap: "0.6rem" }}>
              {dot("#22c55e")}
              <div style={{ flex: 1 }}>
                {/* Result label */}
                <div style={{ fontSize: "0.72rem", color: "#4ade80", fontWeight: 600, display: "flex", gap: "0.4rem", alignItems: "center" }}>
                  Result
                  {toolMs !== null && <span style={{ fontWeight: 400, opacity: 0.65 }}>{toolMs}ms</span>}
                </div>
                {/* Result bubble — always shows Formatted/Raw tabs */}
                <div style={{ marginTop: "0.2rem" }}>
                  <ChatResultBubble result={toolResult.result} />
                </div>
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
import { apiClient } from "@/services/api";
import { type SavedRequest, loadSavedRequests, saveRequest, deleteSavedRequest } from "@/lib/saved-requests";
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
  name?: string;       // optional custom display name (overrides server_info.name)
  server_info?: any;
  tools: any[];
  url: string;
  command?: string;    // stdio only — the full command string used to spawn the process
  transport: string;
  status: 'connecting' | 'connected' | 'disconnected' | 'failed';
  connectedAt?: number; // timestamp (ms) when status became "connected"
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
interface MCPResource {
  uri: string;
  name?: string;
  mimeType?: string;
  description?: string;
  isTemplate?: boolean;
}

// Helper to generate unique server IDs
const generateServerId = () => `server_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

/** Returns a compact relative time string, e.g. "2m ago", "1h ago", "just now" */
function relativeTime(ts: number): string {
  const secs = Math.floor((Date.now() - ts) / 1000);
  if (secs < 10) return "just now";
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ago`;
}

export default function MCPInspector() {

  const [authType, setAuthType] = useState<"none" | "bearer" | "header">("none")

  const [token, setToken] = useState("")
  const [headerKey, setHeaderKey] = useState("")
  const [headerValue, setHeaderValue] = useState("")

  const [inspectorFullscreen, setInspectorFullscreen] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [envVars, setEnvVars] = useState<{ key: string; value: string }[]>([]);
  const [customName, setCustomName] = useState("");
  const [transport, setTransport] = useState("http");

  // Recently connected URLs (up to 3) — persisted in localStorage, no auth data stored
  const [recentUrls, setRecentUrls] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem("mcp_inspector_recent_urls") || "[]"); }
    catch { return []; }
  });
  const addRecentUrl = (newUrl: string) => {
    setRecentUrls(prev => {
      const updated = [newUrl, ...prev.filter(u => u !== newUrl)].slice(0, 3);
      try { localStorage.setItem("mcp_inspector_recent_urls", JSON.stringify(updated)); } catch {}
      return updated;
    });
  };
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
  const [lastRunParams, setLastRunParams] = useState<any | null>(null)
  const [copyRequestToast, setCopyRequestToast] = useState(false)
  const [toolSubTab, setToolSubTab] = useState<"tools" | "saved">("tools")
  const [savedRequests, setSavedRequests] = useState<SavedRequest[]>([])
  const [saveDialogOpen, setSaveDialogOpen] = useState(false)
  const [saveTitle, setSaveTitle] = useState("")
  const [formPrefill, setFormPrefill] = useState<Record<string, any> | undefined>(undefined)
  // 3A-4: typed per-server execution history
  const [executionHistoryByServer, setExecutionHistoryByServer] = useState<Record<string, ExecutionRun[]>>({})
  const executionHistory = executionHistoryByServer[selectedServerId ?? ""] ?? []

  const [mode, setMode] = useState<"manual" | "chat" | "resources" | "prompts">("manual")

  // 4B: Resources tab state
  const [resourcesByServer, setResourcesByServer] = useState<Record<string, MCPResource[]>>({})
  const resources = resourcesByServer[selectedServerId ?? ""] ?? []
  const [selectedResourceUri, setSelectedResourceUri] = useState<string | null>(null)
  const [resourceContent, setResourceContent] = useState<{ text?: string; blob?: string; mimeType?: string } | null>(null)
  const [resourcesLoading, setResourcesLoading] = useState(false)
  const [resourceContentLoading, setResourceContentLoading] = useState(false)
  // Template param inputs: { paramName → value }
  const [templateParams, setTemplateParams] = useState<Record<string, string>>({})

  // 4B: Prompts tab state
  const [promptsByServer, setPromptsByServer] = useState<Record<string, any[]>>({})
  const prompts = promptsByServer[selectedServerId ?? ""] ?? []
  const [selectedPrompt, setSelectedPrompt] = useState<any | null>(null)
  const [promptArgs, setPromptArgs] = useState<Record<string, string>>({})
  const [promptResult, setPromptResult] = useState<any | null>(null)
  const [promptsLoading, setPromptsLoading] = useState(false)
  const [promptResultLoading, setPromptResultLoading] = useState(false)

  const [chatInput, setChatInput] = useState("")
  // 3A-2: Per-server logs
  const [logsByServer, setLogsByServer] = useState<Record<string, LogEntry[]>>({})
  const logs = logsByServer[selectedServerId ?? ""] ?? []
  // Tracks how many backend logs to skip per server after a manual clear.
  // Using a ref so the polling closure always reads the latest value.
  const logsClearedOffsetRef = useRef<Record<string, number>>({})
  // 5B: Log filter pill state
  const [logFilter, setLogFilter] = useState<'all' | 'connect' | 'tool_call' | 'tool_error' | 'chat'>('all')
  const [logSearch, setLogSearch] = useState('')
  const [toolSearch, setToolSearch] = useState('')
  const filteredLogs = logs.filter(l => {
    const matchesType = logFilter === 'all' ? true
      : logFilter === 'tool_error' ? l.type === 'tool_error'
      : logFilter === 'tool_call' ? (l.type === 'tool_call' || l.type === 'tool_result')
      : l.type === logFilter;
    const matchesSearch = logSearch.trim() === '' || l.message.toLowerCase().includes(logSearch.toLowerCase());
    return matchesType && matchesSearch;
  })

  // 3A-3: Per-server chat memory
  const [chatHistoryByServer, setChatHistoryByServer] = useState<Record<string, ChatMessage[]>>({})
  const chatHistory = chatHistoryByServer[selectedServerId ?? ""] ?? []

  // 5A: System prompt + dialog state
  const [systemPrompt, setSystemPrompt] = useState("")
  const [systemPromptDraft, setSystemPromptDraft] = useState("")
  const [systemPromptOpen, setSystemPromptOpen] = useState(false)

  // 5A: Multi-provider LLM selector (UI panel lives in 5A branch; only settings read here)
  type LLMProvider = "groq" | "openai" | "anthropic" | "gemini"
  const loadLLMSettings = () => {
    try {
      const raw = localStorage.getItem("fmcp_llm_settings")
      if (raw) return JSON.parse(raw)
    } catch { /* ignore */ }
    return { provider: "groq", model: "llama-3.1-8b-instant", apiKeys: {} }
  }
  const [llmSettings] = useState<{
    provider: LLMProvider; model: string; apiKeys: Record<string, string>
  }>(loadLLMSettings)

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

  // Tick every 30s to refresh relative timestamps on server cards
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const [chatLoading, setChatLoading] = useState(false)
  const [panelSizes, setPanelSizes] = useState({
    left: 25,     // percentage (right auto-calculated as 100-left)
    logs: 35      // percentage of left panel height
  })
  const logsRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  const handleConnect = async () => {

    if (transport === "stdio") {
      if (!command.trim()) return;
    } else {
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

      const serverUrl = transport === "stdio" ? `stdio://${command.trim().split(" ")[0]}` : url;

      setServers(prev => [
        ...prev.filter(s => !(s.url === serverUrl && s.status === "failed")),
        { id: serverId, session_id: null, url: serverUrl, transport, tools: [], status: "connecting" as const, auth: authConfig,
          ...(customName.trim() ? { name: customName.trim() } : {}),
          ...(transport === "stdio" ? { name: customName.trim() || command.trim().split(" ").slice(0, 3).join(" "), command: command.trim() } : {}),
        },
      ]);

      const envVarsObj = envVars.reduce((acc, { key, value }) => {
        if (key.trim()) acc[key.trim()] = value;
        return acc;
      }, {} as Record<string, string>);

      const payload: any = transport === "stdio"
        ? { command: command.trim(), transport, ...(Object.keys(envVarsObj).length ? { env_vars: envVarsObj } : {}) }
        : { url, transport }

      // Bearer Token (not applicable for stdio)
      if (transport !== "stdio" && authType === "bearer" && token) {
        payload.auth = { type: "bearer", token: token }
      }

      // Header Token (not applicable for stdio)
      if (transport !== "stdio" && authType === "header" && headerKey && headerValue) {
        payload.headers = { [headerKey]: headerValue }
      }

      const res = await apiClient.connectInspectorServer(payload)


      // Reset log offset for this server — new session, fresh log stream
      logsClearedOffsetRef.current = { ...logsClearedOffsetRef.current, [serverId]: 0 };

      const displayName = customName.trim() || res.server_info?.name || "new server";

      setServers(prev =>
        prev.map(s =>
          s.id === serverId
            ? { ...s, session_id: res.session_id, server_info: res.server_info, tools: res.tools || [], status: "connected" as const,
                connectedAt: Date.now(),
                ...(customName.trim() ? { name: customName.trim() } : {}) }
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
          content: `Connected to ${displayName}. Chat cleared — ready to go!`,
          timestamp: Date.now(),
        }]
      }));

      if (transport !== "stdio") addRecentUrl(url);
      setAuthType("none")
      setToken("")
      setHeaderKey("")
      setHeaderValue("")
      setCustomName("")
      setCommand("")
      setEnvVars([])
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
      // Build payload — stdio uses command, http/sse use url
      const payload: any = server.transport === "stdio"
        ? { command: server.command, transport: server.transport }
        : { url: server.url, transport: server.transport };

      // Bearer (not applicable for stdio)
      if (server.transport !== "stdio" && server.auth?.type === "bearer" && server.auth.token) {
        payload.auth = {
          type: "bearer",
          token: server.auth.token,
        };
      }

      // Header (not applicable for stdio)
      if (
        server.transport !== "stdio" &&
        server.auth?.type === "header" &&
        server.auth.headerKey &&
        server.auth.headerValue
      ) {
        payload.headers = {
          [server.auth.headerKey]: server.auth.headerValue,
        };
      }
      
      const res = await apiClient.connectInspectorServer(payload);
      // Reset log offset — reconnect starts a new session with a fresh log stream
      logsClearedOffsetRef.current = { ...logsClearedOffsetRef.current, [serverId]: 0 };
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
                connectedAt: Date.now(),
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
      setLastRunParams(params);

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

 const runChatToolWithMessage = async (message: string) => {
  if (!message || !selectedServer?.session_id || chatLoading || !selectedServerId) return

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
      id: generateId(),
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
        chat_history: nextHistory.slice(-8).map(m => ({
          type: m.type,
          content: m.content
        })),
        provider: llmSettings.provider,
        model: llmSettings.model,
        ...(llmSettings.apiKeys[llmSettings.provider]
          ? { api_key: llmSettings.apiKeys[llmSettings.provider] }
          : {}),
        ...(systemPrompt.trim() ? { system_prompt: systemPrompt.trim() } : {})
      }
    )

    updateChat(prev => prev.filter((m: ChatMessage) => m.id !== thinkingMsg.id))

    if (res.clarification_needed) {
      const assistantMsg: ChatMessage = {
        id: generateId(),
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
      id: generateId(),
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
      id: generateId(),
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
      id: generateId(),
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

  const runChatTool = () => {
    if (chatInput.trim()) {
      const msg = chatInput;
      setChatInput("");
      runChatToolWithMessage(msg);
    }
  }

  useEffect(() => {
    setToolResult(null)
    setToolError(null)
    setExecutionTime(null)
    setLastRunParams(null)
  }, [selectedTool])

  useEffect(() => {
    if (selectedServer?.url) {
      setSavedRequests(loadSavedRequests(selectedServer.url));
      setToolSubTab("tools");
    }
  }, [selectedServer?.url])

  // 4B: Fetch prompts list when Prompts tab becomes active
  useEffect(() => {
    if (mode !== "prompts") return;
    const sessionId = selectedServer?.session_id;
    if (!sessionId) return;
    if (promptsByServer[selectedServerId!]) return;
    setPromptsLoading(true);
    apiClient.listInspectorPrompts(sessionId)
      .then(res => {
        setPromptsByServer(prev => ({ ...prev, [selectedServerId!]: res?.prompts ?? [] }));
      })
      .catch(() => {
        setPromptsByServer(prev => ({ ...prev, [selectedServerId!]: [] }));
      })
      .finally(() => setPromptsLoading(false));
  }, [mode, selectedServer?.session_id])

  // 4B: Fetch resource list when Resources tab becomes active
  useEffect(() => {
    if (mode !== "resources") return;
    const sessionId = selectedServer?.session_id;
    if (!sessionId) return;
    // Already cached for this server — no refetch needed
    if (resourcesByServer[selectedServerId!]) return;
    setResourcesLoading(true);
    apiClient.listInspectorResources(sessionId)
      .then(res => {
        const list: MCPResource[] = res?.resources ?? [];
        setResourcesByServer(prev => ({ ...prev, [selectedServerId!]: list }));
      })
      .catch(() => {
        setResourcesByServer(prev => ({ ...prev, [selectedServerId!]: [] }));
      })
      .finally(() => setResourcesLoading(false));
  }, [mode, selectedServer?.session_id])

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
      const allLogs: LogEntry[] = res.logs || [];
      const offset = logsClearedOffsetRef.current[selectedServerId] ?? 0;
      setLogsByServer(prev => ({ ...prev, [selectedServerId]: allLogs.slice(offset) }));
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
      style={inspectorFullscreen
        ? { position: "fixed", inset: 0, zIndex: 1000, height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden", background: "#09090b", maxWidth: "none", margin: 0, padding: 0 }
        : { height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden", maxWidth: "100%", padding: 0 }
      }
    >
      <style>{`
        @keyframes thinking-blink{0%,100%{opacity:0.2}50%{opacity:1}}
        html, body { overflow: hidden; height: 100%; }
      `}</style>
      {!inspectorFullscreen && <Navbar />}

      <div style={{ paddingTop: inspectorFullscreen ? "0" : "64px", flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div
          style={{
            maxWidth: inspectorFullscreen ? "none" : "1600px",
            width: "100%",
            margin: inspectorFullscreen ? "0" : "0 auto",
            padding: inspectorFullscreen ? "0.4rem 0.5rem" : "2rem",
            flex: 1,
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {/* Page Header — hidden in fullscreen to maximise space */}
          {inspectorFullscreen ? (
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.4rem", flexShrink: 0 }}>
              <button
                onClick={() => setInspectorFullscreen(false)}
                style={{
                  background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: "0.4rem", cursor: "pointer", padding: "0.3rem 0.6rem",
                  fontSize: "0.75rem", color: "rgba(255,255,255,0.7)", display: "flex", alignItems: "center", gap: "0.4rem",
                }}
              >
                ✕ Exit Fullscreen
              </button>
            </div>
          ) : (
            <div style={{ marginBottom: "1.5rem", flexShrink: 0, display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
              <div>
                <h1 style={{ fontSize: "2rem", fontWeight: "bold" }}>MCP Inspector</h1>
                <p style={{ color: "rgba(255,255,255,0.6)", marginTop: "0.5rem" }}>
                  Connect to any MCP server and inspect its tools.
                </p>
              </div>
              <button
                onClick={() => setInspectorFullscreen(true)}
                title="Fullscreen"
                style={{
                  background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: "0.4rem", cursor: "pointer", padding: "0.4rem 0.75rem",
                  fontSize: "0.8rem", color: "rgba(255,255,255,0.7)", display: "flex", alignItems: "center", gap: "0.4rem",
                  marginTop: "0.25rem", flexShrink: 0,
                }}
              >
                ⤢ Fullscreen
              </button>
            </div>
          )}

          {/* Main Layout — fills remaining height, never grows beyond it */}
          <PanelGroup
            key={inspectorFullscreen ? "fs" : "normal"}
            direction="horizontal"
            onLayout={(sizes) => {
              setPanelSizes(prev => {
                const updated = { ...prev, left: sizes[0] };
                sessionStorage.setItem('inspector-panel-sizes', JSON.stringify(updated));
                return updated;
              });
            }}
            style={{ flex: 1, minHeight: 0, overflow: "hidden" }}
          >
            {/* ── LEFT PANEL (outer) ─────────────────────────────────────── */}
            <Panel
              defaultSize={inspectorFullscreen ? Math.min(panelSizes.left, 25) : panelSizes.left}
              minSize={inspectorFullscreen ? 12 : 18}
              maxSize={inspectorFullscreen ? 30 : 50}
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
                style={{ flex: 1, minHeight: 0, overflow: "hidden" }}
              >

                {/* ── TOP: Servers + Tools ────────────────────────────────── */}
                <Panel 
                  defaultSize={100 - panelSizes.logs} 
                  minSize={30}
                  style={{ overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 0 }}
                >
                  <div
                    style={{
                      border: "1px solid rgba(63,63,70,0.5)",
                      borderRadius: "0.75rem",
                      padding: "1.25rem",
                      background: "linear-gradient(to bottom right, rgba(39,39,42,0.9), rgba(24,24,27,0.9))",
                      flex: 1,
                      minHeight: 0,
                      boxSizing: "border-box",
                      display: "flex",
                      flexDirection: "column",
                      overflow: "hidden",
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
                                setToolSearch('');
                                // 3A-3: preserve chat history on switch (no reset)
                                
                              }}
                              style={{
                                marginTop: "0.75rem",
                                padding: "0.9rem",
                                border: isSelected ? "1px solid rgba(99,102,241,0.5)" : "1px solid rgba(63,63,70,0.6)",
                                borderLeft: isSelected ? "3px solid rgba(99,102,241,0.9)" : "3px solid transparent",
                                borderRadius: "0.6rem",
                                cursor: "pointer",
                                background: isSelected ? "rgba(99,102,241,0.08)" : "transparent",
                                transition: "background 0.15s, border-color 0.15s",
                              }}
                            >
                              {/* HEADER */}
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ fontWeight: "600", fontSize: "0.9rem" }}>
                                  {server?.name || server?.server_info?.name || "MCP Server"}
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
                              <div style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.4)", display: "flex", gap: "0.6rem", flexWrap: "wrap", marginTop: "0.15rem" }}>
                                <span>transport: {server.transport}</span>
                                {server.status === "connected" && server.tools.length > 0 && (
                                  <span style={{ color: "rgba(99,102,241,0.8)" }}>{server.tools.length} tool{server.tools.length !== 1 ? "s" : ""}</span>
                                )}
                                {server.status === "connected" && server.connectedAt && (
                                  <span style={{ color: "rgba(34,197,94,0.6)" }}>● {relativeTime(server.connectedAt)}</span>
                                )}
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
                              {isSelected && (server?.tools?.length ?? 0) > 0 && (
                                <>
                                  {/* 5C: Tools | Saved sub-tabs */}
                                  <div style={{ display: "flex", margin: "0.4rem 0.5rem 0.2rem", gap: "0.25rem" }} onClick={e => e.stopPropagation()}>
                                    {(["tools", "saved"] as const).map(tab => (
                                      <button
                                        key={tab}
                                        onClick={() => setToolSubTab(tab)}
                                        style={{
                                          flex: 1, fontSize: "0.68rem", padding: "0.18rem 0",
                                          borderRadius: "4px", cursor: "pointer",
                                          border: toolSubTab === tab ? "1px solid rgba(99,102,241,0.5)" : "1px solid rgba(63,63,70,0.4)",
                                          background: toolSubTab === tab ? "rgba(99,102,241,0.15)" : "transparent",
                                          color: toolSubTab === tab ? "rgba(165,180,252,0.9)" : "rgba(255,255,255,0.4)",
                                          fontWeight: toolSubTab === tab ? 600 : 400,
                                        }}
                                      >
                                        {tab === "tools" ? `Tools (${server.tools.length})` : `Saved (${savedRequests.length})`}
                                      </button>
                                    ))}
                                  </div>

                                  {toolSubTab === "tools" && (
                                    <div style={{ margin: "0 0.5rem 0.2rem", position: "relative" }}>
                                      <input
                                        value={toolSearch}
                                        onChange={e => setToolSearch(e.target.value)}
                                        placeholder="Search tools..."
                                        onClick={e => e.stopPropagation()}
                                        style={{
                                          width: "100%", boxSizing: "border-box",
                                          padding: "0.25rem 1.4rem 0.25rem 1.5rem",
                                          fontSize: "0.7rem", borderRadius: "4px",
                                          border: "1px solid rgba(63,63,70,0.5)",
                                          background: "rgba(0,0,0,0.25)", color: "#fff",
                                        }}
                                      />
                                      <span style={{ position: "absolute", left: "0.4rem", top: "50%", transform: "translateY(-50%)", fontSize: "0.65rem", color: "rgba(255,255,255,0.3)", pointerEvents: "none" }}>⌕</span>
                                      {toolSearch && (
                                        <span
                                          onClick={e => { e.stopPropagation(); setToolSearch(''); }}
                                          style={{ position: "absolute", right: "0.4rem", top: "50%", transform: "translateY(-50%)", fontSize: "0.65rem", color: "rgba(255,255,255,0.4)", cursor: "pointer", lineHeight: 1 }}
                                        >✕</span>
                                      )}
                                    </div>
                                  )}

                                  {/* 5C: Saved requests list */}
                                  {toolSubTab === "saved" && (
                                    <div onClick={e => e.stopPropagation()}>
                                      {savedRequests.length === 0 ? (
                                        <div style={{ margin: "0.5rem", fontSize: "0.72rem", color: "rgba(255,255,255,0.3)", textAlign: "center", padding: "0.5rem" }}>
                                          No saved requests yet.<br />Run a tool and click "Save".
                                        </div>
                                      ) : savedRequests.map(req => (
                                        <div
                                          key={req.id}
                                          style={{
                                            margin: "0.3rem 0.5rem",
                                            padding: "0.35rem 0.5rem",
                                            borderRadius: "5px",
                                            border: "1px solid rgba(63,63,70,0.4)",
                                            background: "rgba(0,0,0,0.2)",
                                            cursor: "pointer",
                                          }}
                                          onClick={() => {
                                            const tool = server.tools.find((t: any) => t.name === req.toolName);
                                            if (tool) {
                                              setSelectedTool(tool);
                                              setFormPrefill(req.params as Record<string, any>);
                                              setToolResult(null);
                                              setToolError(null);
                                              setToolSubTab("tools");
                                            }
                                          }}
                                        >
                                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                              <div style={{ fontSize: "0.72rem", color: "#fff", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{req.title}</div>
                                              <div style={{ fontSize: "0.64rem", color: "rgba(255,255,255,0.4)", marginTop: "0.1rem" }}>{req.toolName}</div>
                                            </div>
                                            <button
                                              onClick={e => {
                                                e.stopPropagation();
                                                deleteSavedRequest(selectedServer.url, req.id);
                                                setSavedRequests(loadSavedRequests(selectedServer.url));
                                              }}
                                              style={{
                                                marginLeft: "0.35rem", fontSize: "0.6rem", padding: "0.1rem 0.3rem",
                                                borderRadius: "3px", border: "1px solid rgba(63,63,70,0.5)",
                                                background: "transparent", color: "rgba(255,255,255,0.3)", cursor: "pointer", flexShrink: 0,
                                              }}
                                              title="Delete saved request"
                                            >✕</button>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </>
                              )}
                              {isSelected && toolSubTab === "tools" && server?.tools?.filter((t: any) =>
                                toolSearch.trim() === '' || t.name.toLowerCase().includes(toolSearch.toLowerCase()) || (t.description ?? '').toLowerCase().includes(toolSearch.toLowerCase())
                              ).map((tool: any) => {
                                const ann = tool.annotations ?? {};
                                const badges = [
                                  ann.readOnlyHint    && { label: "Read-only",   bg: "rgba(63,63,70,0.5)",    color: "rgba(255,255,255,0.5)" },
                                  ann.destructiveHint && { label: "Destructive", bg: "rgba(239,68,68,0.15)",  color: "rgba(252,165,165,0.9)" },
                                  ann.idempotentHint  && { label: "Idempotent",  bg: "rgba(34,197,94,0.12)",  color: "rgba(134,239,172,0.85)" },
                                  ann.openWorldHint   && { label: "External",    bg: "rgba(59,130,246,0.15)", color: "rgba(147,197,253,0.9)" },
                                ].filter(Boolean) as { label: string; bg: string; color: string }[];
                                return (
                                  <div
                                    key={tool.name}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedTool(tool);
                                      setFormPrefill(undefined);
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
                                    <div>• {tool.name}</div>
                                    {badges.length > 0 && (
                                      <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap", marginTop: "0.2rem", marginLeft: "0.6rem" }}>
                                        {badges.map(b => (
                                          <span key={b.label} style={{
                                            fontSize: "0.6rem", padding: "0.05rem 0.3rem", borderRadius: "999px",
                                            background: b.bg, color: b.color, fontWeight: 500,
                                          }}>{b.label}</span>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
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
                    <div style={{ padding: "0.6rem 0.75rem 0.4rem", flexShrink: 0, borderBottom: "1px solid rgba(63,63,70,0.3)" }}>
                      {/* Title row */}
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.4rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                          <span style={{ fontSize: "0.75rem", fontWeight: "600", color: "rgba(255,255,255,0.7)", fontFamily: "monospace" }}>LOGS</span>
                          {logs.length > 0 && (
                            <span style={{ fontSize: "0.65rem", color: "rgba(255,255,255,0.3)" }}>
                              {filteredLogs.length}{logFilter !== 'all' ? `/${logs.length}` : ''}
                            </span>
                          )}
                        </div>
                        {logs.length > 0 && selectedServerId && (
                          <button
                            onClick={() => {
                              if (!selectedServerId) return;
                              const currentOffset = logsClearedOffsetRef.current[selectedServerId] ?? 0;
                              logsClearedOffsetRef.current = { ...logsClearedOffsetRef.current, [selectedServerId]: currentOffset + logs.length };
                              setLogsByServer(prev => ({ ...prev, [selectedServerId]: [] }));
                            }}
                            style={{ fontSize: "0.65rem", background: "none", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "4px", color: "rgba(255,255,255,0.35)", cursor: "pointer", padding: "0.1rem 0.35rem" }}
                          >
                            Clear
                          </button>
                        )}
                      </div>
                      {/* Log search input */}
                      <div style={{ position: "relative", marginBottom: "0.35rem" }}>
                        <input
                          value={logSearch}
                          onChange={e => setLogSearch(e.target.value)}
                          placeholder="Search logs..."
                          style={{
                            width: "100%", boxSizing: "border-box",
                            padding: "0.2rem 1.4rem 0.2rem 1.5rem",
                            fontSize: "0.68rem", borderRadius: "4px",
                            border: "1px solid rgba(63,63,70,0.5)",
                            background: "rgba(0,0,0,0.25)", color: "#fff",
                          }}
                        />
                        <span style={{ position: "absolute", left: "0.4rem", top: "50%", transform: "translateY(-50%)", fontSize: "0.65rem", color: "rgba(255,255,255,0.3)", pointerEvents: "none" }}>⌕</span>
                        {logSearch && (
                          <span
                            onClick={() => setLogSearch('')}
                            style={{ position: "absolute", right: "0.4rem", top: "50%", transform: "translateY(-50%)", fontSize: "0.65rem", color: "rgba(255,255,255,0.4)", cursor: "pointer", lineHeight: 1 }}
                          >✕</span>
                        )}
                      </div>
                      {/* Filter pills */}
                      <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
                        {([
                          { key: 'all', label: 'All', count: logs.length },
                          { key: 'connect', label: 'Connect', count: logs.filter(l => l.type === 'connect').length },
                          { key: 'tool_call', label: 'Tool', count: logs.filter(l => l.type === 'tool_call' || l.type === 'tool_result').length },
                          { key: 'tool_error', label: 'Error', count: logs.filter(l => l.type === 'tool_error').length },
                          { key: 'chat', label: 'Chat', count: logs.filter(l => l.type === 'chat').length },
                        ] as const).map(pill => (
                          <button
                            key={pill.key}
                            onClick={() => setLogFilter(pill.key)}
                            style={{
                              fontSize: "0.65rem", padding: "0.1rem 0.45rem",
                              borderRadius: "999px", cursor: "pointer",
                              border: logFilter === pill.key ? "1px solid rgba(99,102,241,0.7)" : "1px solid rgba(63,63,70,0.5)",
                              background: logFilter === pill.key ? "rgba(99,102,241,0.2)" : "transparent",
                              color: logFilter === pill.key ? "rgba(165,180,252,1)" : "rgba(255,255,255,0.4)",
                              fontFamily: "monospace",
                              transition: "all 0.1s",
                            }}
                          >
                            {pill.label}{pill.count > 0 ? ` (${pill.count})` : ''}
                          </button>
                        ))}
                      </div>
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
                      {filteredLogs.length === 0 ? (
                        <div style={{
                          display: "flex", alignItems: "center", justifyContent: "center",
                          height: "100%", color: "rgba(255,255,255,0.35)", fontSize: "0.8rem",
                        }}>
                          {selectedServer?.session_id ? (logFilter !== 'all' || logSearch ? "No matching logs" : "No logs yet") : "Connect to a server to see logs"}
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          {[...filteredLogs].reverse().map((log, i) => {
                            const color = logColors[log.type] || "#9ca3af";
                            return (
                              <div
                                key={i}
                                style={{
                                  display: "grid",
                                  gridTemplateColumns: "70px 90px 1fr",
                                  gap: "0.5rem",
                                  paddingBottom: "3px",
                                  borderBottom: "1px solid rgba(63,63,70,0.2)",
                                  borderLeft: `2px solid ${color}`,
                                  paddingLeft: "0.4rem",
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
                                {/* Message */}
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
                  flex: 1,
                  minHeight: 0,
                  boxSizing: "border-box",
                  display: "flex",
                  flexDirection: "column",
                  overflow: "hidden",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
                  <h2 style={{ fontSize: "1.1rem", fontWeight: "600" }}>Tool Execution</h2>
                  {selectedServer?.status === "connected" && selectedServer.session_id && (
                    <button
                      onClick={async () => {
                        try {
                          const data = await apiClient.exportInspectorServer(selectedServer.session_id!);
                          // Merge in the display name from local state since backend doesn't store it
                          data.serverInfo = { ...data.serverInfo, name: selectedServer.name || selectedServer.server_info?.name };
                          const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
                          const a = document.createElement("a");
                          a.href = URL.createObjectURL(blob);
                          a.download = `${(selectedServer.name || selectedServer.server_info?.name || "mcp-server").replace(/\s+/g, "-").toLowerCase()}-export.json`;
                          a.click();
                          URL.revokeObjectURL(a.href);
                        } catch (e) {
                          console.error("Export failed", e);
                        }
                      }}
                      title="Export server config + tools as JSON"
                      style={{
                        fontSize: "0.72rem", padding: "0.25rem 0.65rem", borderRadius: "6px",
                        background: "rgba(39,39,42,0.8)", border: "1px solid rgba(63,63,70,0.6)",
                        color: "rgba(255,255,255,0.6)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.3rem",
                      }}
                    >
                      ↓ Export
                    </button>
                  )}
                </div>

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
                  <button
                    onClick={() => {
                      setMode("resources");
                      setSelectedResourceUri(null);
                      setResourceContent(null);
                    }}
                    style={{
                      padding: "0.35rem 0.75rem", borderRadius: "0.35rem",
                      border: "1px solid rgba(63,63,70,0.6)",
                      background: mode === "resources" ? "#fff" : "transparent",
                      color: mode === "resources" ? "#000" : "#fff",
                      cursor: "pointer",
                    }}
                  >
                    Resources
                  </button>
                  <button
                    onClick={() => {
                      setMode("prompts");
                      setSelectedPrompt(null);
                      setPromptArgs({});
                      setPromptResult(null);
                    }}
                    style={{
                      padding: "0.35rem 0.75rem", borderRadius: "0.35rem",
                      border: "1px solid rgba(63,63,70,0.6)",
                      background: mode === "prompts" ? "#fff" : "transparent",
                      color: mode === "prompts" ? "#000" : "#fff",
                      cursor: "pointer",
                    }}
                  >
                    Prompts
                  </button>
                </div>

                {/* ── MANUAL MODE ─── */}
                <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 0 }}>
                  {mode === "manual" && selectedServer && selectedTool && (
                    <div style={{ overflowY: "auto", flex: 1, minHeight: 0, paddingBottom: "0.5rem", marginTop: "1rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap", marginBottom: "1rem" }}>
                        <h3 style={{ margin: 0 }}>{selectedTool.name}</h3>
                        {(() => {
                          const ann = selectedTool.annotations ?? {};
                          const ANNOTATION_META: { key: string; label: string; bg: string; color: string; tip: string }[] = [
                            { key: "readOnlyHint",    label: "Read-only",   bg: "rgba(63,63,70,0.6)",    color: "rgba(220,220,220,0.85)", tip: "Tool does not modify state" },
                            { key: "destructiveHint", label: "Destructive", bg: "rgba(239,68,68,0.18)",  color: "rgba(252,165,165,0.95)", tip: "Tool may delete or overwrite data" },
                            { key: "idempotentHint",  label: "Idempotent",  bg: "rgba(34,197,94,0.15)",  color: "rgba(134,239,172,0.9)",  tip: "Same call with same args always gives same result" },
                            { key: "openWorldHint",   label: "External",    bg: "rgba(59,130,246,0.18)", color: "rgba(147,197,253,0.95)", tip: "Tool interacts with the external world (web, APIs, filesystem)" },
                          ];
                          return ANNOTATION_META.filter(a => ann[a.key]).map(a => (
                            <span key={a.label} title={a.tip} style={{
                              fontSize: "0.65rem", padding: "0.15rem 0.55rem", borderRadius: "999px",
                              background: a.bg, color: a.color, fontWeight: 600, cursor: "help",
                              border: `1px solid ${a.color}33`,
                            }}>{a.label}</span>
                          ));
                        })()}
                      </div>

                      {selectedServer.status === "connected" ? (
                        <>
                          <JsonSchemaForm
                            schema={selectedTool.inputSchema}
                            initialValues={formPrefill}
                            onSubmit={runTool}
                            submitLabel="Run Tool"
                            loading={executing}
                          />

                          {lastRunParams && (
                            <div style={{ marginTop: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                              <button
                                onClick={() => {
                                  const jsonrpc = {
                                    jsonrpc: "2.0", id: 1,
                                    method: "tools/call",
                                    params: { name: selectedTool.name, arguments: lastRunParams },
                                  };
                                  navigator.clipboard.writeText(JSON.stringify(jsonrpc, null, 2));
                                  setCopyRequestToast(true);
                                  setTimeout(() => setCopyRequestToast(false), 2000);
                                }}
                                style={{
                                  fontSize: "0.72rem", padding: "0.25rem 0.65rem", borderRadius: "6px",
                                  background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.35)",
                                  color: "rgba(165,180,252,0.9)", cursor: "pointer",
                                }}
                              >
                                {copyRequestToast ? "✓ Copied!" : "Copy as JSON-RPC"}
                              </button>
                              {/* 5C: Save this request */}
                              <button
                                onClick={() => {
                                  setSaveTitle(selectedTool.name);
                                  setSaveDialogOpen(true);
                                }}
                                style={{
                                  fontSize: "0.72rem", padding: "0.25rem 0.65rem", borderRadius: "6px",
                                  background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.3)",
                                  color: "rgba(134,239,172,0.9)", cursor: "pointer",
                                }}
                              >
                                Save Request
                              </button>
                            </div>
                          )}

                          {/* 5C: Save dialog */}
                          {saveDialogOpen && (
                            <div style={{
                              position: "fixed", inset: 0, zIndex: 9999,
                              background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center",
                            }} onClick={() => setSaveDialogOpen(false)}>
                              <div
                                onClick={e => e.stopPropagation()}
                                style={{
                                  background: "#18181b", border: "1px solid rgba(63,63,70,0.7)",
                                  borderRadius: "10px", padding: "1.25rem", width: "320px",
                                }}
                              >
                                <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "#fff", marginBottom: "0.75rem" }}>Save Request</div>
                                <input
                                  autoFocus
                                  value={saveTitle}
                                  onChange={e => setSaveTitle(e.target.value)}
                                  onKeyDown={e => {
                                    if (e.key === "Enter" && saveTitle.trim() && lastRunParams && selectedServer) {
                                      saveRequest(selectedServer.url, {
                                        id: crypto.randomUUID(),
                                        title: saveTitle.trim(),
                                        toolName: selectedTool.name,
                                        params: lastRunParams,
                                        createdAt: Date.now(),
                                        serverUrl: selectedServer.url,
                                      });
                                      setSavedRequests(loadSavedRequests(selectedServer.url));
                                      setSaveDialogOpen(false);
                                    }
                                    if (e.key === "Escape") setSaveDialogOpen(false);
                                  }}
                                  placeholder="Request title..."
                                  style={{
                                    width: "100%", boxSizing: "border-box",
                                    padding: "0.45rem 0.6rem", fontSize: "0.82rem",
                                    borderRadius: "6px", border: "1px solid rgba(63,63,70,0.6)",
                                    background: "rgba(0,0,0,0.3)", color: "#fff", outline: "none",
                                    marginBottom: "0.75rem",
                                  }}
                                />
                                <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                                  <button
                                    onClick={() => setSaveDialogOpen(false)}
                                    style={{
                                      fontSize: "0.78rem", padding: "0.3rem 0.75rem", borderRadius: "6px",
                                      border: "1px solid rgba(63,63,70,0.6)", background: "transparent",
                                      color: "rgba(255,255,255,0.5)", cursor: "pointer",
                                    }}
                                  >Cancel</button>
                                  <button
                                    onClick={() => {
                                      if (!saveTitle.trim() || !lastRunParams || !selectedServer) return;
                                      saveRequest(selectedServer.url, {
                                        id: crypto.randomUUID(),
                                        title: saveTitle.trim(),
                                        toolName: selectedTool.name,
                                        params: lastRunParams,
                                        createdAt: Date.now(),
                                        serverUrl: selectedServer.url,
                                      });
                                      setSavedRequests(loadSavedRequests(selectedServer.url));
                                      setSaveDialogOpen(false);
                                    }}
                                    disabled={!saveTitle.trim()}
                                    style={{
                                      fontSize: "0.78rem", padding: "0.3rem 0.75rem", borderRadius: "6px",
                                      border: "1px solid rgba(34,197,94,0.4)", background: "rgba(34,197,94,0.1)",
                                      color: "rgba(134,239,172,0.9)", cursor: saveTitle.trim() ? "pointer" : "not-allowed",
                                      opacity: saveTitle.trim() ? 1 : 0.5,
                                    }}
                                  >Save</button>
                                </div>
                              </div>
                            </div>
                          )}

                          {(toolResult || toolError) && (
                            <div style={{ marginTop: "1.25rem" }}>
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
                    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
                      {selectedServer.status === "connected" ? (
                        <>
                          {/* Chat History — fills remaining flex space, scrolls */}
                          <div
                            ref={chatRef}
                            style={{
                              flex: 1,
                              minHeight: 0,
                              overflowY: "auto",
                              padding: "0.5rem 0.5rem 2rem 0.25rem"
                            }}
                          >
                            {/* Inner wrapper: flex layout for gap spacing.
                                Kept separate from the scroll container so flex items
                                don't shrink-to-fit and prevent overflow scrolling. */}
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                            {groupMessages(chatHistory, executionHistory).map((group, _idx, _arr) => {
                              const isLast = _idx === _arr.length - 1;
                              if (group.kind === "run") {
                                const toolResult = group.steps.find(s => s.type === "tool_result");
                                const toolCall = group.steps.find(s => s.type === "tool_call");
                                const sessionId = selectedServer?.session_id ?? undefined;
                                const hasWidget = !!(toolResult?.resourceUri && sessionId && toolCall);
                                return (
                                  <React.Fragment key={group.runId}>
                                    <ExecutionRunBlock steps={group.steps} run={group.run} />
                                    {hasWidget && (
                                      <div style={{
                                        width: "100%",
                                        border: "1px solid rgba(99,102,241,0.3)",
                                        borderRadius: "10px",
                                        overflow: "hidden",
                                        background: "rgba(99,102,241,0.04)",
                                      }}>
                                        <WidgetSandbox
                                          sessionId={sessionId!}
                                          resourceUri={toolResult!.resourceUri!}
                                          toolInput={toolCall!.params || {}}
                                          toolResult={toolResult!.result}
                                        />
                                      </div>
                                    )}
                                    {/* Scroll anchor: AFTER widget so auto-scroll reveals the full widget */}
                                    {isLast && <div ref={chatBottomRef} />}
                                  </React.Fragment>
                                );
                              }

                              const msg = group.msg;

                              if (msg.type === "user") {
                                return (
                                  <React.Fragment key={msg.id}>
                                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                                      <div style={{
                                        background: "rgba(37,99,235,0.85)",
                                        border: "1px solid rgba(59,130,246,0.4)",
                                        color: "#fff",
                                        padding: "0.55rem 0.85rem",
                                        borderRadius: "16px 16px 4px 16px",
                                        maxWidth: "75%", fontSize: "0.875rem", lineHeight: 1.5,
                                      }}>
                                        {msg.content}
                                      </div>
                                    </div>
                                    {isLast && <div ref={chatBottomRef} />}
                                  </React.Fragment>
                                );
                              }

                              if (msg.type === "assistant") {
                                return (
                                  <React.Fragment key={msg.id}>
                                    <div style={{ display: "flex", justifyContent: "flex-start", gap: "0.5rem", alignItems: "flex-start" }}>
                                      <div style={{
                                        width: "22px", height: "22px", borderRadius: "50%", flexShrink: 0, marginTop: "2px",
                                        background: "rgba(99,102,241,0.2)", border: "1px solid rgba(99,102,241,0.4)",
                                        display: "flex", alignItems: "center", justifyContent: "center",
                                        fontSize: "0.65rem",
                                      }}>🤖</div>
                                      <div style={{
                                        background: "rgba(39,39,42,0.8)",
                                        border: "1px solid rgba(63,63,70,0.6)",
                                        padding: "0.55rem 0.85rem",
                                        borderRadius: "4px 16px 16px 16px",
                                        maxWidth: "75%", fontSize: "0.875rem", lineHeight: 1.5,
                                        color: "rgba(255,255,255,0.85)",
                                      }}>
                                        {msg.content}
                                      </div>
                                    </div>
                                    {isLast && <div ref={chatBottomRef} />}
                                  </React.Fragment>
                                );
                              }

                              return null;
                            })}
                            </div>{/* close inner flex wrapper */}
                          </div>

                          {/* Starter prompt chips — shown when no user message sent yet */}
                          {!chatHistory.some(m => m.type === "user") && (selectedServer?.tools?.length ?? 0) > 0 && (
                            <div style={{ flexShrink: 0, padding: "0.5rem 0.25rem", display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                              {[
                                ...selectedServer!.tools.slice(0, 3).map((t: any) => `Try ${t.name} with example data`),
                                selectedServer!.tools.length > 1 ? `Run ${selectedServer!.tools[0].name}` : null,
                              ].filter(Boolean).slice(0, 4).map((prompt: any) => (
                                <button
                                  key={prompt}
                                  onClick={() => runChatToolWithMessage(prompt)}
                                  style={{
                                    fontSize: "0.72rem", padding: "0.3rem 0.7rem", borderRadius: "999px",
                                    background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.25)",
                                    color: "rgba(165,180,252,0.85)", cursor: "pointer",
                                    transition: "background 0.15s",
                                  }}
                                  onMouseEnter={e => (e.currentTarget.style.background = "rgba(99,102,241,0.18)")}
                                  onMouseLeave={e => (e.currentTarget.style.background = "rgba(99,102,241,0.08)")}
                                >
                                  {prompt}
                                </button>
                              ))}
                            </div>
                          )}

                          {/* Chat Input — always at bottom, shrinks to its content */}
                          <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "0.35rem", paddingTop: "0.5rem", borderTop: "1px solid rgba(63,63,70,0.3)" }}>

                            {/* ── Toolbar row: model badge · system prompt · clear ── */}
                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", paddingTop: "0.3rem" }}>
                              {/* Model badge */}
                              <span style={{
                                fontSize: "0.65rem", padding: "0.15rem 0.5rem", borderRadius: "999px",
                                background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.3)",
                                color: "rgba(165,180,252,0.9)", fontFamily: "monospace", flexShrink: 0,
                              }}>
                                Groq · llama-3.1-8b
                              </span>

                              {/* System prompt button */}
                              <button
                                onClick={() => { setSystemPromptDraft(systemPrompt); setSystemPromptOpen(true); }}
                                title="System prompt"
                                style={{
                                  fontSize: "0.65rem", padding: "0.15rem 0.5rem", borderRadius: "999px",
                                  background: systemPrompt ? "rgba(99,102,241,0.15)" : "transparent",
                                  border: systemPrompt ? "1px solid rgba(99,102,241,0.4)" : "1px solid rgba(63,63,70,0.5)",
                                  color: systemPrompt ? "rgba(165,180,252,0.9)" : "rgba(255,255,255,0.35)",
                                  cursor: "pointer", flexShrink: 0,
                                }}
                              >
                                ⚙ {systemPrompt ? "Prompt set" : "System prompt"}
                              </button>

                              {/* Spacer */}
                              <div style={{ flex: 1 }} />

                              {/* Clear chat */}
                              {chatHistory.length > 1 && selectedServerId && (
                                <button
                                  onClick={() => setChatHistoryByServer(prev => ({ ...prev, [selectedServerId]: [] }))}
                                  style={{ fontSize: "0.65rem", background: "none", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "4px", color: "rgba(255,255,255,0.35)", cursor: "pointer", padding: "0.1rem 0.4rem", flexShrink: 0 }}
                                >
                                  Clear Chat
                                </button>
                              )}
                            </div>

                            {/* ── System prompt dialog overlay ── */}
                            {systemPromptOpen && (
                              <div style={{
                                position: "fixed", inset: 0, zIndex: 50,
                                background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center",
                              }}
                                onClick={(e) => { if (e.target === e.currentTarget) setSystemPromptOpen(false); }}
                              >
                                <div style={{
                                  background: "#18181b", border: "1px solid rgba(63,63,70,0.7)",
                                  borderRadius: "12px", padding: "1.25rem", width: "420px", maxWidth: "90vw",
                                  display: "flex", flexDirection: "column", gap: "0.75rem",
                                }}>
                                  <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "rgba(255,255,255,0.85)" }}>System Prompt</div>
                                  <textarea
                                    value={systemPromptDraft}
                                    onChange={e => setSystemPromptDraft(e.target.value)}
                                    placeholder="You are a helpful assistant with access to MCP tools."
                                    rows={5}
                                    style={{
                                      background: "#09090b", border: "1px solid rgba(63,63,70,0.6)",
                                      borderRadius: "6px", padding: "0.5rem 0.6rem",
                                      color: "#fff", fontSize: "0.8rem", resize: "vertical",
                                      fontFamily: "inherit", lineHeight: 1.5,
                                    }}
                                  />
                                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                                    <button
                                      onClick={() => setSystemPromptOpen(false)}
                                      style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem", borderRadius: "6px", background: "transparent", border: "1px solid rgba(63,63,70,0.5)", color: "rgba(255,255,255,0.5)", cursor: "pointer" }}
                                    >
                                      Cancel
                                    </button>
                                    <button
                                      onClick={() => { setSystemPrompt(systemPromptDraft); setSystemPromptOpen(false); }}
                                      style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem", borderRadius: "6px", background: "rgba(99,102,241,0.8)", border: "none", color: "#fff", cursor: "pointer", fontWeight: 600 }}
                                    >
                                      Save
                                    </button>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* ── Message input row ── */}
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
                                flex: 1, minWidth: 0, padding: "0.5rem 0.75rem",
                                borderRadius: "0.5rem", border: "1px solid rgba(63,63,70,0.6)",
                                background: "rgba(24,24,27,0.8)", color: "#fff", opacity: chatLoading ? 0.6 : 1,
                                fontSize: "0.875rem",
                              }}
                            />
                            <button
                              onClick={()=>{ if (chatInput.trim()) runChatTool(); }}
                              disabled={chatLoading || !chatInput.trim()}
                              style={{
                                padding: "0.5rem 1rem", borderRadius: "0.5rem",
                                background: "rgba(99,102,241,0.9)", color: "#fff", fontWeight: "600", flexShrink: 0,
                                border: "none",
                                opacity: chatLoading || !chatInput.trim() ? 0.45 : 1,
                                cursor: chatLoading || !chatInput.trim() ? "not-allowed" : "pointer",
                                fontSize: "0.875rem",
                              }}
                            >
                              {chatLoading ? <ThinkingDots /> : "Send"}
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

                  {/* ── RESOURCES MODE ─── */}
                  {mode === "resources" && selectedServer?.status === "connected" && (
                    <div style={{ display: "flex", flex: 1, minHeight: 0, gap: "0.75rem", overflow: "hidden" }}>

                      {/* Resource list — left column */}
                      <div style={{
                        width: "38%", flexShrink: 0, display: "flex", flexDirection: "column",
                        border: "1px solid rgba(63,63,70,0.5)", borderRadius: "0.5rem", overflow: "hidden",
                      }}>
                        <div style={{
                          padding: "0.5rem 0.75rem", borderBottom: "1px solid rgba(63,63,70,0.4)",
                          display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0,
                          background: "rgba(24,24,27,0.6)",
                        }}>
                          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "rgba(255,255,255,0.7)" }}>
                            Resources {resources.length > 0 && <span style={{ color: "rgba(255,255,255,0.35)", fontWeight: 400 }}>({resources.length})</span>}
                          </span>
                          <button
                            onClick={() => {
                              if (!selectedServer?.session_id || !selectedServerId) return;
                              setResourcesByServer(prev => { const next = { ...prev }; delete next[selectedServerId]; return next; });
                              setSelectedResourceUri(null);
                              setResourceContent(null);
                            }}
                            style={{ fontSize: "0.65rem", background: "none", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "4px", color: "rgba(255,255,255,0.35)", cursor: "pointer", padding: "0.1rem 0.35rem" }}
                          >
                            Refresh
                          </button>
                        </div>
                        <div style={{ flex: 1, overflowY: "auto" }}>
                          {resourcesLoading ? (
                            <div style={{ padding: "1rem", textAlign: "center", color: "rgba(255,255,255,0.35)", fontSize: "0.75rem" }}>
                              Loading resources...
                            </div>
                          ) : resources.length === 0 ? (
                            <div style={{ padding: "1rem", textAlign: "center", color: "rgba(255,255,255,0.35)", fontSize: "0.75rem" }}>
                              No resources found
                            </div>
                          ) : (
                            resources.map(r => {
                              const isSelected = r.uri === selectedResourceUri;
                              // Extract {param} names from template URIs
                              const templateVars = r.isTemplate
                                ? (r.uri.match(/\{([^}]+)\}/g) ?? []).map(v => v.slice(1, -1))
                                : [];
                              const loadResource = async (uri: string) => {
                                setSelectedResourceUri(r.uri);
                                setResourceContent(null);
                                setResourceContentLoading(true);
                                try {
                                  const res = await apiClient.readInspectorResource(selectedServer.session_id!, uri);
                                  const first = res?.contents?.[0];
                                  setResourceContent({
                                    text: first?.text ?? first?.content ?? res?.text ?? "",
                                    blob: first?.blob,
                                    mimeType: first?.mimeType ?? r.mimeType ?? "text/plain",
                                  });
                                } catch {
                                  setResourceContent({ text: "Failed to load resource.", mimeType: "text/plain" });
                                } finally {
                                  setResourceContentLoading(false);
                                }
                              };
                              return (
                                <div
                                  key={r.uri}
                                  onClick={() => {
                                    if (r.isTemplate) {
                                      // Just select — param form shows in right panel
                                      setSelectedResourceUri(r.uri);
                                      setResourceContent(null);
                                      setTemplateParams({});
                                    } else {
                                      if (isSelected) return;
                                      loadResource(r.uri);
                                    }
                                  }}
                                  style={{
                                    padding: "0.55rem 0.75rem",
                                    borderBottom: "1px solid rgba(63,63,70,0.25)",
                                    cursor: "pointer",
                                    background: isSelected ? "rgba(99,102,241,0.12)" : "transparent",
                                    borderLeft: isSelected ? "2px solid rgba(99,102,241,0.8)" : "2px solid transparent",
                                    transition: "background 0.1s",
                                  }}
                                >
                                  <div style={{ fontSize: "0.75rem", fontWeight: 600, color: isSelected ? "rgba(165,180,252,1)" : "rgba(255,255,255,0.85)", wordBreak: "break-all" }}>
                                    {r.name || r.uri}
                                  </div>
                                  {r.name && (
                                    <div style={{ fontSize: "0.65rem", color: "rgba(255,255,255,0.3)", marginTop: "0.1rem", wordBreak: "break-all" }}>
                                      {r.uri}
                                    </div>
                                  )}
                                  <div style={{ display: "flex", gap: "0.35rem", marginTop: "0.25rem", flexWrap: "wrap" }}>
                                    {r.mimeType && (
                                      <span style={{
                                        fontSize: "0.6rem", padding: "0.05rem 0.35rem", borderRadius: "999px",
                                        background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)",
                                        color: "rgba(165,180,252,0.8)", fontFamily: "monospace",
                                      }}>
                                        {r.mimeType}
                                      </span>
                                    )}
                                    {r.isTemplate && (
                                      <span style={{
                                        fontSize: "0.6rem", padding: "0.05rem 0.35rem", borderRadius: "999px",
                                        background: "rgba(245,158,11,0.15)", border: "1px solid rgba(245,158,11,0.3)",
                                        color: "rgba(252,211,77,0.9)", fontFamily: "monospace",
                                      }}>
                                        template
                                      </span>
                                    )}
                                  </div>
                                  {r.description && (
                                    <div style={{ fontSize: "0.65rem", color: "rgba(255,255,255,0.4)", marginTop: "0.2rem" }}>
                                      {r.description}
                                    </div>
                                  )}
                                  {/* Inline param form for selected templates */}
                                  {r.isTemplate && isSelected && templateVars.length > 0 && (
                                    <div
                                      onClick={e => e.stopPropagation()}
                                      style={{ marginTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}
                                    >
                                      {templateVars.map(v => (
                                        <div key={v} style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                          <span style={{ fontSize: "0.65rem", color: "rgba(252,211,77,0.8)", fontFamily: "monospace", flexShrink: 0 }}>{v}</span>
                                          <input
                                            value={templateParams[v] ?? ""}
                                            onChange={e => setTemplateParams(prev => ({ ...prev, [v]: e.target.value }))}
                                            placeholder={v}
                                            style={{
                                              flex: 1, padding: "0.2rem 0.4rem", fontSize: "0.7rem",
                                              background: "rgba(0,0,0,0.3)", border: "1px solid rgba(63,63,70,0.6)",
                                              borderRadius: "4px", color: "#fff",
                                            }}
                                          />
                                        </div>
                                      ))}
                                      <button
                                        onClick={() => {
                                          let uri = r.uri;
                                          templateVars.forEach(v => { uri = uri.replace(`{${v}}`, encodeURIComponent(templateParams[v] ?? "")); });
                                          loadResource(uri);
                                        }}
                                        style={{
                                          marginTop: "0.15rem", padding: "0.25rem 0.5rem", fontSize: "0.7rem",
                                          background: "rgba(99,102,241,0.8)", border: "none", borderRadius: "4px",
                                          color: "#fff", cursor: "pointer", alignSelf: "flex-end",
                                        }}
                                      >
                                        Load
                                      </button>
                                    </div>
                                  )}
                                </div>
                              );
                            })
                          )}
                        </div>
                      </div>

                      {/* Resource content viewer — right column */}
                      <div style={{
                        flex: 1, minWidth: 0, display: "flex", flexDirection: "column",
                        border: "1px solid rgba(63,63,70,0.5)", borderRadius: "0.5rem", overflow: "hidden",
                      }}>
                        {!selectedResourceUri ? (
                          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,0.3)", fontSize: "0.8rem" }}>
                            Select a resource to view its content
                          </div>
                        ) : resourceContentLoading ? (
                          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,0.35)", fontSize: "0.75rem" }}>
                            Loading...
                          </div>
                        ) : resourceContent ? (() => {
                          const mime = resourceContent.mimeType ?? "text/plain";
                          const text = resourceContent.text ?? "";
                          const isImage = mime.startsWith("image/");
                          const isJson = mime.includes("json") || (() => { try { JSON.parse(text); return text.trim().startsWith("{") || text.trim().startsWith("["); } catch { return false; } })();
                          return (
                            <>
                              <div style={{
                                padding: "0.4rem 0.75rem", borderBottom: "1px solid rgba(63,63,70,0.4)",
                                display: "flex", alignItems: "center", gap: "0.5rem", flexShrink: 0,
                                background: "rgba(24,24,27,0.6)",
                              }}>
                                <span style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.5)", wordBreak: "break-all", flex: 1 }}>{selectedResourceUri}</span>
                                <span style={{
                                  fontSize: "0.6rem", padding: "0.05rem 0.35rem", borderRadius: "999px", flexShrink: 0,
                                  background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)",
                                  color: "rgba(165,180,252,0.8)", fontFamily: "monospace",
                                }}>{mime}</span>
                              </div>
                              <div style={{ flex: 1, overflow: "auto", padding: "0.75rem" }}>
                                {isImage ? (
                                  <img
                                    src={resourceContent.blob ? `data:${mime};base64,${resourceContent.blob}` : text}
                                    alt={selectedResourceUri}
                                    style={{ maxWidth: "100%", borderRadius: "4px" }}
                                  />
                                ) : (
                                  <pre style={{
                                    margin: 0, fontSize: "0.75rem", lineHeight: 1.6,
                                    color: isJson ? "#a5f3fc" : "rgba(255,255,255,0.8)",
                                    fontFamily: "ui-monospace, monospace",
                                    whiteSpace: "pre-wrap", wordBreak: "break-word",
                                  }}>
                                    {isJson ? (() => { try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text; } })() : text}
                                  </pre>
                                )}
                              </div>
                            </>
                          );
                        })() : null}
                      </div>
                    </div>
                  )}

                  {/* Empty states */}
                  {mode === "manual" && (!selectedServer || !selectedTool) && (
                    <div style={{
                      marginTop: "1rem", padding: "1rem", border: "1px dashed rgba(63,63,70,0.6)",
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
                  {mode === "resources" && (!selectedServer || selectedServer.status !== "connected") && (
                    <div style={{
                      padding: "1rem", border: "1px dashed rgba(63,63,70,0.6)",
                      borderRadius: "0.5rem", textAlign: "center", color: "rgba(255,255,255,0.6)",
                    }}>
                      {!selectedServer ? "Select a connected server to browse resources" : "Server is not connected."}
                    </div>
                  )}

                  {/* ── PROMPTS MODE ─── */}
                  {mode === "prompts" && selectedServer?.status === "connected" && (
                    <div style={{ display: "flex", flex: 1, minHeight: 0, gap: "0.75rem", overflow: "hidden" }}>

                      {/* Prompt list — left column */}
                      <div style={{
                        width: "38%", flexShrink: 0, display: "flex", flexDirection: "column",
                        border: "1px solid rgba(63,63,70,0.5)", borderRadius: "0.5rem", overflow: "hidden",
                      }}>
                        <div style={{
                          padding: "0.5rem 0.75rem", borderBottom: "1px solid rgba(63,63,70,0.4)",
                          display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0,
                          background: "rgba(24,24,27,0.6)",
                        }}>
                          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "rgba(255,255,255,0.7)" }}>
                            Prompts {prompts.length > 0 && <span style={{ color: "rgba(255,255,255,0.35)", fontWeight: 400 }}>({prompts.length})</span>}
                          </span>
                          <button
                            onClick={() => {
                              if (!selectedServerId) return;
                              setPromptsByServer(prev => { const n = { ...prev }; delete n[selectedServerId]; return n; });
                              setSelectedPrompt(null); setPromptArgs({}); setPromptResult(null);
                            }}
                            style={{ fontSize: "0.65rem", background: "none", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "4px", color: "rgba(255,255,255,0.35)", cursor: "pointer", padding: "0.1rem 0.35rem" }}
                          >
                            Refresh
                          </button>
                        </div>
                        <div style={{ flex: 1, overflowY: "auto" }}>
                          {promptsLoading ? (
                            <div style={{ padding: "1rem", textAlign: "center", color: "rgba(255,255,255,0.35)", fontSize: "0.75rem" }}>Loading prompts...</div>
                          ) : prompts.length === 0 ? (
                            <div style={{ padding: "1rem", textAlign: "center", color: "rgba(255,255,255,0.35)", fontSize: "0.75rem" }}>No prompts found</div>
                          ) : (
                            prompts.map((p: any) => {
                              const isSelected = selectedPrompt?.name === p.name;
                              const argCount = p.arguments?.length ?? 0;
                              return (
                                <div
                                  key={p.name}
                                  onClick={() => {
                                    setSelectedPrompt(p);
                                    setPromptArgs({});
                                    setPromptResult(null);
                                  }}
                                  style={{
                                    padding: "0.55rem 0.75rem",
                                    borderBottom: "1px solid rgba(63,63,70,0.25)",
                                    cursor: "pointer",
                                    background: isSelected ? "rgba(99,102,241,0.12)" : "transparent",
                                    borderLeft: isSelected ? "2px solid rgba(99,102,241,0.8)" : "2px solid transparent",
                                    transition: "background 0.1s",
                                  }}
                                >
                                  <div style={{ fontSize: "0.75rem", fontWeight: 600, color: isSelected ? "rgba(165,180,252,1)" : "rgba(255,255,255,0.85)" }}>
                                    {p.name}
                                  </div>
                                  {p.description && (
                                    <div style={{ fontSize: "0.65rem", color: "rgba(255,255,255,0.4)", marginTop: "0.15rem" }}>
                                      {p.description}
                                    </div>
                                  )}
                                  {argCount > 0 && (
                                    <div style={{ marginTop: "0.25rem", display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
                                      {p.arguments.map((a: any) => (
                                        <span key={a.name} style={{
                                          fontSize: "0.6rem", padding: "0.05rem 0.35rem", borderRadius: "999px",
                                          background: a.required ? "rgba(99,102,241,0.15)" : "rgba(63,63,70,0.4)",
                                          border: `1px solid ${a.required ? "rgba(99,102,241,0.3)" : "rgba(63,63,70,0.6)"}`,
                                          color: a.required ? "rgba(165,180,252,0.9)" : "rgba(255,255,255,0.4)",
                                          fontFamily: "monospace",
                                        }}>
                                          {a.name}{a.required ? "" : "?"}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              );
                            })
                          )}
                        </div>
                      </div>

                      {/* Prompt detail + result — right column */}
                      <div style={{
                        flex: 1, minWidth: 0, display: "flex", flexDirection: "column",
                        border: "1px solid rgba(63,63,70,0.5)", borderRadius: "0.5rem", overflow: "hidden",
                      }}>
                        {!selectedPrompt ? (
                          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,0.3)", fontSize: "0.8rem" }}>
                            Select a prompt to fill its arguments
                          </div>
                        ) : (
                          <>
                            {/* Header */}
                            <div style={{
                              padding: "0.5rem 0.75rem", borderBottom: "1px solid rgba(63,63,70,0.4)",
                              background: "rgba(24,24,27,0.6)", flexShrink: 0,
                            }}>
                              <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "rgba(255,255,255,0.85)" }}>{selectedPrompt.name}</div>
                              {selectedPrompt.description && (
                                <div style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.4)", marginTop: "0.15rem" }}>{selectedPrompt.description}</div>
                              )}
                            </div>

                            {/* Argument form */}
                            <div style={{ padding: "0.75rem", flexShrink: 0, borderBottom: "1px solid rgba(63,63,70,0.3)" }}>
                              {(selectedPrompt.arguments?.length ?? 0) === 0 ? (
                                <div style={{ fontSize: "0.72rem", color: "rgba(255,255,255,0.35)", fontStyle: "italic" }}>No arguments required</div>
                              ) : (
                                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                                  {selectedPrompt.arguments.map((a: any) => (
                                    <div key={a.name}>
                                      <div style={{ fontSize: "0.65rem", color: "rgba(255,255,255,0.5)", marginBottom: "0.2rem", fontFamily: "monospace" }}>
                                        {a.name}{a.required ? <span style={{ color: "rgba(239,68,68,0.8)" }}> *</span> : <span style={{ color: "rgba(255,255,255,0.25)" }}> (optional)</span>}
                                      </div>
                                      {a.description && (
                                        <div style={{ fontSize: "0.62rem", color: "rgba(255,255,255,0.3)", marginBottom: "0.2rem" }}>{a.description}</div>
                                      )}
                                      <input
                                        value={promptArgs[a.name] ?? ""}
                                        onChange={e => setPromptArgs(prev => ({ ...prev, [a.name]: e.target.value }))}
                                        placeholder={a.name}
                                        style={{
                                          width: "100%", boxSizing: "border-box",
                                          padding: "0.3rem 0.5rem", fontSize: "0.75rem",
                                          background: "rgba(0,0,0,0.3)", border: "1px solid rgba(63,63,70,0.6)",
                                          borderRadius: "4px", color: "#fff",
                                        }}
                                      />
                                    </div>
                                  ))}
                                </div>
                              )}
                              <button
                                disabled={promptResultLoading}
                                onClick={async () => {
                                  if (!selectedServer?.session_id) return;
                                  setPromptResultLoading(true);
                                  setPromptResult(null);
                                  try {
                                    const res = await apiClient.getInspectorPrompt(selectedServer.session_id, selectedPrompt.name, promptArgs);
                                    setPromptResult(res);
                                  } catch (e: any) {
                                    setPromptResult({ error: e.message });
                                  } finally {
                                    setPromptResultLoading(false);
                                  }
                                }}
                                style={{
                                  marginTop: "0.6rem", padding: "0.35rem 0.85rem",
                                  background: "rgba(99,102,241,0.85)", border: "none", borderRadius: "6px",
                                  color: "#fff", fontWeight: 600, fontSize: "0.75rem",
                                  cursor: promptResultLoading ? "not-allowed" : "pointer",
                                  opacity: promptResultLoading ? 0.6 : 1,
                                }}
                              >
                                {promptResultLoading ? "Loading..." : "Get Prompt"}
                              </button>
                            </div>

                            {/* Messages preview */}
                            <div style={{ flex: 1, overflowY: "auto", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                              {promptResult?.error ? (
                                <div style={{ fontSize: "0.75rem", color: "#fca5a5", padding: "0.5rem", background: "rgba(239,68,68,0.1)", borderRadius: "6px", border: "1px solid rgba(239,68,68,0.3)" }}>
                                  Error: {promptResult.error}
                                </div>
                              ) : promptResult?.messages ? (
                                promptResult.messages.map((msg: any, i: number) => {
                                  // Unwrap role from nested message objects if SDK wraps them
                                  const role = msg.role ?? msg?.content?.role ?? "user";
                                  const rawContent = msg.content ?? msg;
                                  const text = typeof rawContent === "string"
                                    ? rawContent
                                    : typeof rawContent?.text === "string"
                                      ? rawContent.text
                                      : Array.isArray(rawContent)
                                        ? rawContent.map((c: any) => c.text ?? JSON.stringify(c)).join("\n")
                                        : typeof rawContent === "object" && rawContent !== null && "text" in rawContent
                                          ? rawContent.text
                                          : JSON.stringify(rawContent, null, 2);
                                  return (
                                  <div key={i} style={{
                                    padding: "0.5rem 0.75rem",
                                    borderRadius: "8px",
                                    background: role === "user" ? "rgba(37,99,235,0.15)" : "rgba(39,39,42,0.8)",
                                    border: `1px solid ${role === "user" ? "rgba(59,130,246,0.3)" : "rgba(63,63,70,0.5)"}`,
                                  }}>
                                    <div style={{ fontSize: "0.62rem", fontWeight: 700, color: role === "user" ? "rgba(147,197,253,0.9)" : "rgba(165,180,252,0.9)", marginBottom: "0.3rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                                      {role}
                                    </div>
                                    <div style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.8)", whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
                                      {text}
                                    </div>
                                  </div>
                                  );
                                })
                              ) : !promptResultLoading && (
                                <div style={{ color: "rgba(255,255,255,0.25)", fontSize: "0.75rem", textAlign: "center", marginTop: "1rem" }}>
                                  Fill in arguments and click Get Prompt
                                </div>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  )}

                  {mode === "prompts" && (!selectedServer || selectedServer.status !== "connected") && (
                    <div style={{
                      padding: "1rem", border: "1px dashed rgba(63,63,70,0.6)",
                      borderRadius: "0.5rem", textAlign: "center", color: "rgba(255,255,255,0.6)",
                    }}>
                      {!selectedServer ? "Select a connected server to browse prompts" : "Server is not connected."}
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
          onClick={() => { setShowAddModal(false); setCustomName(""); setUrl(""); setCommand(""); setEnvVars([]); setTransport("http"); setAuthType("none"); setToken(""); setHeaderKey(""); setHeaderValue(""); }}
          onKeyDown={(e) => { if (e.key === "Escape") { setShowAddModal(false); setCustomName(""); setUrl(""); setCommand(""); setEnvVars([]); setTransport("http"); setAuthType("none"); setToken(""); setHeaderKey(""); setHeaderValue(""); } }}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
            display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#18181b", padding: "2rem", borderRadius: "0.75rem",
              width: "420px", border: "1px solid rgba(63,63,70,0.6)",
            }}
          >
            <h2 style={{ fontSize: "1.3rem", marginBottom: "1rem" }}>Connect MCP Server</h2>

            <form onSubmit={(e) => { e.preventDefault(); handleConnect(); }} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)", marginBottom: "0.3rem", display: "block" }}>
                  Server Name <span style={{ color: "rgba(255,255,255,0.3)" }}>(optional)</span>
                </label>
                <input
                  autoFocus
                  placeholder="e.g. My Weather Server"
                  style={{
                    width: "100%", padding: "0.6rem", borderRadius: "0.4rem",
                    border: "1px solid rgba(63,63,70,0.6)",
                    background: "#09090b", color: "#fff", boxSizing: "border-box",
                  }}
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                />
              </div>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.3rem" }}>
                  <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)" }}>Transport</label>
                  <span
                    title="HTTP: stateless request/response. SSE: persistent connection for servers that push notifications. stdio: spawn a local MCP server by command (e.g. npx -y @modelcontextprotocol/server-filesystem /tmp)."
                    style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.3)", cursor: "help", border: "1px solid rgba(255,255,255,0.2)", borderRadius: "50%", width: "14px", height: "14px", display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}
                  >?</span>
                </div>
                <select
                  value={transport}
                  onChange={(e) => { setTransport(e.target.value); setUrl(""); setCommand(""); }}
                  style={{
                    width: "100%", padding: "0.6rem", borderRadius: "0.4rem",
                    border: "1px solid rgba(63,63,70,0.6)",
                    background: "#09090b", color: "#fff",
                  }}
                >
                  <option value="http">HTTP</option>
                  <option value="sse">SSE</option>
                  <option value="stdio">STDIO (local subprocess)</option>
                </select>
              </div>

              {transport === "stdio" ? (
                <div>
                  <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)", marginBottom: "0.3rem", display: "block" }}>
                    Command
                  </label>
                  <input
                    placeholder="npx -y @modelcontextprotocol/server-filesystem /tmp"
                    style={{
                      width: "100%", padding: "0.6rem", borderRadius: "0.4rem",
                      border: "1px solid rgba(63,63,70,0.6)",
                      background: "#09090b", color: "#fff", boxSizing: "border-box",
                      fontFamily: "ui-monospace, monospace", fontSize: "0.8rem",
                    }}
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                  />
                  <p style={{ fontSize: "0.72rem", color: "rgba(255,255,255,0.3)", marginTop: "0.3rem", marginBottom: 0 }}>
                    The server will be spawned as a subprocess on the FluidMCP backend machine.
                  </p>

                  {/* Environment Variables */}
                  <div style={{ marginTop: "0.9rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                      <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)" }}>
                        Environment Variables <span style={{ color: "rgba(255,255,255,0.25)", fontWeight: 400 }}>(optional)</span>
                        <span
                          title="Env vars are passed to the subprocess at spawn time and cannot be changed while the server is running. Reconnect to update them."
                          style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.3)", cursor: "help", border: "1px solid rgba(255,255,255,0.2)", borderRadius: "50%", width: "14px", height: "14px", display: "inline-flex", alignItems: "center", justifyContent: "center", marginLeft: "0.3rem", flexShrink: 0 }}
                        >?</span>
                      </label>
                      <button
                        type="button"
                        onClick={() => setEnvVars(prev => [...prev, { key: "", value: "" }])}
                        style={{
                          fontSize: "0.72rem", padding: "0.2rem 0.55rem",
                          borderRadius: "0.3rem", border: "1px solid rgba(99,102,241,0.4)",
                          background: "rgba(99,102,241,0.1)", color: "rgba(200,200,255,0.8)",
                          cursor: "pointer",
                        }}
                      >+ Add</button>
                    </div>
                    {envVars.map((ev, i) => (
                      <div key={i} style={{ display: "flex", gap: "0.4rem", marginBottom: "0.35rem", alignItems: "center" }}>
                        <input
                          placeholder="KEY"
                          value={ev.key}
                          onChange={(e) => setEnvVars(prev => prev.map((x, j) => j === i ? { ...x, key: e.target.value } : x))}
                          style={{
                            flex: "0 0 38%", padding: "0.4rem 0.5rem", borderRadius: "0.3rem",
                            border: "1px solid rgba(63,63,70,0.6)", background: "#09090b",
                            color: "#fff", fontSize: "0.78rem", fontFamily: "ui-monospace, monospace",
                          }}
                        />
                        <input
                          placeholder="value"
                          value={ev.value}
                          onChange={(e) => setEnvVars(prev => prev.map((x, j) => j === i ? { ...x, value: e.target.value } : x))}
                          style={{
                            flex: 1, padding: "0.4rem 0.5rem", borderRadius: "0.3rem",
                            border: "1px solid rgba(63,63,70,0.6)", background: "#09090b",
                            color: "#fff", fontSize: "0.78rem",
                          }}
                        />
                        <button
                          type="button"
                          onClick={() => setEnvVars(prev => prev.filter((_, j) => j !== i))}
                          style={{
                            background: "transparent", border: "none", color: "rgba(255,100,100,0.6)",
                            cursor: "pointer", fontSize: "1rem", lineHeight: 1, padding: "0 0.2rem",
                          }}
                        >×</button>
                      </div>
                    ))}
                    {envVars.length === 0 && (
                      <p style={{ fontSize: "0.71rem", color: "rgba(255,255,255,0.2)", marginTop: "0.2rem", marginBottom: 0 }}>
                        e.g. API_KEY, OPENAI_API_KEY, …
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                <div>
                  <input
                    placeholder="Server URL"
                    style={{
                      width: "100%", padding: "0.6rem", borderRadius: "0.4rem",
                      border: "1px solid rgba(63,63,70,0.6)",
                      background: "#09090b", color: "#fff", boxSizing: "border-box",
                    }}
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                  />
                  {recentUrls.length > 0 && (
                    <div style={{ marginTop: "0.4rem", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                      <span style={{ fontSize: "0.72rem", color: "rgba(255,255,255,0.35)", alignSelf: "center" }}>Recent:</span>
                      {recentUrls.map(u => (
                        <button
                          key={u}
                          type="button"
                          onClick={() => setUrl(u)}
                          style={{
                            fontSize: "0.72rem", padding: "0.15rem 0.5rem",
                            borderRadius: "999px", border: "1px solid rgba(99,102,241,0.35)",
                            background: url === u ? "rgba(99,102,241,0.2)" : "rgba(99,102,241,0.07)",
                            color: "rgba(200,200,255,0.75)", cursor: "pointer",
                            maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                          }}
                          title={u}
                        >
                          {u.replace(/^https?:\/\//, "").slice(0, 35)}{u.replace(/^https?:\/\//, "").length > 35 ? "…" : ""}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Auth — not shown for stdio (local subprocess, no auth needed) */}
              {transport !== "stdio" && (
                <>
                  <div style={{ marginTop: "1rem" }}>
                    <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)" }}>
                      Auth Type
                    </label>
                    <select
                      value={authType}
                      onChange={(e) => setAuthType(e.target.value as any)}
                      style={{
                        width: "100%", marginTop: "0.3rem", padding: "0.5rem",
                        borderRadius: "0.4rem", background: "#18181b", color: "#fff",
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
                          width: "100%", marginTop: "0.3rem", padding: "0.5rem",
                          borderRadius: "0.4rem", background: "#18181b", color: "#fff",
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
                          width: "100%", marginTop: "0.3rem", padding: "0.5rem",
                          borderRadius: "0.4rem", background: "#18181b", color: "#fff",
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
                          width: "100%", marginTop: "0.3rem", padding: "0.5rem",
                          borderRadius: "0.4rem", background: "#18181b", color: "#fff",
                          border: "1px solid rgba(63,63,70,0.6)"
                        }}
                      />
                    </div>
                  )}
                </>
              )}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                <button
                  type="button"
                  onClick={() => { setShowAddModal(false); setCustomName(""); setUrl(""); setCommand(""); setEnvVars([]); setTransport("http"); setAuthType("none"); setToken(""); setHeaderKey(""); setHeaderValue(""); }}
                  style={{
                    background: "transparent", border: "1px solid rgba(63,63,70,0.6)",
                    padding: "0.5rem 1rem", borderRadius: "0.4rem", color: "#fff",
                  }}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={connecting}
                  style={{
                    background: "#fff", color: "#000",
                    padding: "0.5rem 1rem", borderRadius: "0.4rem", fontWeight: "600",
                  }}
                >
                  {connecting ? "Connecting..." : "Connect"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}