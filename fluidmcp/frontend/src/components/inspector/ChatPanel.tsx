import React, { useState, useEffect } from "react";
import { type ChatMessage, type ExecutionRun, type DisplayGroup, groupMessages } from "./chat-types";
import { JsonResultView } from "@/components/result/JsonResultView";
import { McpContentView } from "@/components/result/McpContentView";
import { WidgetSandbox } from "@/components/WidgetSandbox";

// ── Animated thinking indicator ──────────────────────────────────────────────
function ThinkingDots() {
  return (
    <span style={{ fontStyle: "italic", color: "rgba(255,255,255,0.4)", fontSize: "0.72rem" }}>
      Thinking
      <span style={{ display: "inline-flex", gap: "1px" }}>
        {[0, 1, 2].map(i => (
          <span key={i} style={{ animation: `thinking-blink 1.4s ease-in-out ${i * 0.2}s infinite` }}>.</span>
        ))}
      </span>
    </span>
  );
}

// ── Compact collapsible result bubble ────────────────────────────────────────
function ChatResultBubble({ result, initialView = "formatted", hideTabSwitcher = false }: { result: unknown; initialView?: "formatted" | "raw"; hideTabSwitcher?: boolean }) {
  const [expanded, setExpanded] = useState(true);
  const [viewMode, setViewMode] = useState<"formatted" | "raw">(initialView);
  useEffect(() => { setViewMode(initialView); }, [initialView]);
  const isMcp = typeof result === "object" && result !== null &&
    "content" in result && Array.isArray((result as any).content);
  const isMcpArray = Array.isArray(result) && result.length > 0 &&
    (result as any[]).every((i: any) => typeof i === "object" && i !== null && "type" in i);
  const preview = (() => {
    if (isMcp) {
      const texts = ((result as any).content || []).filter((c: any) => c.type === "text" && c.text);
      if (texts.length > 0) return String(texts[0].text).slice(0, 80);
      return `[${(result as any).content?.length || 0} items]`;
    }
    if (isMcpArray) {
      const texts = (result as any[]).filter((c: any) => c.type === "text" && c.text);
      if (texts.length > 0) return String(texts[0].text).slice(0, 80);
      return `[${(result as any[]).length} items]`;
    }
    if (typeof result === "object" && result !== null) return `{${Object.keys(result as object).length} keys}`;
    return String(result).slice(0, 60);
  })();

  const tabStyle = (active: boolean) => ({
    padding: "0.2rem 0.5rem", borderRadius: "0.25rem", border: "none",
    fontSize: "0.75rem", fontWeight: 500 as const, cursor: "pointer",
    background: active ? "#fff" : "transparent",
    color: active ? "#000" : "rgba(255,255,255,0.6)"
  });

  return (
    <div style={{ fontSize: "0.8rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <button
          onClick={() => setExpanded(v => !v)}
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: "#22c55e", fontWeight: 600, padding: "0.25rem 0",
            fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.3rem"
          }}
        >
          {expanded ? "▼" : "▶"} Result:{!expanded && <span style={{ color: "rgba(255,255,255,0.6)", fontWeight: 400, marginLeft: "0.3rem" }}>{preview}</span>}
        </button>
        {expanded && !hideTabSwitcher && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <div style={{ display: "flex", background: "rgba(0,0,0,0.3)", borderRadius: "0.25rem", padding: "0.15rem", gap: "0.15rem" }}>
              <button style={tabStyle(viewMode === "formatted")} onClick={() => setViewMode("formatted")}>Formatted</button>
              <button style={tabStyle(viewMode === "raw")} onClick={() => setViewMode("raw")}>Raw JSON</button>
            </div>
            <button
              onClick={() => navigator.clipboard.writeText(JSON.stringify(result, null, 2))}
              style={{ ...tabStyle(false), border: "1px solid rgba(63,63,70,0.5)", borderRadius: "0.25rem" }}
              title="Copy to clipboard"
            >
              Copy
            </button>
          </div>
        )}
      </div>
      {expanded && (
        <div style={{
          background: "rgba(0,0,0,0.3)",
          border: "1px solid rgba(63,63,70,0.5)",
          borderRadius: "0.5rem",
          padding: "0.75rem",
          marginTop: "0.25rem",
          width: "100%", boxSizing: "border-box",
          maxHeight: "350px",
          overflowY: "auto",
        }}>
          {viewMode === "raw"
            ? <pre style={{ margin: 0, fontSize: "0.75rem", color: "#e5e7eb", whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "ui-monospace, monospace", width: "100%", boxSizing: "border-box" as const }}>{JSON.stringify(result, null, 2)}</pre>
            : <div style={{ minWidth: 0, width: "100%", overflow: "hidden" }}>
                {(isMcp || isMcpArray)
                  ? <McpContentView content={isMcpArray ? result as any : (result as any).content} />
                  : <JsonResultView data={result} />
                }
              </div>
          }
        </div>
      )}
    </div>
  );
}

