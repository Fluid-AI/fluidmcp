import { useState, useEffect, useRef } from "react";
import { Navbar } from "@/components/Navbar";
import { apiClient } from "@/services/api";
import type { OAuthToken } from "@/components/inspector/AddServerModal";
import { type SavedRequest, loadSavedRequests } from "@/lib/saved-requests";
import { ServerListPanel } from '../components/inspector/ServerListPanel';
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels';
import { LogsPanel } from '../components/inspector/LogsPanel';
import { AddServerModal } from '../components/inspector/AddServerModal';
import { ResourcesPanel } from '../components/inspector/ResourcesPanel';
import { PromptsPanel } from '../components/inspector/PromptsPanel';
import { ManualToolPanel } from '../components/inspector/ManualToolPanel';
import { ChatPanel } from '../components/inspector/ChatPanel';
import { type ChatMessage, type ExecutionRun } from '../components/inspector/chat-types';

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
    type: "none" | "bearer" | "header" | "oauth"
    token?: string
    headerKey?: string
    headerValue?: string
    access_token?: string
    refresh_token?: string
    expires_at?: number
    token_url?: string
    client_id?: string
  };
}

// Type for log entry
interface LogEntry {
  timestamp: string;
  type: 'connect' | 'disconnect' | 'tool_call' | 'tool_result' | 'tool_error' | 'chat';
  message: string;
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


export default function MCPInspector() {

  const [authType, setAuthType] = useState<"none" | "bearer" | "header" | "oauth">("none")

  const [token, setToken] = useState("")
  const [headerKey, setHeaderKey] = useState("")
  const [headerValue, setHeaderValue] = useState("")
  const [oauthToken, setOAuthToken] = useState<OAuthToken | null>(null)

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
  const chatAbortRef = useRef<AbortController | null>(null);

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
      if (authType === "oauth" && !oauthToken) {
        alert("Please complete the OAuth authorization flow first")
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

    const authConfig = authType === "oauth" && oauthToken ? {
      type: "oauth" as const,
      access_token: oauthToken.access_token,
      refresh_token: oauthToken.refresh_token,
      expires_at: oauthToken.expires_at,
      token_url: oauthToken.token_url,
      client_id: oauthToken.client_id,
    } : authType === "bearer" ? {
      type: "bearer" as const,
      token,
    } : authType === "header" ? {
      type: "header" as const,
      headerKey,
      headerValue,
    } : { type: "none" as const };

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

      // OAuth (not applicable for stdio)
      if (transport !== "stdio" && authType === "oauth" && oauthToken) {
        payload.auth = {
          type: "oauth",
          access_token: oauthToken.access_token,
          refresh_token: oauthToken.refresh_token,
          expires_at: oauthToken.expires_at,
          token_url: oauthToken.token_url,
          client_id: oauthToken.client_id,
        }
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
      setOAuthToken(null)
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

      // OAuth (not applicable for stdio) — token stored on server.auth
      if (server.transport !== "stdio" && server.auth?.type === "oauth" && server.auth.access_token) {
        let oauthAuth = { ...server.auth };

        // Proactively refresh if token is expired or within 60s of expiry
        if (server.session_id && oauthAuth.expires_at && Date.now() / 1000 > oauthAuth.expires_at - 60) {
          try {
            const refreshed = await apiClient.refreshOAuthToken(server.session_id);
            oauthAuth = { ...oauthAuth, access_token: refreshed.access_token, expires_at: refreshed.expires_at };
            setServers(prev => prev.map(s => s.id === serverId ? { ...s, auth: oauthAuth } : s));
          } catch {
            // Refresh failed — proceed with stale token, backend 401 will surface the error
          }
        }

        payload.auth = {
          type: "oauth",
          access_token: oauthAuth.access_token,
          refresh_token: oauthAuth.refresh_token,
          expires_at: oauthAuth.expires_at,
          token_url: oauthAuth.token_url,
          client_id: oauthAuth.client_id,
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

  const runId = crypto.randomUUID()
  const runStartTime = Date.now()
  const runSteps: ChatMessage[] = []
  const capturedServerId = selectedServerId

  // Streaming message bubble shown while tokens arrive (before tool_call is known)
  const streamingMsgId = generateId()

  // Cancel any in-flight stream from a previous turn
  chatAbortRef.current?.abort()
  const abortController = new AbortController()
  chatAbortRef.current = abortController

  const thinkingMsg: ChatMessage = {
    id: generateId(),
    runId,
    type: "thinking",
    content: "Deciding which tool to use...",
    timestamp: Date.now(),
    perfMark: performance.now()
  }

  try {
    setChatLoading(true)
    updateChat(prev => [...prev, thinkingMsg])
    runSteps.push(thinkingMsg)

    const payload = {
      message,
      chat_history: nextHistory.slice(-8).map(m => ({ type: m.type, content: m.content })),
      provider: llmSettings.provider,
      model: llmSettings.model,
      ...(llmSettings.apiKeys[llmSettings.provider]
        ? { api_key: llmSettings.apiKeys[llmSettings.provider] }
        : {}),
      ...(systemPrompt.trim() ? { system_prompt: systemPrompt.trim() } : {})
    }

    let toolName: string | null = null
    let toolParams: Record<string, unknown> = {}
    let clarificationText: string | null = null
    let streamingStarted = false

    for await (const event of apiClient.chatWithInspectorStream(selectedServer.session_id, payload, abortController.signal)) {
      if (event.type === "thinking") {
        // already showing thinking bubble — no-op
      } else if (event.type === "token" && event.content) {
        if (!streamingStarted) {
          // Replace thinking bubble with streaming assistant bubble
          updateChat(prev => prev.filter((m: ChatMessage) => m.id !== thinkingMsg.id))
          updateChat(prev => [...prev, {
            id: streamingMsgId,
            runId,
            type: "assistant",
            content: event.content ?? "",
            timestamp: Date.now(),
            perfMark: performance.now()
          } as ChatMessage])
          streamingStarted = true
        } else {
          // Append token to existing streaming bubble
          updateChat(prev => prev.map((m: ChatMessage) =>
            m.id === streamingMsgId
              ? { ...m, content: (m.content ?? "") + (event.content ?? "") }
              : m
          ))
        }
      } else if (event.type === "tool_call") {
        toolName = event.tool_name ?? null
        toolParams = (event.params as Record<string, unknown>) ?? {}
      } else if (event.type === "clarification") {
        clarificationText = event.message ?? "Could not determine which tool to run."
      } else if (event.type === "error") {
        clarificationText = event.message ?? "Unable to determine which tool to run."
      }
    }

    // Remove thinking bubble if streaming never started
    updateChat(prev => prev.filter((m: ChatMessage) => m.id !== thinkingMsg.id))
    // Remove streaming bubble — it will be replaced by a proper typed message
    updateChat(prev => prev.filter((m: ChatMessage) => m.id !== streamingMsgId))

    if (clarificationText || !toolName) {
      const assistantMsg: ChatMessage = {
        id: generateId(),
        runId,
        type: "assistant",
        content: clarificationText ?? "Could not determine which tool to run.",
        timestamp: Date.now(),
        perfMark: performance.now()
      }
      updateChat(prev => [...prev, assistantMsg])
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
      toolName,
      params: toolParams,
      timestamp: Date.now(),
      perfMark: performance.now()
    }
    updateChat(prev => [...prev, toolCallMsg])
    runSteps.push(toolCallMsg)

    const result = await apiClient.runInspectorTool(
      selectedServer.session_id,
      toolName,
      toolParams
    )

    const toolDef = selectedServer.tools.find((t: any) => t.name === toolName)
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

    setExecutionHistoryByServer(prev => ({
      ...prev,
      [capturedServerId]: [{ runId, serverId: capturedServerId, startTime: runStartTime, endTime: Date.now(), steps: runSteps }, ...(prev[capturedServerId] ?? [])]
    }))

  } catch (err: any) {
    updateChat(prev => prev.filter((m: ChatMessage) => m.id !== thinkingMsg.id && m.id !== streamingMsgId))

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

  // Abort any in-flight chat stream when the selected server changes or on unmount
  useEffect(() => {
    return () => { chatAbortRef.current?.abort() }
  }, [selectedServerId])

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
    setOAuthToken(null)
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
                  <ServerListPanel
                    servers={servers}
                    selectedServerId={selectedServerId}
                    selectedServer={selectedServer}
                    selectedTool={selectedTool}
                    toolSubTab={toolSubTab}
                    toolSearch={toolSearch}
                    savedRequests={savedRequests}
                    setSelectedServerId={setSelectedServerId}
                    setSelectedTool={setSelectedTool}
                    setToolResult={setToolResult}
                    setToolError={setToolError}
                    setToolSearch={setToolSearch}
                    setToolSubTab={setToolSubTab}
                    setSavedRequests={setSavedRequests}
                    setFormPrefill={setFormPrefill}
                    onDisconnect={handleDisconnect}
                    onReconnect={handleReconnect}
                    onRemove={handleRemove}
                    onAddServer={() => setShowAddModal(true)}
                  />
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
                  <LogsPanel
                    logs={logs}
                    filteredLogs={filteredLogs}
                    logFilter={logFilter}
                    setLogFilter={setLogFilter}
                    logSearch={logSearch}
                    setLogSearch={setLogSearch}
                    logsRef={logsRef}
                    selectedServerId={selectedServerId}
                    hasSession={!!selectedServer?.session_id}
                    logColors={logColors}
                    onClear={() => {
                      if (!selectedServerId) return;
                      const currentOffset = logsClearedOffsetRef.current[selectedServerId] ?? 0;
                      logsClearedOffsetRef.current = { ...logsClearedOffsetRef.current, [selectedServerId]: currentOffset + logs.length };
                      setLogsByServer(prev => ({ ...prev, [selectedServerId]: [] }));
                    }}
                  />
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
                    <ManualToolPanel
                      selectedTool={selectedTool}
                      selectedServer={selectedServer}
                      formPrefill={formPrefill}
                      executing={executing}
                      toolResult={toolResult}
                      toolError={toolError}
                      executionTime={executionTime}
                      lastRunParams={lastRunParams}
                      copyRequestToast={copyRequestToast}
                      saveDialogOpen={saveDialogOpen}
                      saveTitle={saveTitle}
                      setSaveTitle={setSaveTitle}
                      setSaveDialogOpen={setSaveDialogOpen}
                      setCopyRequestToast={setCopyRequestToast}
                      setSavedRequests={setSavedRequests}
                      onRunTool={runTool}
                    />
                  )}

                  {/* ── CHAT MODE ─── */}
                  {mode === "chat" && selectedServer && (
                    <ChatPanel
                      selectedServer={selectedServer}
                      selectedServerId={selectedServerId!}
                      chatHistory={chatHistory}
                      executionHistory={executionHistory}
                      chatInput={chatInput}
                      chatLoading={chatLoading}
                      systemPrompt={systemPrompt}
                      systemPromptDraft={systemPromptDraft}
                      systemPromptOpen={systemPromptOpen}
                      chatRef={chatRef}
                      chatBottomRef={chatBottomRef}
                      setChatInput={setChatInput}
                      setChatHistoryByServer={setChatHistoryByServer}
                      setSystemPrompt={setSystemPrompt}
                      setSystemPromptDraft={setSystemPromptDraft}
                      setSystemPromptOpen={setSystemPromptOpen}
                      onSendMessage={runChatTool}
                      onSendMessageWithText={runChatToolWithMessage}
                    />
                  )}

                  {/* ── RESOURCES MODE ─── */}
                  {mode === "resources" && selectedServer?.status === "connected" && (
                    <ResourcesPanel
                      resources={resources}
                      resourcesLoading={resourcesLoading}
                      selectedResourceUri={selectedResourceUri}
                      setSelectedResourceUri={setSelectedResourceUri}
                      resourceContent={resourceContent}
                      setResourceContent={setResourceContent}
                      resourceContentLoading={resourceContentLoading}
                      setResourceContentLoading={setResourceContentLoading}
                      templateParams={templateParams}
                      setTemplateParams={setTemplateParams}
                      sessionId={selectedServer.session_id!}
                      selectedServerId={selectedServerId!}
                      onRefresh={() => {
                        if (!selectedServer?.session_id || !selectedServerId) return;
                        setResourcesByServer(prev => { const next = { ...prev }; delete next[selectedServerId]; return next; });
                        setSelectedResourceUri(null);
                        setResourceContent(null);
                      }}
                    />
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
                    <PromptsPanel
                      prompts={prompts}
                      promptsLoading={promptsLoading}
                      selectedPrompt={selectedPrompt}
                      setSelectedPrompt={setSelectedPrompt}
                      promptArgs={promptArgs}
                      setPromptArgs={setPromptArgs}
                      promptResult={promptResult}
                      setPromptResult={setPromptResult}
                      promptResultLoading={promptResultLoading}
                      setPromptResultLoading={setPromptResultLoading}
                      sessionId={selectedServer.session_id!}
                      selectedServerId={selectedServerId!}
                      onRefresh={() => {
                        if (!selectedServerId) return;
                        setPromptsByServer(prev => { const n = { ...prev }; delete n[selectedServerId]; return n; });
                        setSelectedPrompt(null); setPromptArgs({}); setPromptResult(null);
                      }}
                    />
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
        <AddServerModal
          connecting={connecting}
          url={url} setUrl={setUrl}
          command={command} setCommand={setCommand}
          transport={transport} setTransport={setTransport}
          authType={authType} setAuthType={setAuthType}
          token={token} setToken={setToken}
          headerKey={headerKey} setHeaderKey={setHeaderKey}
          headerValue={headerValue} setHeaderValue={setHeaderValue}
          customName={customName} setCustomName={setCustomName}
          envVars={envVars} setEnvVars={setEnvVars}
          recentUrls={recentUrls}
          oauthToken={oauthToken} setOAuthToken={setOAuthToken}
          onConnect={handleConnect}
          onClose={() => { setShowAddModal(false); setCustomName(""); setUrl(""); setCommand(""); setEnvVars([]); setTransport("http"); setAuthType("none"); setToken(""); setHeaderKey(""); setHeaderValue(""); setOAuthToken(null); }}
        />
      )}

    </div>
  );
}