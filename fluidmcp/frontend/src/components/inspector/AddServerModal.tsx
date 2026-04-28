import React, { useState, useCallback } from "react";
import apiClient, { BASE_URL } from "@/services/api";

export interface OAuthToken {
  access_token: string;
  refresh_token?: string;
  expires_at?: number;
  token_url: string;
  client_id: string;
}

interface AddServerModalProps {
  connecting: boolean;
  url: string;
  setUrl: (v: string) => void;
  command: string;
  setCommand: (v: string) => void;
  transport: string;
  setTransport: (v: string) => void;
  authType: "none" | "bearer" | "header" | "oauth";
  setAuthType: (v: "none" | "bearer" | "header" | "oauth") => void;
  token: string;
  setToken: (v: string) => void;
  headerKey: string;
  setHeaderKey: (v: string) => void;
  headerValue: string;
  setHeaderValue: (v: string) => void;
  customName: string;
  setCustomName: (v: string) => void;
  envVars: { key: string; value: string }[];
  setEnvVars: React.Dispatch<React.SetStateAction<{ key: string; value: string }[]>>;
  recentUrls: string[];
  oauthToken: OAuthToken | null;
  setOAuthToken: (t: OAuthToken | null) => void;
  onClose: () => void;
  onConnect: () => void;
}

