import React from "react";
import { JsonSchemaForm } from "@/components/form/JsonSchemaForm";
import { ToolResult } from "@/components/result/ToolResult";
import { type SavedRequest, saveRequest, loadSavedRequests } from "@/lib/saved-requests";

interface MCPTool {
  name: string;
  description?: string;
  inputSchema?: any;
  annotations?: Record<string, boolean>;
}

interface MCPServer {
  session_id: string | null;
  status: string;
  url: string;
}

interface ManualToolPanelProps {
  selectedTool: MCPTool;
  selectedServer: MCPServer;
  formPrefill: Record<string, any> | undefined;
  executing: boolean;
  toolResult: any;
  toolError: string | null;
  executionTime: number | null;
  lastRunParams: any | null;
  copyRequestToast: boolean;
  saveDialogOpen: boolean;
  saveTitle: string;
  setSaveTitle: (v: string) => void;
  setSaveDialogOpen: (v: boolean) => void;
  setCopyRequestToast: (v: boolean) => void;
  setSavedRequests: (reqs: SavedRequest[]) => void;
  onRunTool: (params: any) => void;
}

const ANNOTATION_META = [
  { key: "readOnlyHint",    label: "Read-only",   bg: "rgba(63,63,70,0.6)",    color: "rgba(220,220,220,0.85)", tip: "Tool does not modify state" },
  { key: "destructiveHint", label: "Destructive", bg: "rgba(239,68,68,0.18)",  color: "rgba(252,165,165,0.95)", tip: "Tool may delete or overwrite data" },
  { key: "idempotentHint",  label: "Idempotent",  bg: "rgba(34,197,94,0.15)",  color: "rgba(134,239,172,0.9)",  tip: "Same call with same args always gives same result" },
  { key: "openWorldHint",   label: "External",    bg: "rgba(59,130,246,0.18)", color: "rgba(147,197,253,0.95)", tip: "Tool interacts with the external world (web, APIs, filesystem)" },
];

export const ManualToolPanel: React.FC<ManualToolPanelProps> = ({
  selectedTool,
  selectedServer,
  formPrefill,
  executing,
  toolResult,
  toolError,
  executionTime,
  lastRunParams,
  copyRequestToast,
  saveDialogOpen,
  saveTitle,
  setSaveTitle,
  setSaveDialogOpen,
  setCopyRequestToast,
  setSavedRequests,
  onRunTool,
}) => {
  const ann = selectedTool.annotations ?? {};
  const activeBadges = ANNOTATION_META.filter(a => ann[a.key]);

  return (
    <div style={{ overflowY: "auto", flex: 1, minHeight: 0, paddingBottom: "0.5rem", marginTop: "1rem" }}>
      {/* Tool header */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap", marginBottom: "1rem" }}>
        <h3 style={{ margin: 0 }}>{selectedTool.name}</h3>
        {activeBadges.map(a => (
          <span key={a.label} title={a.tip} style={{
            fontSize: "0.65rem", padding: "0.15rem 0.55rem", borderRadius: "999px",
            background: a.bg, color: a.color, fontWeight: 600, cursor: "help",
            border: `1px solid ${a.color}33`,
          }}>{a.label}</span>
        ))}
      </div>

      {selectedServer.status === "connected" ? (
        <>
          <JsonSchemaForm
            schema={selectedTool.inputSchema}
            initialValues={formPrefill}
            onSubmit={onRunTool}
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

          {/* Save dialog */}
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
                    if (e.key === "Enter" && saveTitle.trim() && lastRunParams) {
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
                      if (!saveTitle.trim() || !lastRunParams) return;
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
  );
};
