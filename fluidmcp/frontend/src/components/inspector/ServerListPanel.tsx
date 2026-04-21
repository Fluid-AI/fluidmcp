import React from "react";
import { type SavedRequest, loadSavedRequests, deleteSavedRequest } from "@/lib/saved-requests";

interface MCPServer {
  id: string;
  session_id: string | null;
  name?: string;
  server_info?: any;
  tools: any[];
  url: string;
  transport: string;
  status: 'connecting' | 'connected' | 'disconnected' | 'failed';
  connectedAt?: number;
  error?: string;
}

function relativeTime(ts: number): string {
  const secs = Math.floor((Date.now() - ts) / 1000);
  if (secs < 10) return "just now";
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ago`;
}

interface ServerListPanelProps {
  servers: MCPServer[];
  selectedServerId: string | null;
  selectedServer: MCPServer | null;
  selectedTool: any | null;
  toolSubTab: "tools" | "saved";
  toolSearch: string;
  savedRequests: SavedRequest[];
  setSelectedServerId: (id: string) => void;
  setSelectedTool: (t: any | null) => void;
  setToolResult: (r: any) => void;
  setToolError: (e: string | null) => void;
  setToolSearch: (s: string) => void;
  setToolSubTab: (tab: "tools" | "saved") => void;
  setSavedRequests: (reqs: SavedRequest[]) => void;
  setFormPrefill: (v: Record<string, any> | undefined) => void;
  onDisconnect: (serverId: string) => void;
  onReconnect: (serverId: string) => void;
  onRemove: (serverId: string) => void;
  onAddServer: () => void;
}

const STATUS_CONFIG = {
  connecting:   { text: "Connecting...", bg: "rgba(59,130,246,0.2)",  color: "#3b82f6" },
  connected:    { text: "Connected",     bg: "rgba(16,185,129,0.2)",   color: "#10b981" },
  disconnected: { text: "Disconnected",  bg: "rgba(107,114,128,0.2)", color: "#6b7280" },
  failed:       { text: "Failed",        bg: "rgba(239,68,68,0.2)",    color: "#ef4444" },
};

export const ServerListPanel: React.FC<ServerListPanelProps> = ({
  servers,
  selectedServerId,
  selectedServer,
  selectedTool,
  toolSubTab,
  toolSearch,
  savedRequests,
  setSelectedServerId,
  setSelectedTool,
  setToolResult,
  setToolError,
  setToolSearch,
  setToolSubTab,
  setSavedRequests,
  setFormPrefill,
  onDisconnect,
  onReconnect,
  onRemove,
  onAddServer,
}) => {
  return (
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
        <h2 style={{ fontSize: "1.1rem", fontWeight: "600" }}>Servers</h2>
        <button
          style={{
            background: "#fff", color: "#000", border: "none",
            padding: "0.35rem 0.75rem", borderRadius: "0.375rem",
            fontSize: "0.8rem", fontWeight: "600", cursor: "pointer",
          }}
          onClick={onAddServer}
        >
          + Add
        </button>
      </div>

      {/* Server list */}
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
            const statusInfo = STATUS_CONFIG[server.status];
            const isSelected = selectedServerId === server.id;

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
                {/* Header row */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontWeight: "600", fontSize: "0.9rem" }}>
                    {server.name || server.server_info?.name || "MCP Server"}
                  </div>
                  <span style={{
                    fontSize: "0.7rem", padding: "0.2rem 0.5rem", borderRadius: "0.3rem",
                    background: statusInfo.bg, color: statusInfo.color, flexShrink: 0,
                  }}>
                    {statusInfo.text}
                  </span>
                </div>

                {/* URL + meta */}
                <div style={{ marginTop: "0.3rem", fontSize: "0.75rem", color: "rgba(255,255,255,0.5)", wordBreak: "break-all" }}>
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

                {/* Error */}
                {server.status === "failed" && server.error && (
                  <div style={{
                    marginTop: "0.5rem", fontSize: "0.75rem", color: "#ef4444",
                    padding: "0.4rem", background: "rgba(239,68,68,0.1)", borderRadius: "0.3rem", wordBreak: "break-word",
                  }}>
                    {server.error}
                  </div>
                )}

                {/* Action buttons */}
                <div style={{ marginTop: "0.6rem", display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                  {server.status === "connected" && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onDisconnect(server.id); }}
                      style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem", borderRadius: "0.35rem", border: "1px solid rgba(63,63,70,0.6)", background: "transparent", color: "#fff", cursor: "pointer" }}
                    >Disconnect</button>
                  )}
                  {server.status === "disconnected" && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onReconnect(server.id); }}
                      style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem", borderRadius: "0.35rem", border: "1px solid rgba(107,114,128,0.6)", background: "rgba(107,114,128,0.1)", color: "#fff", cursor: "pointer" }}
                    >Reconnect</button>
                  )}
                  {server.status === "failed" && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onReconnect(server.id); }}
                      style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem", borderRadius: "0.35rem", border: "1px solid rgba(239,68,68,0.6)", background: "rgba(239,68,68,0.1)", color: "#ef4444", cursor: "pointer" }}
                    >Retry</button>
                  )}
                  {server.status !== "connecting" && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onRemove(server.id); }}
                      style={{ fontSize: "0.75rem", padding: "0.25rem 0.4rem", borderRadius: "0.35rem", border: "1px solid rgba(63,63,70,0.6)", background: "transparent", color: "rgba(255,255,255,0.6)", cursor: "pointer" }}
                      title="Remove server"
                    >✕</button>
                  )}
                </div>

                {/* Tools / Saved (only when selected) */}
                {isSelected && (server.tools?.length ?? 0) > 0 && (
                  <>
                    {/* Sub-tabs */}
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

                    {/* Tool search */}
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

                    {/* Saved requests list */}
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
                              margin: "0.3rem 0.5rem", padding: "0.35rem 0.5rem",
                              borderRadius: "5px", border: "1px solid rgba(63,63,70,0.4)",
                              background: "rgba(0,0,0,0.2)", cursor: "pointer",
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
                                  if (!selectedServer) return;
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

                {/* Tool list */}
                {isSelected && toolSubTab === "tools" && server.tools.filter((t: any) =>
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
                        marginLeft: "0.5rem", marginTop: "0.4rem",
                        fontSize: "0.82rem", cursor: "pointer",
                        color: selectedTool?.name === tool.name ? "#fff" : "rgba(255,255,255,0.65)",
                        padding: "0.2rem 0.4rem", borderRadius: "0.25rem",
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
  );
};
