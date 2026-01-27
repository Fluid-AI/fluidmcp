import { useParams, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useServerDetails } from "../hooks/useServerDetails";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorMessage from "../components/ErrorMessage";

export default function ServerDetails() {
  const { serverId } = useParams<{ serverId: string }>();
  const navigate = useNavigate();
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const {
    serverDetails,
    tools,
    hasTools,
    isRunning,
    isStopped,
    loading,
    error,
    refetch,
    startServer,
    stopServer,
    restartServer,
  } = useServerDetails(serverId!);

  const handleStartServer = async () => {
    setActionLoading('start');
    try {
      await startServer();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to start server');
    } finally {
      setActionLoading(null);
    }
  };

  const handleStopServer = async () => {
    setActionLoading('stop');
    try {
      await stopServer();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to stop server');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRestartServer = async () => {
    setActionLoading('restart');
    try {
      await restartServer();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to restart server');
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="dashboard">
        <header className="dashboard-header">
          <button className="details-btn" onClick={() => navigate("/dashboard")}>
            ← Back to Dashboard
          </button>
        </header>
        <LoadingSpinner size="large" message="Loading server details..." />
      </div>
    );
  }

  if (error || !serverDetails) {
    return (
      <div className="dashboard">
        <header className="dashboard-header">
          <button className="details-btn" onClick={() => navigate("/dashboard")}>
            ← Back to Dashboard
          </button>
          <h1>Error Loading Server</h1>
        </header>
        <ErrorMessage
          message={error || "Server not found"}
          onRetry={refetch}
        />
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* Header with Back Button */}
      <header className="dashboard-header">
        <button className="details-btn" onClick={() => navigate("/dashboard")}>
          ← Back to Dashboard
        </button>
        <h1>{serverDetails.name}</h1>
        <span className={`status ${serverDetails.status.state || "stopped"}`}>
          {serverDetails.status.state || "stopped"}
        </span>
        <p className="subtitle">
          {serverDetails.description || "No description available"}
        </p>

        {/* Server Control Buttons */}
        <div className="server-card-actions" style={{ marginTop: '1rem' }}>
          {isStopped && (
            <button
              onClick={handleStartServer}
              disabled={actionLoading === 'start'}
              className="start-btn"
            >
              {actionLoading === 'start' ? 'Starting...' : 'Start Server'}
            </button>
          )}
          {isRunning && (
            <>
              <button
                onClick={handleStopServer}
                disabled={actionLoading === 'stop'}
                className="stop-btn"
              >
                {actionLoading === 'stop' ? 'Stopping...' : 'Stop Server'}
              </button>
              <button
                onClick={handleRestartServer}
                disabled={actionLoading === 'restart'}
                className="restart-btn"
              >
                {actionLoading === 'restart' ? 'Restarting...' : 'Restart Server'}
              </button>
            </>
          )}
        </div>
      </header>

      {/* Tools */}
      <section className="dashboard-section">
        <h2>Available tools</h2>
        <div className="active-server-container">
          {!hasTools ? (
            <div className="empty-state">
              <div className="empty-state-icon">🔧</div>
              <h3 className="empty-state-title">No tools available</h3>
              <p className="empty-state-description">
                {serverDetails.status.state !== "running"
                  ? "Start the server to discover available tools"
                  : "This server has no tools configured"}
              </p>
            </div>
          ) : (
            <div className="active-server-list">
              {tools.map((tool) => (
                <div key={tool.name} className="active-server-row">
                  <div>
                    <strong>{tool.name}</strong>
                    <p className="subtitle">{tool.description}</p>
                  </div>

                  <button
                    className="details-btn"
                    onClick={() => navigate(`/servers/${serverId}/tools/${tool.name}`)}
                  >
                    Run tool
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Server Information */}
      {serverDetails.status.state === "running" && serverDetails.status.pid && (
        <section className="dashboard-section">
          <h2>Server Information</h2>
          <div className="server-info">
            <div className="info-row">
              <span className="info-label">Process ID:</span>
              <span className="info-value">{serverDetails.status.pid}</span>
            </div>
            {serverDetails.status.uptime && (
              <div className="info-row">
                <span className="info-label">Uptime:</span>
                <span className="info-value">
                  {Math.floor(serverDetails.status.uptime / 60)} minutes
                </span>
              </div>
            )}
            <div className="info-row">
              <span className="info-label">Restart Count:</span>
              <span className="info-value">{serverDetails.status.restart_count}</span>
            </div>
            {serverDetails.restart_policy && (
              <>
                <div className="info-row">
                  <span className="info-label">Restart Policy:</span>
                  <span className="info-value">{serverDetails.restart_policy}</span>
                </div>
                {serverDetails.max_restarts && (
                  <div className="info-row">
                    <span className="info-label">Max Restarts:</span>
                    <span className="info-value">{serverDetails.max_restarts}</span>
                  </div>
                )}
                {serverDetails.restart_window_sec && (
                  <div className="info-row">
                    <span className="info-label">Restart Window:</span>
                    <span className="info-value">{serverDetails.restart_window_sec}s</span>
                  </div>
                )}
              </>
            )}
          </div>
        </section>
      )}
    </div>
  );
}