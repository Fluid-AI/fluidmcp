import { useParams, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useServerDetails } from "../hooks/useServerDetails";
import { useServerEnv } from "../hooks/useServerEnv";
import { useServerPolling } from "../hooks/useServerPolling";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorMessage from "../components/ErrorMessage";
import { ServerEnvForm } from "../components/ServerEnvForm";
import { showSuccess, showError, showLoading } from "../services/toast";

export default function ServerDetails() {
  const { serverId } = useParams<{ serverId: string }>();
  const navigate = useNavigate();
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [envFormExpanded, setEnvFormExpanded] = useState(false);
  const [envSubmitting, setEnvSubmitting] = useState(false);

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

  const {
    envMetadata,
    loading: envLoading,
    error: envError,
    updateEnv,
    refetch: refetchEnv,
  } = useServerEnv(serverId);

  const { pollForServerState } = useServerPolling(serverId || '');

  // Detect if server needs env variables
  const configEnv = serverDetails?.config?.env || {};
  const needsEnv = Object.keys(configEnv).length > 0;

  // Check if instance env is configured by looking at envMetadata
  // All required env vars must be present
  const hasInstanceEnv = envMetadata && needsEnv &&
    Object.keys(configEnv).every(key => envMetadata[key]?.present === true);

  // Debug logging
  console.log('[ServerDetails] Env Check:', {
    needsEnv,
    hasInstanceEnv,
    configEnvKeys: Object.keys(configEnv),
    envMetadata
  });

  // Auto-expand env form if server needs env but doesn't have instance env yet
  const shouldExpandEnvForm = needsEnv && !hasInstanceEnv;

  const handleStartServer = async () => {
    const toastId = `server-${serverId}`;
    const serverName = serverDetails?.name || serverId;

    setActionLoading('start');
    showLoading(`Starting server "${serverName}"...`, toastId);

    try {
      await startServer();
      showSuccess(`Server "${serverName}" started successfully`, toastId);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to start server', toastId);
    } finally {
      setActionLoading(null);
    }
  };

  const handleStopServer = async () => {
    const toastId = `server-${serverId}`;
    const serverName = serverDetails?.name || serverId;

    setActionLoading('stop');
    showLoading(`Stopping server "${serverName}"...`, toastId);

    try {
      await stopServer();
      showSuccess(`Server "${serverName}" stopped successfully`, toastId);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to stop server', toastId);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRestartServer = async () => {
    const toastId = `server-${serverId}`;
    const serverName = serverDetails?.name || serverId;

    setActionLoading('restart');
    showLoading(`Restarting server "${serverName}"...`, toastId);

    try {
      await restartServer();
      showSuccess(`Server "${serverName}" restarted successfully`, toastId);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to restart server', toastId);
    } finally {
      setActionLoading(null);
    }
  };

  const handleEnvSubmit = async (env: Record<string, string>) => {
    if (!serverId) return;

    const toastId = `env-${serverId}`;

    setEnvSubmitting(true);
    showLoading('Saving environment variables and restarting server...', toastId);

    try {
      await updateEnv(env);

      // Poll for server restart and tools availability
      const success = await pollForServerState({
        expectedState: 'running',
        checkTools: true,
        onSuccess: () => {
          // Collapse form after successful restart
          setEnvFormExpanded(false);
          showSuccess('Environment variables saved and server restarted successfully', toastId);
        },
        onTimeout: () => {
          showError('Server restart timed out. Please check server status manually.', toastId);
        },
      });

      // Refetch server details and env metadata after polling completes
      if (success) {
        await Promise.all([refetch(), refetchEnv()]);
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to update environment variables', toastId);
      throw err; // Re-throw so form knows it failed
    } finally {
      setEnvSubmitting(false);
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

      {/* Environment Configuration Section */}
      {needsEnv && (
        <section className="dashboard-section">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <h2>
              {shouldExpandEnvForm ? '⚠️ Environment Configuration Required' : '✓ Environment Configuration'}
            </h2>
            {hasInstanceEnv && !envFormExpanded && (
              <button
                className="details-btn"
                onClick={() => setEnvFormExpanded(true)}
              >
                Edit Variables ▼
              </button>
            )}
            {hasInstanceEnv && envFormExpanded && (
              <button
                className="details-btn"
                onClick={() => setEnvFormExpanded(false)}
              >
                Collapse ▲
              </button>
            )}
          </div>

          {shouldExpandEnvForm && (
            <div style={{ padding: '16px', background: 'rgba(234, 179, 8, 0.1)', border: '1px solid rgba(234, 179, 8, 0.3)', borderRadius: '8px', marginBottom: '16px' }}>
              <p style={{ margin: 0, color: 'var(--color-warning)' }}>
                This server requires environment variables to function properly. Please configure them below.
              </p>
            </div>
          )}

          {(shouldExpandEnvForm || envFormExpanded) && (
            <>
              {envLoading ? (
                <LoadingSpinner message="Loading environment configuration..." />
              ) : envError ? (
                <ErrorMessage message={envError} onRetry={refetchEnv} />
              ) : (
                <>
                  <ServerEnvForm
                    serverId={serverId!}
                    configEnv={configEnv}
                    envMetadata={envMetadata}
                    onSubmit={handleEnvSubmit}
                    onCancel={hasInstanceEnv ? () => setEnvFormExpanded(false) : undefined}
                    serverState={serverDetails?.status?.state || 'stopped'}
                  />
                  {envSubmitting && (
                    <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(74, 144, 226, 0.1)', borderRadius: '8px', textAlign: 'center' }}>
                      <LoadingSpinner size="small" />
                      <p style={{ marginTop: '0.5rem', color: '#4a90e2' }}>
                        Saving and restarting server... This may take a few moments.
                      </p>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </section>
      )}

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
            <>
              {needsEnv && !hasInstanceEnv && (
                <div className="empty-state" style={{ marginBottom: '1rem', backgroundColor: '#2a2a2a', padding: '1rem', borderLeft: '4px solid #f59e0b' }}>
                  <div className="empty-state-icon" style={{ fontSize: '1.5rem' }}>⚠️</div>
                  <h3 className="empty-state-title" style={{ fontSize: '1rem', margin: '0.5rem 0' }}>Environment Configuration Required</h3>
                  <p className="empty-state-description" style={{ fontSize: '0.875rem', margin: '0' }}>
                    Configure environment variables above before running tools
                  </p>
                </div>
              )}
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
                      disabled={needsEnv && !hasInstanceEnv}
                      title={needsEnv && !hasInstanceEnv ? "Configure environment variables first" : "Run this tool"}
                    >
                      Run tool
                    </button>
                  </div>
                ))}
              </div>
            </>
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