// import React from "react";
import { useState, useEffect } from "react";
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
  const [chatHistory, setChatHistory] = useState<any[]>([])
  const [chatLoading, setChatLoading] = useState(false)
  const [panelSizes, setPanelSizes] = useState({
    left: 25,     // percentage (right auto-calculated as 100-left)
    logs: 40      // percentage
  })
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
    if (!chatInput || !selectedServer?.session_id) return;

    try {
      setChatLoading(true);

      const message = chatInput;

      setChatHistory((prev) => [...prev, { role: "user", content: message }]);

      const tool = selectedTool || selectedServer.tools?.[0];

      if (!tool) throw new Error("No tools available");

      const res = await apiClient.runInspectorTool(
        selectedServer.session_id,
        tool.name,
        { location: message }
      );

      setChatHistory((prev) => [
        ...prev,
        { role: "assistant", content: JSON.stringify(res, null, 2) },
      ]);

      setChatInput("");
    } catch (err: any) {
      setChatHistory((prev) => [
        ...prev,
        { role: "assistant", content: "Error running tool" },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  useEffect(() => {
    setToolResult(null)
    setToolError(null)
    setExecutionTime(null)
  }, [selectedTool])

  useEffect(() => {
    const saved = sessionStorage.getItem('inspector-panel-sizes')
    if (saved) setPanelSizes(JSON.parse(saved))
  }, [])

  return (
    <div
      className="dashboard"
      style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}
    >
      <Navbar />

      <div style={{ paddingTop: "64px", flex: 1 }}>
        <div
          style={{
            maxWidth: "1600px",
            margin: "0 auto",
            padding: "2rem",
          }}
        >
          {/* Page Header */}
          <div style={{ marginBottom: "2rem" }}>
            <h1 style={{ fontSize: "2rem", fontWeight: "bold" }}>
              MCP Inspector
            </h1>
            <p style={{ color: "rgba(255,255,255,0.6)", marginTop: "0.5rem" }}>
              Connect to any MCP server and inspect its tools.
            </p>
          </div>

          {/* Main Layout */}
          <PanelGroup 
            direction="horizontal" 
            onLayout={(sizes) => {
              setPanelSizes(prev => {
                const updated = { ...prev, left: sizes[0] };
                sessionStorage.setItem('inspector-panel-sizes', JSON.stringify(updated));
                return updated;
              });
            }}
            style={{ minHeight: "600px" }}
          >
            {/* LEFT PANEL (outer) */}
            <Panel 
              defaultSize={panelSizes.left} 
              minSize={20} 
              maxSize={50}
              style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}
            >
              {/* LEFT PANEL INNER: Vertical split between Servers+Tools and Logs */}
              <PanelGroup 
                direction="vertical" 
                onLayout={(sizes) => {
                  setPanelSizes(prev => {
                    const updated = { ...prev, logs: sizes[1] };
                    sessionStorage.setItem('inspector-panel-sizes', JSON.stringify(updated));
                    return updated;
                  });
                }}
                style={{ flex: 1 }}
              >
                {/* TOP: Servers + Tools Section */}
                <Panel 
                  defaultSize={100 - panelSizes.logs} 
                  minSize={40}
                  style={{ overflow: "auto", display: "flex", flexDirection: "column" }}
                >
            {/* LEFT PANEL */}
            <div
              style={{
                border: "1px solid rgba(63,63,70,0.5)",
                borderRadius: "0.75rem",
                padding: "1.5rem",
                background:
                  "linear-gradient(to bottom right, rgba(39,39,42,0.9), rgba(24,24,27,0.9))",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
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
              {/* Connected Servers List or Empty State */}
              <div
                style={{
                  marginTop: "1rem",
                  padding: "1rem",
                  border: "1px dashed rgba(63,63,70,0.6)",
                  borderRadius: "0.5rem",
                  textAlign: "center",
                  color: "rgba(255,255,255,0.6)",
                }}
              >
                {servers.length === 0 ? (
                  <div> No servers connected </div>
                ) : (
                  servers.map((server) => {
                    // Determine badge color and text based on status
                    const statusConfig = {
                      connecting: {
                        text: "Connecting...",
                        bg: "rgba(59,130,246,0.2)",
                        color: "#3b82f6",
                      },
                      connected: {
                        text: "Connected",
                        bg: "rgba(16,185,129,0.2)",
                        color: "#10b981",
                      },
                      disconnected: {
                        text: "Disconnected",
                        bg: "rgba(107,114,128,0.2)",
                        color: "#6b7280",
                      },
                      failed: {
                        text: "Failed",
                        bg: "rgba(239,68,68,0.2)",
                        color: "#ef4444",
                      },
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
                          marginTop: "1rem",
                          padding: "1rem",
                          border: "1px solid rgba(63,63,70,0.6)",
                          borderRadius: "0.6rem",
                          cursor: "pointer",
                          background: isSelected
                            ? "rgba(255,255,255,0.08)"
                            : "transparent",
                        }}
                      >
                        {/* HEADER */}
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                        >
                          <div style={{ fontWeight: "600" }}>
                            {server?.server_info?.name || "MCP Server"}
                          </div>

                          <span
                            style={{
                              fontSize: "0.7rem",
                              padding: "0.2rem 0.5rem",
                              borderRadius: "0.3rem",
                              background: statusInfo.bg,
                              color: statusInfo.color,
                            }}
                          >
                            {statusInfo.text}
                          </span>
                        </div>

                        {/* URL */}
                        <div
                          style={{
                            marginTop: "0.3rem",
                            fontSize: "0.8rem",
                            color: "rgba(255,255,255,0.6)",
                            wordBreak: "break-all",
                          }}
                        >
                          {server.url}
                        </div>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "rgba(255,255,255,0.5)",
                          }}
                        >
                          transport: {server.transport}
                        </div>

                        {/* ERROR MESSAGE (for failed status) */}
                        {server.status === "failed" && server.error && (
                          <div
                            style={{
                              marginTop: "0.5rem",
                              fontSize: "0.75rem",
                              color: "#ef4444",
                              padding: "0.5rem",
                              background: "rgba(239,68,68,0.1)",
                              borderRadius: "0.3rem",
                              wordBreak: "break-word",
                            }}
                          >
                            {server.error}
                          </div>
                        )}

                        {/* ACTION BUTTONS */}
                        <div
                          style={{
                            marginTop: "0.6rem",
                            display: "flex",
                            justifyContent: "flex-end",
                            gap: "0.5rem",
                          }}
                        >
                          {server.status === "connected" && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDisconnect(server.id);
                              }}
                              style={{
                                fontSize: "0.75rem",
                                padding: "0.25rem 0.6rem",
                                borderRadius: "0.35rem",
                                border: "1px solid rgba(63,63,70,0.6)",
                                background: "transparent",
                                color: "#fff",
                                cursor: "pointer",
                              }}
                            >
                              Disconnect
                            </button>
                          )}

                          {server.status === "disconnected" && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleReconnect(server.id);
                              }}
                              style={{
                                fontSize: "0.75rem",
                                padding: "0.25rem 0.6rem",
                                borderRadius: "0.35rem",
                                border: "1px solid rgba(107,114,128,0.6)",
                                background: "rgba(107,114,128,0.1)",
                                color: "#fff",
                                cursor: "pointer",
                              }}
                            >
                              Reconnect
                            </button>
                          )}

                          {server.status === "failed" && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleReconnect(server.id);
                              }}
                              style={{
                                fontSize: "0.75rem",
                                padding: "0.25rem 0.6rem",
                                borderRadius: "0.35rem",
                                border: "1px solid rgba(239,68,68,0.6)",
                                background: "rgba(239,68,68,0.1)",
                                color: "#ef4444",
                                cursor: "pointer",
                              }}
                            >
                              Retry
                            </button>
                          )}

                          {server.status !== "connecting" && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRemove(server.id);
                              }}
                              style={{
                                fontSize: "0.75rem",
                                padding: "0.25rem 0.4rem",
                                borderRadius: "0.35rem",
                                border: "1px solid rgba(63,63,70,0.6)",
                                background: "transparent",
                                color: "rgba(255,255,255,0.6)",
                                cursor: "pointer",
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
                              marginLeft: "0.8rem",
                              marginTop: "0.4rem",
                              fontSize: "0.85rem",
                              cursor: "pointer",
                              color:
                                selectedTool?.name === tool.name
                                  ? "#fff"
                                  : "rgba(255,255,255,0.7)",
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
              <div style={{ marginTop: "1.5rem" }}>
                <h3 style={{ marginBottom: "0.5rem" }}>Execution History</h3>

                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.5rem",
                    maxHeight: "200px",
                    overflowY: "auto"
                  }}
                >
                  {executionHistory.map((item) => (
                    <div
                      key={item.id}
                      onClick={() => {
                        setToolResult(item.result)
                        setSelectedTool( item.tool )
                        setToolError(null)
                      }}
                      style={{
                        padding: "0.5rem",
                        borderRadius: "0.35rem",
                        border: "1px solid rgba(63,63,70,0.6)",
                        cursor: "pointer",
                        background: "rgba(255,255,255,0.05)"
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{item.tool.name}</div>
                      <div style={{ fontSize: "0.8rem", opacity: 0.7 }}>
                        {item.time}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <button
                onClick={() => setExecutionHistory([])}
                style={{
                  marginTop: "0.5rem",
                  fontSize: "0.75rem",
                  padding: "0.25rem 0.6rem",
                  borderRadius: "0.35rem",
                  border: "1px solid rgba(63,63,70,0.6)",
                  background: "transparent",
                  color: "#fff",
                  cursor: "pointer",
                }}
              >
                Clear
              </button>
            </div>

                </Panel>

                {/* Vertical Divider between Servers+Tools and Logs */}
                <PanelResizeHandle
                  style={{
                    backgroundColor: "rgba(63,63,70,0.3)",
                    height: "4px",
                    cursor: "row-resize",
                    transition: "background 0.15s ease",
                  }}
                  onMouseEnter={(e: any) => { e.target.style.backgroundColor = "rgba(63,63,70,0.5)" }}
                  onMouseLeave={(e: any) => { e.target.style.backgroundColor = "rgba(63,63,70,0.3)" }}
                />

                {/* BOTTOM: Logs Section (Placeholder for Phase 3) */}
                <Panel 
                  defaultSize={panelSizes.logs} 
                  minSize={15}
                  style={{ overflow: "auto", overflowY: "auto", display: "flex", flexDirection: "column" }}
                >
                  <div
                    style={{
                      padding: "1rem",
                      border: "1px dashed rgba(63,63,70,0.6)",
                      borderRadius: "0.5rem",
                      textAlign: "center",
                      color: "rgba(255,255,255,0.5)",
                      height: "100%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    Logs section (coming next phase)
                  </div>
                </Panel>
              </PanelGroup>
            </Panel>

            {/* Horizontal Divider between Left and Right Panels */}
            <PanelResizeHandle
              style={{
                backgroundColor: "rgba(63,63,70,0.3)",
                width: "4px",
                cursor: "col-resize",
                transition: "background 0.15s ease",
              }}
              onMouseEnter={(e: any) => { e.target.style.backgroundColor = "rgba(63,63,70,0.5)" }}
              onMouseLeave={(e: any) => { e.target.style.backgroundColor = "rgba(63,63,70,0.3)" }}
            />

            {/* RIGHT PANEL */}
            <Panel 
              defaultSize={100 - panelSizes.left} 
              minSize={50}
              style={{ overflow: "auto", display: "flex", flexDirection: "column" }}
            >
            <div
              style={{
                border: "1px solid rgba(63,63,70,0.5)",
                borderRadius: "0.75rem",
                padding: "1.5rem",
                background:
                  "linear-gradient(to bottom right, rgba(39,39,42,0.9), rgba(24,24,27,0.9))",
              }}
            >
              <h2 style={{ fontSize: "1.1rem", fontWeight: "600" }}>
                Tool Execution
              </h2>
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
                <button
                  onClick={() => setMode("manual")}
                  style={{
                    padding: "0.35rem 0.75rem",
                    borderRadius: "0.35rem",
                    border: "1px solid rgba(63,63,70,0.6)",
                    background: mode === "manual" ? "#fff" : "transparent",
                    color: mode === "manual" ? "#000" : "#fff",
                    cursor: "pointer"
                  }}
                >
                  Manual
                </button>

                <button
                  onClick={() => setMode("chat")}
                  style={{
                    padding: "0.35rem 0.75rem",
                    borderRadius: "0.35rem",
                    border: "1px solid rgba(63,63,70,0.6)",
                    background: mode === "chat" ? "#fff" : "transparent",
                    color: mode === "chat" ? "#000" : "#fff",
                    cursor: "pointer"
                  }}
                >
                  Chat
                </button>
              </div>
              {mode === "manual" && selectedServer && selectedTool && (
                <div style={{ marginTop: "1rem" }}>
                  <h3 style={{ marginBottom: "1rem" }}>
                    {selectedTool.name}
                  </h3>

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
                    <div
                      style={{
                        padding: "1rem",
                        border: "1px dashed rgba(239,68,68,0.6)",
                        borderRadius: "0.5rem",
                        textAlign: "center",
                        color: "rgba(239,68,68,0.8)",
                      }}
                    >
                      Server is not connected. Please reconnect to run tools.
                    </div>
                  )}
                </div>
              )}
              {mode === "chat" && selectedServer && (
                <div style={{ marginTop: "1rem", width: "100%" }}>
                  {selectedServer.status === "connected" ? (
                    <>
                      {/* Chat History */}
                      <div
                        style={{
                          maxHeight: "400px",
                          overflow: "auto",
                          marginBottom: "1rem",
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.5rem",
                        }}
                      >
                        {chatHistory.map((msg, i) => (
                          <div
                            key={i}
                            style={{
                              padding: "0.5rem",
                              borderRadius: "0.35rem",
                              background:
                                msg.role === "user"
                                  ? "rgba(255,255,255,0.1)"
                                  : "rgba(99,102,241,0.2)",
                            }}
                          >
                            <strong>{msg.role}</strong>
                            <pre
                              style={{
                                margin: 0,
                                whiteSpace: "pre-wrap",
                                wordBreak: "break-word",
                              }}
                            >
                              {msg.content}
                            </pre>
                          </div>
                        ))}
                      </div>

                      {/* Chat Input Row */}
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <input
                          value={chatInput}
                          onChange={(e) => setChatInput(e.target.value)}
                          placeholder="Ask something..."
                          onKeyDown={(e) => {
                            if (e.key === "Enter") runChatTool();
                          }}
                          style={{
                            flex: 1,
                            minWidth: 0,
                            padding: "0.5rem",
                            borderRadius: "0.35rem",
                            border: "1px solid rgba(63,63,70,0.6)",
                            background: "#09090b",
                            color: "#fff",
                          }}
                        />

                        <button
                          onClick={runChatTool}
                          disabled={chatLoading}
                          style={{
                            padding: "0.5rem 0.75rem",
                            borderRadius: "0.35rem",
                            background: "#fff",
                            color: "#000",
                            fontWeight: "600",
                            flexShrink: 0,
                          }}
                        >
                          Send
                        </button>
                      </div>
                    </>
                  ) : (
                    <div
                      style={{
                        padding: "1rem",
                        border: "1px dashed rgba(239,68,68,0.6)",
                        borderRadius: "0.5rem",
                        textAlign: "center",
                        color: "rgba(239,68,68,0.8)",
                      }}
                    >
                      Server is not connected. Please reconnect to chat.
                    </div>
                  )}
                </div>
              )}
              {mode === "manual" && (!selectedServer || !selectedTool) && (
                <div
                  style={{
                    marginTop: "1rem",
                    padding: "1rem",
                    border: "1px dashed rgba(63,63,70,0.6)",
                    borderRadius: "0.5rem",
                    textAlign: "center",
                    color: "rgba(255,255,255,0.6)",
                  }}
                >
                  Select a tool to execute
                </div>
              )}
              {mode === "chat" && (!selectedServer || selectedServer.status !== "connected") && (
                <div
                  style={{
                    marginTop: "1rem",
                    padding: "1rem",
                    border: "1px dashed rgba(63,63,70,0.6)",
                    borderRadius: "0.5rem",
                    textAlign: "center",
                    color: "rgba(255,255,255,0.6)",
                  }}
                >
                  {!selectedServer
                    ? "Select a connected server to chat"
                    : "Server is not connected. Please reconnect to chat."}
                </div>
              )}
            </div>
            </Panel>
          </PanelGroup>
        </div>
      </div>

      {showAddModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "#18181b",
              padding: "2rem",
              borderRadius: "0.75rem",
              width: "420px",
              border: "1px solid rgba(63,63,70,0.6)",
            }}
          >
            <h2 style={{ fontSize: "1.3rem", marginBottom: "1rem" }}>
              Connect MCP Server
            </h2>

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <input
                placeholder="Server URL"
                style={{
                  padding: "0.6rem",
                  borderRadius: "0.4rem",
                  border: "1px solid rgba(63,63,70,0.6)",
                  background: "#09090b",
                  color: "#fff",
                }}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />

              <select
                value={transport}
                onChange={(e) => setTransport(e.target.value)}
                style={{
                  padding: "0.6rem",
                  borderRadius: "0.4rem",
                  border: "1px solid rgba(63,63,70,0.6)",
                  background: "#09090b",
                  color: "#fff",
                }}
              >
                <option value="http">HTTP</option>
                <option value="sse">SSE</option>
              </select>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                <button
                  onClick={() => setShowAddModal(false)}
                  style={{
                    background: "transparent",
                    border: "1px solid rgba(63,63,70,0.6)",
                    padding: "0.5rem 1rem",
                    borderRadius: "0.4rem",
                    color: "#fff",
                  }}
                >
                  Cancel
                </button>

                <button
                  onClick={handleConnect}
                  disabled={connecting}
                  style={{
                    background: "#fff",
                    color: "#000",
                    padding: "0.5rem 1rem",
                    borderRadius: "0.4rem",
                    fontWeight: "600",
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