export const AddServerModal: React.FC<AddServerModalProps> = ({
  connecting,
  url, setUrl,
  command, setCommand,
  transport, setTransport,
  authType, setAuthType,
  token, setToken,
  headerKey, setHeaderKey,
  headerValue, setHeaderValue,
  customName, setCustomName,
  envVars, setEnvVars,
  recentUrls,
  oauthToken, setOAuthToken,
  onClose,
  onConnect,
}) => {
  const [oauthAuthUrl, setOauthAuthUrl] = useState("");
  const [oauthTokenUrl, setOauthTokenUrl] = useState("");
  const [oauthClientId, setOauthClientId] = useState("");
  const [oauthScopes, setOauthScopes] = useState("");
  const [oauthAuthorizing, setOauthAuthorizing] = useState(false);
  const [oauthError, setOauthError] = useState<string | null>(null);

  const redirectUri = `${BASE_URL}/api/inspector/oauth/callback`;

  const handleAuthorize = useCallback(async () => {
    if (!oauthAuthUrl || !oauthTokenUrl || !oauthClientId) {
      setOauthError("Authorization URL, Token URL, and Client ID are required.");
      return;
    }
    setOauthError(null);
    setOauthAuthorizing(true);
    setOAuthToken(null);

    try {
      const { redirect_url, state } = await apiClient.startOAuthFlow({
        authorization_url: oauthAuthUrl,
        token_url: oauthTokenUrl,
        client_id: oauthClientId,
        redirect_uri: redirectUri,
        scopes: oauthScopes,
      });

      const popup = window.open(redirect_url, "oauth_popup", "width=520,height=640,resizable=yes");
      if (!popup) {
        setOauthError("Popup blocked. Please allow popups for this site.");
        setOauthAuthorizing(false);
        return;
      }

      // Poll backend for result with exponential backoff (1s → 2s → 4s, cap 5s).
      // popup.closed must NOT stop polling — the popup closes intentionally
      // as soon as our callback page runs window.close(). Keep polling until
      // we get a result or the hard deadline passes.
      const deadline = Date.now() + 10 * 60 * 1000;
      let popupClosedAt: number | null = null;
      let pollInterval = 1000;

      const poll = async () => {
        // Track when popup first closed so we can give a grace period
        if (popup.closed && popupClosedAt === null) {
          popupClosedAt = Date.now();
        }

        // Hard deadline
        if (Date.now() > deadline) {
          setOauthAuthorizing(false);
          setOauthError("Authorization timed out.");
          return;
        }

        // If popup has been closed for >15s with no result, user probably cancelled
        if (popupClosedAt !== null && Date.now() - popupClosedAt > 15000) {
          setOauthAuthorizing(false);
          setOauthError("Authorization cancelled or failed.");
          return;
        }

        try {
          const result = await apiClient.pollOAuthResult(state);
          if (result.status === "complete" && result.token) {
            setOAuthToken({
              access_token: result.token.access_token,
              refresh_token: result.token.refresh_token,
              expires_at: result.token.expires_at,
              token_url: oauthTokenUrl,
              client_id: oauthClientId,
            });
            setOauthAuthorizing(false);
            popup.close();
            return;
          }
        } catch {
          // transient error — keep polling
        }
        pollInterval = Math.min(pollInterval * 2, 5000);
        setTimeout(poll, pollInterval);
      };
      setTimeout(poll, pollInterval);
    } catch (e: any) {
      setOauthError(e?.message ?? "Failed to start OAuth flow.");
      setOauthAuthorizing(false);
    }
  }, [oauthAuthUrl, oauthTokenUrl, oauthClientId, oauthScopes, redirectUri, setOAuthToken]);

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "0.5rem", borderRadius: "0.4rem",
    border: "1px solid rgba(63,63,70,0.6)",
    background: "#18181b", color: "#fff", boxSizing: "border-box",
    fontSize: "0.85rem",
  };

  return (
    <div
      onClick={onClose}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#18181b", padding: "2rem", borderRadius: "0.75rem",
          width: "420px", border: "1px solid rgba(63,63,70,0.6)",
        }}
      >
        <h2 style={{ fontSize: "1.3rem", marginBottom: "1rem" }}>Connect MCP Server</h2>

        <form onSubmit={(e) => { e.preventDefault(); onConnect(); }} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)", marginBottom: "0.3rem", display: "block" }}>
              Server Name <span style={{ color: "rgba(255,255,255,0.3)" }}>(optional)</span>
            </label>
            <input
              autoFocus
              placeholder="e.g. My Weather Server"
              style={{
                width: "100%", padding: "0.6rem", borderRadius: "0.4rem",
                border: "1px solid rgba(63,63,70,0.6)",
                background: "#09090b", color: "#fff", boxSizing: "border-box",
              }}
              value={customName}
              onChange={(e) => setCustomName(e.target.value)}
            />
          </div>

          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.3rem" }}>
              <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)" }}>Transport</label>
              <span
                title="HTTP: stateless request/response. SSE: persistent connection for servers that push notifications. stdio: spawn a local MCP server by command (e.g. npx -y @modelcontextprotocol/server-filesystem /tmp)."
                style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.3)", cursor: "help", border: "1px solid rgba(255,255,255,0.2)", borderRadius: "50%", width: "14px", height: "14px", display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}
              >?</span>
            </div>
            <select
              value={transport}
              onChange={(e) => { setTransport(e.target.value); setUrl(""); setCommand(""); }}
              style={{
                width: "100%", padding: "0.6rem", borderRadius: "0.4rem",
                border: "1px solid rgba(63,63,70,0.6)",
                background: "#09090b", color: "#fff",
              }}
            >
              <option value="http">HTTP</option>
              <option value="sse">SSE</option>
              <option value="stdio">STDIO (local subprocess)</option>
            </select>
          </div>

          {transport === "stdio" ? (
            <div>
              <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)", marginBottom: "0.3rem", display: "block" }}>
                Command
              </label>
              <input
                placeholder="npx -y @modelcontextprotocol/server-filesystem /tmp"
                style={{
                  width: "100%", padding: "0.6rem", borderRadius: "0.4rem",
                  border: "1px solid rgba(63,63,70,0.6)",
                  background: "#09090b", color: "#fff", boxSizing: "border-box",
                  fontFamily: "ui-monospace, monospace", fontSize: "0.8rem",
                }}
                value={command}
                onChange={(e) => setCommand(e.target.value)}
              />
              <p style={{ fontSize: "0.72rem", color: "rgba(255,255,255,0.3)", marginTop: "0.3rem", marginBottom: 0 }}>
                The server will be spawned as a subprocess on the FluidMCP backend machine.
              </p>

              {/* Environment Variables */}
              <div style={{ marginTop: "0.9rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                  <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)" }}>
                    Environment Variables <span style={{ color: "rgba(255,255,255,0.25)", fontWeight: 400 }}>(optional)</span>
                    <span
                      title="Env vars are passed to the subprocess at spawn time and cannot be changed while the server is running. Reconnect to update them."
                      style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.3)", cursor: "help", border: "1px solid rgba(255,255,255,0.2)", borderRadius: "50%", width: "14px", height: "14px", display: "inline-flex", alignItems: "center", justifyContent: "center", marginLeft: "0.3rem", flexShrink: 0 }}
                    >?</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => setEnvVars(prev => [...prev, { key: "", value: "" }])}
                    style={{
                      fontSize: "0.72rem", padding: "0.2rem 0.55rem",
                      borderRadius: "0.3rem", border: "1px solid rgba(99,102,241,0.4)",
                      background: "rgba(99,102,241,0.1)", color: "rgba(200,200,255,0.8)",
                      cursor: "pointer",
                    }}
                  >+ Add</button>
                </div>
                {envVars.map((ev, i) => (
                  <div key={i} style={{ display: "flex", gap: "0.4rem", marginBottom: "0.35rem", alignItems: "center" }}>
                    <input
                      placeholder="KEY"
                      value={ev.key}
                      onChange={(e) => setEnvVars(prev => prev.map((x, j) => j === i ? { ...x, key: e.target.value } : x))}
                      style={{
                        flex: "0 0 38%", padding: "0.4rem 0.5rem", borderRadius: "0.3rem",
                        border: "1px solid rgba(63,63,70,0.6)", background: "#09090b",
                        color: "#fff", fontSize: "0.78rem", fontFamily: "ui-monospace, monospace",
                      }}
                    />
                    <input
                      placeholder="value"
                      value={ev.value}
                      onChange={(e) => setEnvVars(prev => prev.map((x, j) => j === i ? { ...x, value: e.target.value } : x))}
                      style={{
                        flex: 1, padding: "0.4rem 0.5rem", borderRadius: "0.3rem",
                        border: "1px solid rgba(63,63,70,0.6)", background: "#09090b",
                        color: "#fff", fontSize: "0.78rem",
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setEnvVars(prev => prev.filter((_, j) => j !== i))}
                      style={{
                        background: "transparent", border: "none", color: "rgba(255,100,100,0.6)",
                        cursor: "pointer", fontSize: "1rem", lineHeight: 1, padding: "0 0.2rem",
                      }}
                    >×</button>
                  </div>
                ))}
                {envVars.length === 0 && (
                  <p style={{ fontSize: "0.71rem", color: "rgba(255,255,255,0.2)", marginTop: "0.2rem", marginBottom: 0 }}>
                    e.g. API_KEY, OPENAI_API_KEY, …
                  </p>
                )}
              </div>
            </div>
          ) : (
            <div>
              <input
                placeholder="Server URL"
                style={{
                  width: "100%", padding: "0.6rem", borderRadius: "0.4rem",
                  border: "1px solid rgba(63,63,70,0.6)",
                  background: "#09090b", color: "#fff", boxSizing: "border-box",
                }}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              {recentUrls.length > 0 && (
                <div style={{ marginTop: "0.4rem", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                  <span style={{ fontSize: "0.72rem", color: "rgba(255,255,255,0.35)", alignSelf: "center" }}>Recent:</span>
                  {recentUrls.map(u => (
                    <button
                      key={u}
                      type="button"
                      onClick={() => setUrl(u)}
                      style={{
                        fontSize: "0.72rem", padding: "0.15rem 0.5rem",
                        borderRadius: "999px", border: "1px solid rgba(99,102,241,0.35)",
                        background: url === u ? "rgba(99,102,241,0.2)" : "rgba(99,102,241,0.07)",
                        color: "rgba(200,200,255,0.75)", cursor: "pointer",
                        maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}
                      title={u}
                    >
                      {u.replace(/^https?:\/\//, "").slice(0, 35)}{u.replace(/^https?:\/\//, "").length > 35 ? "…" : ""}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Auth — not shown for stdio */}
          {transport !== "stdio" && (
            <>
              <div style={{ marginTop: "1rem" }}>
                <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)" }}>Auth Type</label>
                <select
                  value={authType}
                  onChange={(e) => setAuthType(e.target.value as "none" | "bearer" | "header" | "oauth")}
                  style={{
                    width: "100%", marginTop: "0.3rem", padding: "0.5rem",
                    borderRadius: "0.4rem", background: "#18181b", color: "#fff",
                    border: "1px solid rgba(63,63,70,0.6)"
                  }}
                >
                  <option value="none">None</option>
                  <option value="bearer">Bearer Token</option>
                  <option value="header">Header Token</option>
                  <option value="oauth">OAuth 2.0 (PKCE)</option>
                </select>
              </div>

              {authType === "oauth" && (
                <div style={{ marginTop: "0.8rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                  <div>
                    <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.6)", display: "block", marginBottom: "0.25rem" }}>Authorization URL</label>
                    <input
                      value={oauthAuthUrl}
                      onChange={(e) => setOauthAuthUrl(e.target.value)}
                      placeholder="https://provider.example.com/oauth/authorize"
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.6)", display: "block", marginBottom: "0.25rem" }}>Token URL</label>
                    <input
                      value={oauthTokenUrl}
                      onChange={(e) => setOauthTokenUrl(e.target.value)}
                      placeholder="https://provider.example.com/oauth/token"
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.6)", display: "block", marginBottom: "0.25rem" }}>Client ID</label>
                    <input
                      value={oauthClientId}
                      onChange={(e) => setOauthClientId(e.target.value)}
                      placeholder="your-client-id"
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.6)", display: "block", marginBottom: "0.25rem" }}>
                      Scopes <span style={{ color: "rgba(255,255,255,0.3)" }}>(space-separated, optional)</span>
                    </label>
                    <input
                      value={oauthScopes}
                      onChange={(e) => setOauthScopes(e.target.value)}
                      placeholder="read write"
                      style={inputStyle}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleAuthorize}
                    disabled={oauthAuthorizing}
                    style={{
                      padding: "0.5rem 1rem", borderRadius: "0.4rem", fontWeight: 600,
                      background: oauthToken ? "rgba(16,185,129,0.15)" : "rgba(99,102,241,0.15)",
                      border: `1px solid ${oauthToken ? "rgba(16,185,129,0.4)" : "rgba(99,102,241,0.4)"}`,
                      color: oauthToken ? "#10b981" : "rgba(165,180,252,0.9)",
                      cursor: oauthAuthorizing ? "default" : "pointer",
                      fontSize: "0.85rem",
                    }}
                  >
                    {oauthAuthorizing ? "Waiting for authorization…" : oauthToken ? "✓ Authorized — re-authorize" : "Authorize"}
                  </button>
                  {oauthError && (
                    <p style={{ margin: 0, fontSize: "0.75rem", color: "#ef4444" }}>{oauthError}</p>
                  )}
                  {oauthToken && (
                    <p style={{ margin: 0, fontSize: "0.72rem", color: "rgba(16,185,129,0.8)" }}>
                      Token obtained
                      {oauthToken.expires_at ? ` · expires ${new Date(oauthToken.expires_at * 1000).toLocaleTimeString()}` : ""}
                    </p>
                  )}
                </div>
              )}

              {authType === "bearer" && (
                <div style={{ marginTop: "0.8rem" }}>
                  <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)" }}>Token</label>
                  <input
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="Enter bearer token"
                    style={{
                      width: "100%", marginTop: "0.3rem", padding: "0.5rem",
                      borderRadius: "0.4rem", background: "#18181b", color: "#fff",
                      border: "1px solid rgba(63,63,70,0.6)"
                    }}
                  />
                </div>
              )}

              {authType === "header" && (
                <div style={{ marginTop: "0.8rem" }}>
                  <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)" }}>Header Key</label>
                  <input
                    value={headerKey}
                    onChange={(e) => setHeaderKey(e.target.value)}
                    placeholder="X-Api-Key"
                    style={{
                      width: "100%", marginTop: "0.3rem", padding: "0.5rem",
                      borderRadius: "0.4rem", background: "#18181b", color: "#fff",
                      border: "1px solid rgba(63,63,70,0.6)"
                    }}
                  />
                  <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)", marginTop: "0.5rem", display: "block" }}>
                    Header Value
                  </label>
                  <input
                    type="password"
                    value={headerValue}
                    onChange={(e) => setHeaderValue(e.target.value)}
                    placeholder="Enter token"
                    style={{
                      width: "100%", marginTop: "0.3rem", padding: "0.5rem",
                      borderRadius: "0.4rem", background: "#18181b", color: "#fff",
                      border: "1px solid rgba(63,63,70,0.6)"
                    }}
                  />
                </div>
              )}
            </>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                background: "transparent", border: "1px solid rgba(63,63,70,0.6)",
                padding: "0.5rem 1rem", borderRadius: "0.4rem", color: "#fff",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={connecting}
              style={{
                background: "#fff", color: "#000",
                padding: "0.5rem 1rem", borderRadius: "0.4rem", fontWeight: "600",
              }}
            >
              {connecting ? "Connecting..." : "Connect"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
