// import React from "react";
import { useState } from "react";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { apiClient } from "@/services/api";

export default function MCPInspector() {

  const [showAddModal, setShowAddModal] = useState(false);
  const [url, setUrl] = useState("");
  const [transport, setTransport] = useState("http");
  const [servers, setServers] = useState<any[]>([]);
  const [connecting, setConnecting] = useState(false);

  const handleConnect = async () => {
  if (!url) return;

  try {
    setConnecting(true);

    const res = await apiClient.connectInspectorServer({
      url,
      transport,
    });


    setServers((prev) => [...prev, res]);

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
                    <div key={i} style={{ marginTop: "1rem" }}>
                      {server.server_info?.name || "Connected Server"}
                    </div>
                  ))
                )}
              </div>
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
                Connect a server to start inspecting tools
              </div>
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