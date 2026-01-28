import type { Server } from "../types/server";

interface ServerCardProps {
  server: Server;
  onStart: () => void;
  onViewDetails: () => void;
  isStarting: boolean;
}

export default function ServerCard({
  server,
  onStart,
  onViewDetails,
  isStarting,
}: ServerCardProps) {
  const isStopped =
    server.status?.state === "stopped" ||
    server.status?.state === "failed" ||
    !server.status;

  const toolCount = server.tools?.length || 0;
  const lastUpdated = server.updated_at
    ? new Date(server.updated_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null;

  return (
    <div className="server-card">
      <div className="server-card-header">
        <h3>{server.name}</h3>
        <span className={`status ${server.status?.state || "stopped"}`}>
          {server.status?.state || "stopped"}
        </span>
      </div>
      <p className="server-description">
        {server.description || "No description available"}
      </p>

      {/* Server metadata */}
      <div className="server-card-metadata">
        {toolCount > 0 && (
          <span className="metadata-badge">
            🔧 {toolCount} {toolCount === 1 ? 'tool' : 'tools'}
          </span>
        )}
        {lastUpdated && (
          <span className="metadata-timestamp">
            Updated {lastUpdated}
          </span>
        )}
      </div>

      <div className="server-card-actions">
        {isStopped && (
          <button onClick={onStart} disabled={isStarting} className="start-btn">
            {isStarting ? "Starting..." : "Start"}
          </button>
        )}
        <button onClick={onViewDetails} className="details-btn">
          Details
        </button>
      </div>
    </div>
  );
}