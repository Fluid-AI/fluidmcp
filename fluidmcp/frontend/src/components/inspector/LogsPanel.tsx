import React from "react";

interface LogEntry {
  timestamp: string;
  type: 'connect' | 'disconnect' | 'tool_call' | 'tool_result' | 'tool_error' | 'chat';
  message: string;
}

interface LogsPanelProps {
  logs: LogEntry[];
  filteredLogs: LogEntry[];
  logFilter: 'all' | 'connect' | 'tool_call' | 'tool_error' | 'chat';
  setLogFilter: (f: 'all' | 'connect' | 'tool_call' | 'tool_error' | 'chat') => void;
  logSearch: string;
  setLogSearch: (s: string) => void;
  logsRef: React.RefObject<HTMLDivElement | null>;
  selectedServerId: string | null;
  hasSession: boolean;
  logColors: Record<string, string>;
  onClear: () => void;
}

export const LogsPanel: React.FC<LogsPanelProps> = ({
  logs,
  filteredLogs,
  logFilter,
  setLogFilter,
  logSearch,
  setLogSearch,
  logsRef,
  selectedServerId,
  hasSession,
  logColors,
  onClear,
}) => {
  return (
    <div
      style={{
        border: "1px solid rgba(63,63,70,0.5)",
        borderRadius: "0.75rem",
        background: "linear-gradient(to bottom right, rgba(39,39,42,0.9), rgba(24,24,27,0.9))",
        height: "100%",
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Logs header */}
      <div style={{ padding: "0.6rem 0.75rem 0.4rem", flexShrink: 0, borderBottom: "1px solid rgba(63,63,70,0.3)" }}>
        {/* Title row */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.4rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: "600", color: "rgba(255,255,255,0.7)", fontFamily: "monospace" }}>LOGS</span>
            {logs.length > 0 && (
              <span style={{ fontSize: "0.65rem", color: "rgba(255,255,255,0.3)" }}>
                {filteredLogs.length}{logFilter !== 'all' ? `/${logs.length}` : ''}
              </span>
            )}
          </div>
          {logs.length > 0 && selectedServerId && (
            <button
              onClick={onClear}
              style={{ fontSize: "0.65rem", background: "none", border: "1px solid rgba(63,63,70,0.5)", borderRadius: "4px", color: "rgba(255,255,255,0.35)", cursor: "pointer", padding: "0.1rem 0.35rem" }}
            >
              Clear
            </button>
          )}
        </div>
        {/* Log search input */}
        <div style={{ position: "relative", marginBottom: "0.35rem" }}>
          <input
            value={logSearch}
            onChange={e => setLogSearch(e.target.value)}
            placeholder="Search logs..."
            style={{
              width: "100%", boxSizing: "border-box",
              padding: "0.2rem 1.4rem 0.2rem 1.5rem",
              fontSize: "0.68rem", borderRadius: "4px",
              border: "1px solid rgba(63,63,70,0.5)",
              background: "rgba(0,0,0,0.25)", color: "#fff",
            }}
          />
          <span style={{ position: "absolute", left: "0.4rem", top: "50%", transform: "translateY(-50%)", fontSize: "0.65rem", color: "rgba(255,255,255,0.3)", pointerEvents: "none" }}>⌕</span>
          {logSearch && (
            <span
              onClick={() => setLogSearch('')}
              style={{ position: "absolute", right: "0.4rem", top: "50%", transform: "translateY(-50%)", fontSize: "0.65rem", color: "rgba(255,255,255,0.4)", cursor: "pointer", lineHeight: 1 }}
            >✕</span>
          )}
        </div>
        {/* Filter pills */}
        <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
          {([
            { key: 'all', label: 'All', count: logs.length },
            { key: 'connect', label: 'Connect', count: logs.filter(l => l.type === 'connect').length },
            { key: 'tool_call', label: 'Tool', count: logs.filter(l => l.type === 'tool_call' || l.type === 'tool_result').length },
            { key: 'tool_error', label: 'Error', count: logs.filter(l => l.type === 'tool_error').length },
            { key: 'chat', label: 'Chat', count: logs.filter(l => l.type === 'chat').length },
          ] as const).map(pill => (
            <button
              key={pill.key}
              onClick={() => setLogFilter(pill.key)}
              style={{
                fontSize: "0.65rem", padding: "0.1rem 0.45rem",
                borderRadius: "999px", cursor: "pointer",
                border: logFilter === pill.key ? "1px solid rgba(99,102,241,0.7)" : "1px solid rgba(63,63,70,0.5)",
                background: logFilter === pill.key ? "rgba(99,102,241,0.2)" : "transparent",
                color: logFilter === pill.key ? "rgba(165,180,252,1)" : "rgba(255,255,255,0.4)",
                fontFamily: "monospace",
                transition: "all 0.1s",
              }}
            >
              {pill.label}{pill.count > 0 ? ` (${pill.count})` : ''}
            </button>
          ))}
        </div>
      </div>

      {/* Logs content */}
      <div
        ref={logsRef}
        style={{
          flex: 1,
          overflowY: "auto",
          overflowX: "hidden",
          padding: "0.5rem 0.75rem",
          fontFamily: "monospace",
          fontSize: "0.78rem",
        }}
      >
        {filteredLogs.length === 0 ? (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            height: "100%", color: "rgba(255,255,255,0.35)", fontSize: "0.8rem",
          }}>
            {hasSession ? (logFilter !== 'all' || logSearch ? "No matching logs" : "No logs yet") : "Connect to a server to see logs"}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {[...filteredLogs].reverse().map((log, i) => {
              const color = logColors[log.type] || "#9ca3af";
              return (
                <div
                  key={i}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "70px 90px 1fr",
                    gap: "0.5rem",
                    paddingBottom: "3px",
                    borderBottom: "1px solid rgba(63,63,70,0.2)",
                    borderLeft: `2px solid ${color}`,
                    paddingLeft: "0.4rem",
                    alignItems: "start",
                  }}
                >
                  <span style={{ opacity: 0.45, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>
                  <span style={{ color, fontWeight: "700", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {log.type.toUpperCase()}
                  </span>
                  <span style={{ color: "rgba(255,255,255,0.75)", wordBreak: "break-word", overflowWrap: "break-word" }}>
                    {log.message}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
