// import React from "react";
import { useState, useEffect, useRef } from "react";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { apiClient } from "@/services/api";
import { JsonSchemaForm } from '../components/form/JsonSchemaForm';
import { ToolResult } from '../components/result/ToolResult';
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
}

// Type for log entry
interface LogEntry {
  timestamp: string;
  type: 'connect' | 'disconnect' | 'tool_call' | 'tool_result' | 'tool_error' | 'chat';
  message: string;
}

type ChatMessage = {
  id: string
  type: "user" | "thinking" | "tool_call" | "tool_result" | "assistant" | "error"
  content?: string
  toolName?: string
  params?: any
  result?: any
  timestamp: number
}
// Helper to generate unique server IDs
const generateServerId = () => `server_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

export default function MCPInspector() {

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
  const [executionHistory, setExecutionHistory] = useState<any[]>([])

  const [mode, setMode] = useState<"manual" | "chat">("manual")

  const [chatInput, setChatInput] = useState("")
  // const [chatHistory, setChatHistory] = useState<any[]>([])
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([])
  const [chatLoading, setChatLoading] = useState(false)
  const [panelSizes, setPanelSizes] = useState({
    left: 25,     // percentage (right auto-calculated as 100-left)
    logs: 35      // percentage of left panel height
  })
  const [logs, setLogs] = useState<LogEntry[]>([])
  const logsRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  const handleConnect = async () => {
    if (!url) return;

    // Prevent duplicate servers
    if (servers.some(s => s.url === url)) {
      alert("Server already added");
      return;
    }

    const serverId = generateServerId();

    try {
      setConnecting(true);

      // Add optimistic "connecting" state
      setServers((prev) => [
        ...prev,
        {
          id: serverId,
          session_id: null,
          url,
          transport,
          tools: [],
          status: 'connecting' as const,
        },
      ]);

      const res = await apiClient.connectInspectorServer({
        url,
        transport,
      });

      // Update server with connected state and fetched data
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

      // Auto-select the newly connected server
      setSelectedServerId(serverId);

      setShowAddModal(false);
      setUrl("");
      setTransport("http");
    } catch (err: any) {
      console.error("Failed to connect", err);

      // Update server with failed state
      setServers((prev) =>
        prev.map((s) =>
          s.id === serverId
            ? {
                ...s,
                status: 'failed' as const,
                error: err?.message || 'Failed to connect to MCP server',
              }
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

      const res = await apiClient.connectInspectorServer({
        url: server.url,
        transport: server.transport,
      });

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

    if (selectedServerId === serverId) {
      setSelectedServerId(null);
    }
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
      setExecutionHistory((prev) => [
        {
          id: Date.now(),
          tool: selectedTool,
          params,
          result: res,
          time: new Date().toLocaleTimeString(),
        },
        ...prev,
      ]);
    } catch (err: any) {
      console.error(err);
      setToolError(err?.message || "Tool execution failed");
    } finally {
      setExecuting(false);
    }
  };

 const runChatTool = async () => {
  if (!chatInput || !selectedServer?.session_id) return

  const message = chatInput
  setChatInput("")

  const userMsg: ChatMessage = {
    id: crypto.randomUUID(),
    type: "user",
    content: message,
    timestamp: Date.now()
  }

  setChatHistory(prev => [...prev, userMsg])

  try {
    setChatLoading(true)

    // Show thinking
    const thinkingMsg: ChatMessage = {
      id: crypto.randomUUID(),
      type: "thinking",
      content: "Deciding which tool to use...",
      timestamp: Date.now()
    }

    setChatHistory(prev => [...prev, thinkingMsg])

    // Call backend chat endpoint
    const res = await apiClient.chatWithInspector(
      selectedServer.session_id,
      {
        message,
        chat_history: chatHistory.slice(-8).map(m => ({
          type: m.type,
          content: m.content
        }))
      }
    )

    // Remove thinking message
    setChatHistory(prev => prev.filter(m => m.id !== thinkingMsg.id))

    if (res.clarification_needed) {
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        type: "assistant",
        content: res.message,
        timestamp: Date.now()
      }

      setChatHistory(prev => [...prev, assistantMsg])
      return
    }

    // Tool call message
    const toolCallMsg: ChatMessage = {
      id: crypto.randomUUID(),
      type: "tool_call",
      toolName: res.tool_name,
      params: res.params,
      timestamp: Date.now()
    }

    setChatHistory(prev => [...prev, toolCallMsg])

    // Execute tool
    const result = await apiClient.runInspectorTool(
      selectedServer.session_id,
      res.tool_name,
      res.params
    )

    const resultMsg: ChatMessage = {
      id: crypto.randomUUID(),
      type: "tool_result",
      result,
      timestamp: Date.now()
    }

    setChatHistory(prev => [...prev, resultMsg])

  } catch (err: any) {

    const errorMsg: ChatMessage = {
      id: crypto.randomUUID(),
      type: "error",
      content: err?.message || "Chat error",
      timestamp: Date.now()
    }

    setChatHistory(prev => [...prev, errorMsg])
  } finally {
    setChatLoading(false)
  }
}

  useEffect(() => {
    setToolResult(null)
    setToolError(null)
    setExecutionTime(null)
  }, [selectedTool])

  useEffect(() => {
    const saved = sessionStorage.getItem('inspector-panel-sizes')
    if (saved) setPanelSizes(JSON.parse(saved))
  }, [])

  // Auto-scroll logs to bottom when new entries arrive
  useEffect(() => {
    logsRef.current?.scrollTo({ top: logsRef.current.scrollHeight });
  }, [logs]);

  // Auto-scroll chat to bottom when new messages arrive
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [chatHistory]);

  // Fetch logs from the server
  const fetchLogs = async () => {
    if (!selectedServer?.session_id) return;
    try {
      const res = await apiClient.getInspectorLogs(selectedServer.session_id);
      setLogs(res.logs || []);
    } catch (err) {
      console.error("Failed to fetch logs", err);
    }
  };

  // Poll for logs every 2 seconds when a session is active
  useEffect(() => {
    if (!selectedServer?.session_id) {
      return;
    }
    // NOTE FOR REVIEW: When a new server connects, its logs replace the previous server's logs.
    // Decision needed: Should we accumulate logs across all servers (keyed by session_id)?
    // Or is replacing on new connection acceptable?
    // Options:
    //   A) Current behaviour — replace logs on new connection (simple, clean)
    //   B) Accumulate all logs — merge new logs into existing, tag each entry with server name
    //   C) Per-server log history — store logs[serverId] map, show logs for selected server
    // Leaning towards C if inspector gets heavy usage, but A is fine for now.
    fetchLogs();     // Fetch immediately

    const interval = setInterval(fetchLogs, 2000);     // Set up polling interval

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

  return (
    <div
      className="dashboard"
      style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}
    >
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
                                setSelectedServerId(server.id);
                                setSelectedTool(null);
                                setToolResult(null);
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

                    {/* Execution History */}
                    <div style={{ marginTop: "1.25rem", flexShrink: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                        <h3 style={{ fontSize: "0.9rem", fontWeight: "600" }}>Execution History</h3>
                        <button
                          onClick={() => setExecutionHistory([])}
                          style={{
                            fontSize: "0.7rem", padding: "0.2rem 0.5rem",
                            borderRadius: "0.3rem", border: "1px solid rgba(63,63,70,0.6)",
                            background: "transparent", color: "rgba(255,255,255,0.6)", cursor: "pointer",
                          }}
                        >
                          Clear
                        </button>
                      </div>

                      <div
                        style={{
                          display: "flex", flexDirection: "column", gap: "0.4rem",
                          maxHeight: "160px", overflowY: "auto",
                        }}
                      >
                        {executionHistory.map((item) => (
                          <div
                            key={item.id}
                            onClick={() => {
                              setToolResult(item.result);
                              setSelectedTool(item.tool);
                              setToolError(null);
                            }}
                            style={{
                              padding: "0.4rem 0.5rem",
                              borderRadius: "0.35rem",
                              border: "1px solid rgba(63,63,70,0.6)",
                              cursor: "pointer",
                              background: "rgba(255,255,255,0.04)",
                            }}
                          >
                            <div style={{ fontWeight: 600, fontSize: "0.8rem" }}>{item.tool.name}</div>
                            <div style={{ fontSize: "0.75rem", opacity: 0.6 }}>{item.time}</div>
                          </div>
                        ))}
                      </div>
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
                    <div style={{ padding: "0.75rem 1rem 0.5rem", flexShrink: 0, borderBottom: "1px solid rgba(63,63,70,0.3)" }}>
                      <span style={{ fontSize: "0.8rem", fontWeight: "600", color: "rgba(255,255,255,0.7)", fontFamily: "monospace" }}>
                        LOGS
                      </span>
                      {logs.length > 0 && (
                        <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: "rgba(255,255,255,0.35)" }}>
                          {logs.length} entries
                        </span>
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
                <div style={{ flex: 1, overflow: "hidden", marginTop: "1rem", minHeight: 0 }}>
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
                    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: "0", overflow: "hidden" }}>
                      {selectedServer.status === "connected" ? (
                        <>
                          {/* Chat History */}
                          <div
                            ref={chatRef}
                            style={{
                              flex: 1,
                              minHeight: 0,        
                              overflowY: "auto",
                              overflowX: "hidden",
                              marginBottom: "1rem",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.5rem",
                              paddingRight: "4px"
                            }}
                          >
                            {chatHistory.map((msg) => {

                              if (msg.type === "user") {
                                return (
                                  <div key={msg.id} style={{ alignSelf: "flex-end", background: "rgba(255,255,255,0.1)", padding: "0.5rem", borderRadius: "6px", maxWidth: "75%", wordBreak: "break-word" }}>
                                    {msg.content}
                                  </div>
                                )
                              }

                              if (msg.type === "thinking") {
                                return (
                                  <div key={msg.id} style={{ opacity: 0.6 }}>
                                    {msg.content}
                                  </div>
                                )
                              }

                              if (msg.type === "tool_call") {
                                return (
                                  <div key={msg.id} style={{ background: "rgba(59,130,246,0.15)", padding: "0.5rem", borderRadius: "6px" }}>
                                    <strong>Calling tool:</strong> {msg.toolName}
                                    <pre>{JSON.stringify(msg.params, null, 2)}</pre>
                                  </div>
                                )
                              }

                              if (msg.type === "tool_result") {
                                return (
                                  <div key={msg.id} style={{ maxWidth: "100%", overflowX: "auto" }}>
                                    <ToolResult result={msg.result} />
                                  </div>
                                )
                              }

                              if (msg.type === "assistant") {
                                return (
                                  <div key={msg.id} style={{ background: "rgba(99,102,241,0.2)", padding: "0.5rem", borderRadius: "6px" }}>
                                    {msg.content}
                                  </div>
                                )
                              }

                              if (msg.type === "error") {
                                return (
                                  <div key={msg.id} style={{ background: "rgba(239,68,68,0.15)", padding: "0.5rem", borderRadius: "6px" }}>
                                    {msg.content}
                                  </div>
                                )
                              }

                            })}
                          </div>

                          {/* Chat Input */}
                          <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
                            <input
                              value={chatInput}
                              onChange={(e) => setChatInput(e.target.value)}
                              placeholder="Ask something..."
                              onKeyDown={(e) => { if (e.key === "Enter") runChatTool(); }}
                              style={{
                                flex: 1, minWidth: 0, padding: "0.5rem",
                                borderRadius: "0.35rem", border: "1px solid rgba(63,63,70,0.6)",
                                background: "#09090b", color: "#fff",
                              }}
                            />
                            <button
                              onClick={runChatTool}
                              disabled={chatLoading}
                              style={{
                                padding: "0.5rem 0.75rem", borderRadius: "0.35rem",
                                background: "#fff", color: "#000", fontWeight: "600", flexShrink: 0,
                              }}
                            >
                              {chatLoading ? "..." : "Send"}
                            </button>
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