import React from "react";
import { apiClient } from "@/services/api";

interface MCPResource {
  uri: string;
  name?: string;
  mimeType?: string;
  description?: string;
  isTemplate?: boolean;
}

interface ResourcesPanelProps {
  resources: MCPResource[];
  resourcesLoading: boolean;
  selectedResourceUri: string | null;
  setSelectedResourceUri: (uri: string | null) => void;
  resourceContent: { text?: string; blob?: string; mimeType?: string } | null;
  setResourceContent: (c: { text?: string; blob?: string; mimeType?: string } | null) => void;
  resourceContentLoading: boolean;
  setResourceContentLoading: (v: boolean) => void;
  templateParams: Record<string, string>;
  setTemplateParams: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  sessionId: string;
  selectedServerId: string;
  onRefresh: () => void;
}

export const ResourcesPanel: React.FC<ResourcesPanelProps> = ({
  resources,
  resourcesLoading,
  selectedResourceUri,
  setSelectedResourceUri,
  resourceContent,
  setResourceContent,
  resourceContentLoading,
  setResourceContentLoading,
  templateParams,
  setTemplateParams,
  sessionId,
  onRefresh,
}) => {
  const loadResource = async (resource: MCPResource, uri: string) => {
    setSelectedResourceUri(resource.uri);
    setResourceContent(null);
    setResourceContentLoading(true);
    try {
      const res = await apiClient.readInspectorResource(sessionId, uri);
      const first = res?.contents?.[0];
      setResourceContent({
        text: first?.text ?? first?.content ?? res?.text ?? "",
        blob: first?.blob,
        mimeType: first?.mimeType ?? resource.mimeType ?? "text/plain",
      });
    } catch {
      setResourceContent({ text: "Failed to load resource.", mimeType: "text/plain" });
    } finally {
      setResourceContentLoading(false);
    }
  };

  return (
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
            onClick={onRefresh}
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
              const templateVars = r.isTemplate
                ? (r.uri.match(/\{([^}]+)\}/g) ?? []).map(v => v.slice(1, -1))
                : [];
              return (
                <div
                  key={r.uri}
                  onClick={() => {
                    if (r.isTemplate) {
                      setSelectedResourceUri(r.uri);
                      setResourceContent(null);
                      setTemplateParams({});
                    } else {
                      if (isSelected) return;
                      loadResource(r, r.uri);
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
                          loadResource(r, uri);
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
  );
};
