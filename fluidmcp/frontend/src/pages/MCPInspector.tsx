// import React from "react";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";

export default function Inspector() {
    return (
        <div
      className="dashboard"
      style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}
    >
      <Navbar />

      <div style={{ paddingTop: "64px", flex: 1 }}>
        <div
          style={{
            maxWidth: "1400px",
            margin: "0 auto",
            padding: "2rem",
          }}
        >
          <h1 style={{ fontSize: "2rem", fontWeight: "bold" }}>
            MCP Inspector
          </h1>

          <p style={{ color: "rgba(255,255,255,0.6)", marginTop: "0.5rem" }}>
            Connect to any MCP server and inspect its tools.
          </p>

          <div
            style={{
              marginTop: "2rem",
              border: "1px solid rgba(63,63,70,0.5)",
              borderRadius: "0.75rem",
              padding: "2rem",
            }}
          >
            <p>No servers connected yet.</p>
            <p style={{ marginTop: "0.5rem", opacity: 0.6 }}>
              Click "Add Server" to connect to an MCP server.
            </p>
          </div>
        </div>
      </div>

      <Footer />
    </div>
    );
}