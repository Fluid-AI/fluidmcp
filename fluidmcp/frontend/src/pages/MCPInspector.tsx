// import React from "react";
import { useState, useEffect } from "react";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { apiClient } from "@/services/api";
import { JsonSchemaForm } from '../components/form/JsonSchemaForm';
import { ToolResult } from '../components/result/ToolResult';

export default function MCPInspector() {

  const [showAddModal, setShowAddModal] = useState(false);
  const [url, setUrl] = useState("");
  const [transport, setTransport] = useState("http");
  const [servers, setServers] = useState<any[]>([]);
  const [connecting, setConnecting] = useState(false);
  const [selectedServer, setSelectedServer] = useState<any | null>(null);

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

  const handleConnect = async () => {
  if (!url) return;

  try {
    setConnecting(true);

    const res = await apiClient.connectInspectorServer({
      url,
      transport,
    });


    setServers((prev) => {
      if (prev.some(s => s.session_id === res.session_id)) return prev; 
      return [...prev, { ...res, url, transport, }]
    });

    setShowAddModal(false);
    setUrl("");
    setTransport("http");

  } catch (err) {
    console.error("Failed to connect", err);
    alert("Failed to connect to MCP server");
  } finally {
    setConnecting(false);
  }
  };

  const handleDisconnect = async (session_id: string) => {
    try {
      await apiClient.disconnectInspectorServer(session_id);
      setServers((prev) => prev.filter((s) => s.session_id !== session_id));

      if (selectedServer?.session_id === session_id) {
        setSelectedServer(null);
      }
    }catch (err) {
      console.error("Failed to disconnect", err);
      alert("Failed to disconnect from MCP server");
    }
  };

  const runTool = async (params: any) => {
    if (!selectedServer || !selectedTool || executing) return

    try {
      setExecuting(true)
      setToolError(null)

      const start = performance.now()

      const res = await apiClient.runInspectorTool(
        selectedServer.session_id,
        selectedTool.name,
        params
      )

      const end = performance.now()

      setToolResult(res)
      setExecutionTime((end - start) / 1000)
      setExecutionHistory(prev => [
        {
          id: Date.now(),
          tool: selectedTool,
          params,
          result: res,
          time: new Date().toLocaleTimeString()
        },
        ...prev
      ])
    } catch (err: any) {
      console.error(err)
      setToolError(err?.message || "Tool execution failed")
    } finally {
      setExecuting(false)
    }
  }

  const runChatTool = async () => {
    if (!chatInput || !selectedServer) return

    try {
      setChatLoading(true)

      const message = chatInput

      setChatHistory(prev => [
        ...prev,
        { role: "user", content: message }
      ])

      // simple heuristic: use first tool
      // const messageLower = message.toLowerCase()

      // let tool =
      //   selectedServer.tools.find((t:any) =>
      //     messageLower.includes(t.name.replace("_", " "))
      //   ) ||
      //   selectedServer.tools.find((t:any) =>
      //     messageLower.includes("details")
      //   ) ||
      //   selectedServer.tools[0]
      const tool = selectedTool || selectedServer.tools?.[0]

      if (!tool) throw new Error("No tools available")

      const res = await apiClient.runInspectorTool(
        selectedServer.session_id,
        tool.name,
        { location: message} 
      )

      setChatHistory(prev => [
        ...prev,
        { role: "assistant", content: JSON.stringify(res, null, 2) }
      ])

      setChatInput("")

    } catch (err: any) {
      setChatHistory(prev => [
        ...prev,
        { role: "assistant", content: "Error running tool" }
      ])
    } finally {
      setChatLoading(false)
    }
  }

  useEffect(() => {
    setToolResult(null)
    setToolError(null)
    setExecutionTime(null)
  }, [selectedTool])

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
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "320px 1fr",
              gap: "2rem",
              minHeight: "600px",
            }}
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
                  servers.map((server, i) => (
                    <div
                      key={i}
                      onClick={() => {
                        setSelectedServer(server)
                        setSelectedTool(null)
                        setToolResult(null)
                      }}
                      style={{
                        marginTop: "1rem",
                        padding: "1rem",
                        border: "1px solid rgba(63,63,70,0.6)",
                        borderRadius: "0.6rem",
                        cursor: "pointer",
                        background:
                          selectedServer?.session_id === server.session_id
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
                          {server?.server_info?.name || "Connected Server"}
                        </div>

                        <span
                          style={{
                            fontSize: "0.7rem",
                            padding: "0.2rem 0.5rem",
                            borderRadius: "0.3rem",
                            background: "rgba(16,185,129,0.2)",
                            color: "#10b981",
                          }}
                        >
                          connected
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
                      {/* DISCONNECT */}
                      <div
                        style={{
                          marginTop: "0.6rem",
                          display: "flex",
                          justifyContent: "flex-end",
                        }}
                      >
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDisconnect(server.session_id);
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
                      </div>

                      {/* TOOLS */}
                      {selectedServer?.session_id === server.session_id &&
                        server?.tools?.map((tool: any) => (
                          <div
                            key={tool.name}
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedTool(tool)
                              setToolResult(null)
                              setToolError(null)
                            }}
                            style={{
                              marginLeft: "0.8rem",
                              marginTop: "0.4rem",
                              fontSize: "0.85rem",
                              cursor: "pointer",
                              color:
                                selectedTool?.name === tool.name
                                  ? "#fff"
                                  : "rgba(255,255,255,0.7)"
                            }}
                          >
                            • {tool.name}
                          </div>
                        ))}
                    </div>
                  ))
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
              <button onClick={() => setExecutionHistory([])}>
                Clear
              </button>
            </div>

            {/* RIGHT PANEL */}
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
                </div>
              )}
              {mode === "chat" && selectedServer && (
                <div style={{ marginTop: "1rem", width: "100%" }}>
                  
                  {/* Chat History */}
                  <div
                    style={{
                      maxHeight: "400px",
                      overflow: "auto",
                      marginBottom: "1rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.5rem"
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
                              : "rgba(99,102,241,0.2)"
                        }}
                      >
                        <strong>{msg.role}</strong>
                        <pre style={{ margin: 0,whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
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
                        if (e.key === "Enter") runChatTool()
                      }}
                      style={{
                        flex: 1,
                        minWidth: 0,
                        padding: "0.5rem",
                        borderRadius: "0.35rem",
                        border: "1px solid rgba(63,63,70,0.6)",
                        background: "#09090b",
                        color: "#fff"
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
                        flexShrink: 0
                      }}
                    >
                      Send
                    </button>
                  </div>

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
            </div>
          </div>
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