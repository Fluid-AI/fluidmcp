import React from "react";
import { apiClient } from "@/services/api";

interface PromptsPanel {
  prompts: any[];
  promptsLoading: boolean;
  selectedPrompt: any | null;
  setSelectedPrompt: (p: any | null) => void;
  promptArgs: Record<string, string>;
  setPromptArgs: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  promptResult: any;
  setPromptResult: (r: any) => void;
  promptResultLoading: boolean;
  setPromptResultLoading: (v: boolean) => void;
  sessionId: string;
  selectedServerId: string;
  onRefresh: () => void;
}

export const PromptsPanel: React.FC<PromptsPanel> = ({
  prompts,
  promptsLoading,
  selectedPrompt,
  setSelectedPrompt,
  promptArgs,
  setPromptArgs,
  promptResult,
  setPromptResult,
  promptResultLoading,
  setPromptResultLoading,
  sessionId,
  onRefresh,
}) => {
  return (
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
            onClick={onRefresh}
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
                  onClick={() => { setSelectedPrompt(p); setPromptArgs({}); setPromptResult(null); }}
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
            <div style={{
              padding: "0.5rem 0.75rem", borderBottom: "1px solid rgba(63,63,70,0.4)",
              background: "rgba(24,24,27,0.6)", flexShrink: 0,
            }}>
              <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "rgba(255,255,255,0.85)" }}>{selectedPrompt.name}</div>
              {selectedPrompt.description && (
                <div style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.4)", marginTop: "0.15rem" }}>{selectedPrompt.description}</div>
              )}
            </div>

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
                  if (!sessionId) return;
                  setPromptResultLoading(true);
                  setPromptResult(null);
                  try {
                    const res = await apiClient.getInspectorPrompt(sessionId, selectedPrompt.name, promptArgs);
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

            <div style={{ flex: 1, overflowY: "auto", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {promptResult?.error ? (
                <div style={{ fontSize: "0.75rem", color: "#fca5a5", padding: "0.5rem", background: "rgba(239,68,68,0.1)", borderRadius: "6px", border: "1px solid rgba(239,68,68,0.3)" }}>
                  Error: {promptResult.error}
                </div>
              ) : promptResult?.messages ? (
                promptResult.messages.map((msg: any, i: number) => {
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
                      padding: "0.5rem 0.75rem", borderRadius: "8px",
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
  );
};