// ── Timeline block for one agent turn ────────────────────────────────────────
export function ExecutionRunBlock({ steps, run }: { steps: ChatMessage[]; run?: ExecutionRun }) {
  const [collapsed, setCollapsed] = useState(false);
  const thinking  = steps.find(s => s.type === "thinking");
  const toolCall  = steps.find(s => s.type === "tool_call");
  const toolResult = steps.find(s => s.type === "tool_result");
  const errorStep = steps.find(s => s.type === "error");
  const isActive  = !toolResult && !errorStep;

  const totalMs    = run?.endTime ? run.endTime - run.startTime : null;
  const thinkingMs = (toolCall?.perfMark && thinking?.perfMark)
    ? Math.round(toolCall.perfMark - thinking.perfMark) : null;
  const toolMs     = (toolResult?.perfMark && toolCall?.perfMark)
    ? Math.round(toolResult.perfMark - toolCall.perfMark) : null;

  const dot = (color: string) => (
    <div style={{ width: "7px", height: "7px", borderRadius: "50%", background: color, marginTop: "4px", flexShrink: 0 }} />
  );

  return (
    <div style={{ width: "100%", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "10px" }}>
      <div
        onClick={() => setCollapsed(v => !v)}
        style={{
          display: "flex", alignItems: "center", gap: "0.5rem",
          padding: "0.45rem 0.75rem",
          background: "rgba(255,255,255,0.04)", cursor: "pointer",
          borderBottom: collapsed ? "none" : "1px solid rgba(63,63,70,0.25)",
        }}
      >
        <span style={{ fontSize: "0.7rem", opacity: 0.45 }}>{collapsed ? "▶" : "▼"}</span>
        <span style={{ fontSize: "0.8rem", fontWeight: 600 }}>
          {toolCall ? `🔧 ${toolCall.toolName}` : errorStep ? "❌ Error" : "🤖 Thinking"}
        </span>
        {isActive && <ThinkingDots />}
        {totalMs !== null && (
          <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "rgba(99,102,241,0.7)", fontFamily: "monospace" }}>
            {totalMs}ms
          </span>
        )}
      </div>

      {!collapsed && (
        <div style={{ padding: "0.6rem 0.75rem", display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {thinking && (
            <div style={{ display: "flex", gap: "0.6rem" }}>
              {dot("#3b82f6")}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "0.72rem", color: "#60a5fa", fontWeight: 600, display: "flex", gap: "0.4rem", alignItems: "center" }}>
                  Thinking
                  {thinkingMs !== null && <span style={{ fontWeight: 400, opacity: 0.65 }}>{thinkingMs}ms</span>}
                  {isActive && <ThinkingDots />}
                </div>
                <div style={{ fontSize: "0.73rem", opacity: 0.6, fontStyle: "italic", marginTop: "0.15rem" }}>
                  {thinking.content}
                </div>
              </div>
            </div>
          )}

          {toolCall && (
            <div style={{ display: "flex", gap: "0.6rem" }}>
              {dot("#f59e0b")}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "0.72rem", color: "#fbbf24", fontWeight: 600 }}>
                  Tool: {toolCall.toolName}
                </div>
                {toolCall.params && Object.keys(toolCall.params).length > 0 ? (
                  <div style={{ marginTop: "0.25rem", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                    {Object.entries(toolCall.params).map(([k, v]) => (
                      <div key={k} style={{ display: "flex", gap: "0.4rem", alignItems: "baseline", fontSize: "0.7rem" }}>
                        <span style={{ color: "#fbbf24", opacity: 0.7, fontFamily: "monospace", flexShrink: 0 }}>{k}</span>
                        <span style={{ color: "rgba(255,255,255,0.2)", flexShrink: 0 }}>→</span>
                        <span style={{
                          background: "rgba(0,0,0,0.25)", borderRadius: "4px",
                          padding: "0.05rem 0.35rem", color: "#e5e7eb", fontFamily: "monospace",
                          wordBreak: "break-all",
                        }}>
                          {typeof v === "string" ? v : JSON.stringify(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.3)", fontStyle: "italic" }}>no params</span>
                )}
              </div>
            </div>
          )}

          {toolResult && (
            <div style={{ display: "flex", gap: "0.6rem" }}>
              {dot("#22c55e")}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "0.72rem", color: "#4ade80", fontWeight: 600, display: "flex", gap: "0.4rem", alignItems: "center" }}>
                  Result
                  {toolMs !== null && <span style={{ fontWeight: 400, opacity: 0.65 }}>{toolMs}ms</span>}
                </div>
                <div style={{ marginTop: "0.2rem" }}>
                  <ChatResultBubble result={toolResult.result} />
                </div>
              </div>
            </div>
          )}

          {errorStep && (
            <div style={{ display: "flex", gap: "0.6rem" }}>
              {dot("#ef4444")}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "0.72rem", color: "#fca5a5", fontWeight: 600 }}>Error</div>
                <div style={{ fontSize: "0.73rem", color: "#fca5a5", marginTop: "0.15rem" }}>
                  {errorStep.content}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface MCPServer {
  session_id: string | null;
  status: string;
  tools: any[];
}

interface ChatPanelProps {
  selectedServer: MCPServer;
  selectedServerId: string;
  chatHistory: ChatMessage[];
  executionHistory: ExecutionRun[];
  chatInput: string;
  chatLoading: boolean;
  systemPrompt: string;
  systemPromptDraft: string;
  systemPromptOpen: boolean;
  chatRef: React.RefObject<HTMLDivElement | null>;
  chatBottomRef: React.RefObject<HTMLDivElement | null>;
  setChatInput: (v: string) => void;
  setChatHistoryByServer: React.Dispatch<React.SetStateAction<Record<string, ChatMessage[]>>>;
  setSystemPrompt: (v: string) => void;
  setSystemPromptDraft: (v: string) => void;
  setSystemPromptOpen: (v: boolean) => void;
  onSendMessage: () => void;
  onSendMessageWithText: (text: string) => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  selectedServer,
  selectedServerId,
  chatHistory,
  executionHistory,
  chatInput,
  chatLoading,
  systemPrompt,
  systemPromptDraft,
  systemPromptOpen,
  chatRef,
  chatBottomRef,
  setChatInput,
  setChatHistoryByServer,
  setSystemPrompt,
  setSystemPromptDraft,
  setSystemPromptOpen,
  onSendMessage,
  onSendMessageWithText,
}) => {
  const groups: DisplayGroup[] = groupMessages(chatHistory, executionHistory);

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
      {selectedServer.status === "connected" ? (
        <>
          {/* Chat History */}
          <div
            ref={chatRef}
            style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "0.5rem 0.5rem 2rem 0.25rem" }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {groups.map((group, _idx, _arr) => {
                const isLast = _idx === _arr.length - 1;
                if (group.kind === "run") {
                  const toolResult = group.steps.find(s => s.type === "tool_result");
                  const toolCall = group.steps.find(s => s.type === "tool_call");
                  const sessionId = selectedServer.session_id ?? undefined;
                  const hasWidget = !!(toolResult?.resourceUri && sessionId && toolCall);
                  return (
                    <React.Fragment key={group.runId}>
                      <ExecutionRunBlock steps={group.steps} run={group.run} />
                      {hasWidget && (
                        <div style={{
                          width: "100%",
                          border: "1px solid rgba(99,102,241,0.3)",
                          borderRadius: "10px",
                          overflow: "hidden",
                          background: "rgba(99,102,241,0.04)",
                        }}>
                          <WidgetSandbox
                            sessionId={sessionId!}
                            resourceUri={toolResult!.resourceUri!}
                            toolInput={toolCall!.params || {}}
                            toolResult={toolResult!.result}
                          />
                        </div>
                      )}
                      {isLast && <div ref={chatBottomRef} />}
                    </React.Fragment>
                  );
                }

                const msg = group.msg;

                if (msg.type === "user") {
                  return (
                    <React.Fragment key={msg.id}>
                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <div style={{
                          background: "rgba(37,99,235,0.85)",
                          border: "1px solid rgba(59,130,246,0.4)",
                          color: "#fff",
                          padding: "0.55rem 0.85rem",
                          borderRadius: "16px 16px 4px 16px",
                          maxWidth: "75%", fontSize: "0.875rem", lineHeight: 1.5,
                        }}>
                          {msg.content}
                        </div>
                      </div>
                      {isLast && <div ref={chatBottomRef} />}
                    </React.Fragment>
                  );
                }

                if (msg.type === "assistant") {
                  return (
                    <React.Fragment key={msg.id}>
                      <div style={{ display: "flex", justifyContent: "flex-start", gap: "0.5rem", alignItems: "flex-start" }}>
                        <div style={{
                          width: "22px", height: "22px", borderRadius: "50%", flexShrink: 0, marginTop: "2px",
                          background: "rgba(99,102,241,0.2)", border: "1px solid rgba(99,102,241,0.4)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: "0.65rem",
                        }}>🤖</div>
                        <div style={{
                          background: "rgba(39,39,42,0.8)",
                          border: "1px solid rgba(63,63,70,0.6)",
                          padding: "0.55rem 0.85rem",
                          borderRadius: "4px 16px 16px 16px",
                          maxWidth: "75%", fontSize: "0.875rem", lineHeight: 1.5,
                          color: "rgba(255,255,255,0.85)",
                        }}>
                          {msg.content}
                        </div>
                      </div>
                      {isLast && <div ref={chatBottomRef} />}
                    </React.Fragment>
                  );
                }

                return null;
              })}
            </div>
          </div>

          {/* Starter prompt chips */}
          {!chatHistory.some(m => m.type === "user") && (selectedServer.tools?.length ?? 0) > 0 && (
            <div style={{ flexShrink: 0, padding: "0.5rem 0.25rem", display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
              {[
                ...selectedServer.tools.slice(0, 3).map((t: any) => `Try ${t.name} with example data`),
                selectedServer.tools.length > 1 ? `Run ${selectedServer.tools[0].name}` : null,
              ].filter(Boolean).slice(0, 4).map((prompt: any) => (
                <button
                  key={prompt}
                  onClick={() => onSendMessageWithText(prompt)}
                  style={{
                    fontSize: "0.72rem", padding: "0.3rem 0.7rem", borderRadius: "999px",
                    background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.25)",
                    color: "rgba(165,180,252,0.85)", cursor: "pointer",
                    transition: "background 0.15s",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = "rgba(99,102,241,0.18)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "rgba(99,102,241,0.08)")}
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}

          {/* Chat Input area */}
          <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "0.35rem", paddingTop: "0.5rem", borderTop: "1px solid rgba(63,63,70,0.3)" }}>
            {/* Toolbar row */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", paddingTop: "0.3rem" }}>
              <span style={{
                fontSize: "0.65rem", padding: "0.15rem 0.5rem", borderRadius: "999px",
                background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.3)",
                color: "rgba(165,180,252,0.9)", fontFamily: "monospace", flexShrink: 0,
              }}>
                Groq · llama-3.1-8b
              </span>
              <button
                onClick={() => { setSystemPromptDraft(systemPrompt); setSystemPromptOpen(true); }}
                title="System prompt"
                style={{
                  fontSize: "0.65rem", padding: "0.15rem 0.5rem", borderRadius: "999px",
                  background: systemPrompt ? "rgba(99,102,241,0.15)" : "transparent",
                  border: systemPrompt ? "1px solid rgba(99,102,241,0.4)" : "1px solid rgba(63,63,70,0.5)",
                  color: systemPrompt ? "rgba(165,180,252,0.9)" : "rgba(255,255,255,0.35)",
                  cursor: "pointer", flexShrink: 0,
                }}
              >
                ⚙ {systemPrompt ? "Prompt set" : "System prompt"}
              </button>
              <div style={{ flex: 1 }} />
              {chatHistory.length > 1 && (
                <button
                  onClick={() => setChatHistoryByServer(prev => ({ ...prev, [selectedServerId]: [] }))}
                  style={{ fontSize: "0.65rem", background: "none", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "4px", color: "rgba(255,255,255,0.35)", cursor: "pointer", padding: "0.1rem 0.4rem", flexShrink: 0 }}
                >
                  Clear Chat
                </button>
              )}
            </div>

            {/* System prompt dialog */}
            {systemPromptOpen && (
              <div style={{
                position: "fixed", inset: 0, zIndex: 50,
                background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center",
              }}
                onClick={(e) => { if (e.target === e.currentTarget) setSystemPromptOpen(false); }}
              >
                <div style={{
                  background: "#18181b", border: "1px solid rgba(63,63,70,0.7)",
                  borderRadius: "12px", padding: "1.25rem", width: "420px", maxWidth: "90vw",
                  display: "flex", flexDirection: "column", gap: "0.75rem",
                }}>
                  <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "rgba(255,255,255,0.85)" }}>System Prompt</div>
                  <textarea
                    value={systemPromptDraft}
                    onChange={e => setSystemPromptDraft(e.target.value)}
                    placeholder="You are a helpful assistant with access to MCP tools."
                    rows={5}
                    style={{
                      background: "#09090b", border: "1px solid rgba(63,63,70,0.6)",
                      borderRadius: "6px", padding: "0.5rem 0.6rem",
                      color: "#fff", fontSize: "0.8rem", resize: "vertical",
                      fontFamily: "inherit", lineHeight: 1.5,
                    }}
                  />
                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                    <button
                      onClick={() => setSystemPromptOpen(false)}
                      style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem", borderRadius: "6px", background: "transparent", border: "1px solid rgba(63,63,70,0.5)", color: "rgba(255,255,255,0.5)", cursor: "pointer" }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => { setSystemPrompt(systemPromptDraft); setSystemPromptOpen(false); }}
                      style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem", borderRadius: "6px", background: "rgba(99,102,241,0.8)", border: "none", color: "#fff", cursor: "pointer", fontWeight: 600 }}
                    >
                      Save
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Message input row */}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <input
                value={chatInput}
                disabled={chatLoading}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask something..."
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && chatInput.trim()) {
                    e.preventDefault();
                    onSendMessage();
                  }
                }}
                style={{
                  flex: 1, minWidth: 0, padding: "0.5rem 0.75rem",
                  borderRadius: "0.5rem", border: "1px solid rgba(63,63,70,0.6)",
                  background: "rgba(24,24,27,0.8)", color: "#fff", opacity: chatLoading ? 0.6 : 1,
                  fontSize: "0.875rem",
                }}
              />
              <button
                onClick={() => { if (chatInput.trim()) onSendMessage(); }}
                disabled={chatLoading || !chatInput.trim()}
                style={{
                  padding: "0.5rem 1rem", borderRadius: "0.5rem",
                  background: "rgba(99,102,241,0.9)", color: "#fff", fontWeight: "600", flexShrink: 0,
                  border: "none",
                  opacity: chatLoading || !chatInput.trim() ? 0.45 : 1,
                  cursor: chatLoading || !chatInput.trim() ? "not-allowed" : "pointer",
                  fontSize: "0.875rem",
                }}
              >
                {chatLoading ? <ThinkingDots /> : "Send"}
              </button>
            </div>
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
  );
};
