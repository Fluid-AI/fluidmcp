import { useParams, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useServerDetails } from "../hooks/useServerDetails";
import { useServerEnv } from "../hooks/useServerEnv";
import { useServerPolling } from "../hooks/useServerPolling";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorMessage from "../components/ErrorMessage";
import { ServerEnvForm } from "../components/ServerEnvForm";
import { showSuccess, showError, showLoading } from "../services/toast";
import { Footer } from "@/components/Footer";
import { Skeleton } from "@/components/ui/skeleton";
import { Navbar } from "@/components/Navbar";

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
      <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <Navbar />
        <div style={{ paddingTop: '64px', flex: 1 }}>
          <header className="dashboard-header">
            <button 
              onClick={() => navigate("/servers")}
              style={{ background: 'transparent', color: '#d1d5db', border: '1px solid rgba(63, 63, 70, 0.6)', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', gap: '0.5rem', transition: 'all 0.2s', marginBottom: '1rem', cursor: 'pointer' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(39, 39, 42, 0.8)'; e.currentTarget.style.borderColor = 'rgba(82, 82, 91, 0.8)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(63, 63, 70, 0.6)'; }}
            >
              ← Back to Servers
            </button>
            <Skeleton className="h-8 w-64 mb-2" />
            <Skeleton className="h-4 w-48" />
          </header>
          <section className="dashboard-section">
            <div className="flex flex-col gap-6">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          </section>
        </div>
        <Footer />
      </div>
    );
  }

  if (error || !serverDetails) {
    return (
      <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <Navbar />
        <div style={{ paddingTop: '64px', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <header className="dashboard-header">
            <button 
              onClick={() => navigate("/servers")}
              style={{ background: 'transparent', color: '#d1d5db', border: '1px solid rgba(63, 63, 70, 0.6)', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', gap: '0.5rem', transition: 'all 0.2s', marginBottom: '1rem', cursor: 'pointer' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(39, 39, 42, 0.8)'; e.currentTarget.style.borderColor = 'rgba(82, 82, 91, 0.8)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(63, 63, 70, 0.6)'; }}
            >
              ← Back to Servers
            </button>
            <h1>Error Loading Server</h1>
          </header>
          <ErrorMessage
            message={error || "Server not found"}
            onRetry={refetch}
          />
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />

      {/* Main Content */}
      <div style={{ paddingTop: '64px', flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Header with Back Button and Server Info */}
        <header className="dashboard-header">
          <button 
            onClick={() => navigate("/servers")}
            style={{ background: 'transparent', color: '#d1d5db', border: '1px solid rgba(63, 63, 70, 0.6)', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', gap: '0.5rem', transition: 'all 0.2s', marginBottom: '1rem', cursor: 'pointer' }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(39, 39, 42, 0.8)'; e.currentTarget.style.borderColor = 'rgba(82, 82, 91, 0.8)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(63, 63, 70, 0.6)'; }}
          >
            ← Back to Servers
          </button>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h1>{serverDetails.name}</h1>
              <p className="subtitle">
                {serverDetails.description || "No description available"}
              </p>
            </div>
            <div className={`flex items-center gap-1 px-3 py-1.5 border rounded-full whitespace-nowrap ${serverDetails.status.state === 'running' ? 'text-green-400 bg-green-500/10 border-green-500/30' : serverDetails.status.state === 'failed' ? 'text-red-400 bg-red-500/10 border-red-500/30' : 'text-zinc-400 bg-zinc-500/10 border-zinc-500/30'}`}>
              <span className="text-sm font-medium capitalize">
                {serverDetails.status.state || "stopped"}
              </span>
            </div>
          </div>

          {/* Server Control Buttons */}
          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
            {isStopped && (
              <button
                onClick={handleStartServer}
                disabled={actionLoading === 'start'}
                className="px-4 py-2 bg-white hover:bg-zinc-100 text-black rounded-lg font-medium transition-all duration-200 hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading === 'start' ? 'Starting...' : 'Start Server'}
              </button>
            )}
            {isRunning && (
              <>
                <button
                  onClick={handleStopServer}
                  disabled={actionLoading === 'stop'}
                  className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {actionLoading === 'stop' ? 'Stopping...' : 'Stop Server'}
                </button>
                <button
                  onClick={handleRestartServer}
                  disabled={actionLoading === 'restart'}
                  className="px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-lg font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
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
        <div style={{ maxWidth: '1200px' }}>
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
                <div style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem', background: 'rgba(234, 179, 8, 0.1)', border: '1px solid rgba(234, 179, 8, 0.3)', borderRadius: '12px', borderLeft: '4px solid #f59e0b' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{ fontSize: '1.5rem' }}>⚠️</div>
                    <div>
                      <h3 style={{ fontSize: '1rem', margin: '0 0 0.25rem 0', color: '#fbbf24', fontWeight: '600' }}>Environment Configuration Required</h3>
                      <p style={{ fontSize: '0.875rem', margin: '0', color: '#d1d5db' }}>
                        Configure environment variables above before running tools
                      </p>
                    </div>
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {tools.map((tool) => (
                  <div 
                    key={tool.name} 
                    style={{ 
                      background: 'linear-gradient(to bottom right, rgba(39, 39, 42, 0.9), rgba(24, 24, 27, 0.9))',
                      border: '1px solid rgba(63, 63, 70, 0.5)',
                      borderRadius: '16px',
                      padding: '1.5rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: '1.5rem',
                      transition: 'all 0.3s ease',
                      position: 'relative',
                      overflow: 'hidden'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.transform = 'translateY(-2px)';
                      e.currentTarget.style.borderColor = 'rgba(82, 82, 91, 0.8)';
                      e.currentTarget.style.boxShadow = '0 8px 16px rgba(0, 0, 0, 0.3)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.transform = 'translateY(0)';
                      e.currentTarget.style.borderColor = 'rgba(63, 63, 70, 0.5)';
                      e.currentTarget.style.boxShadow = 'none';
                    }}
                  >
                    {/* Gradient accent */}
                    <div style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      right: 0,
                      height: '3px',
                      background: 'linear-gradient(to right, #6366f1, #8b5cf6, #ec4899)',
                      opacity: 0.6
                    }} />
                    
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                        <span style={{ fontSize: '1.25rem' }}>🔧</span>
                        <h3 style={{ 
                          fontSize: '1.125rem', 
                          fontWeight: '700', 
                          color: '#fff',
                          margin: 0,
                          letterSpacing: '-0.01em'
                        }}>
                          {tool.name}
                        </h3>
                      </div>
                      <p style={{ 
                        fontSize: '0.875rem', 
                        color: '#a1a1aa',
                        margin: 0,
                        lineHeight: '1.5'
                      }}>
                        {tool.description}
                      </p>
                    </div>

                    <button
                      onClick={() => navigate(`/servers/${serverId}/tools/${tool.name}`)}
                      disabled={needsEnv && !hasInstanceEnv}
                      style={{
                        padding: '0.625rem 1.5rem',
                        background: '#fff',
                        color: '#000',
                        border: 'none',
                        borderRadius: '10px',
                        fontSize: '0.875rem',
                        fontWeight: '600',
                        cursor: needsEnv && !hasInstanceEnv ? 'not-allowed' : 'pointer',
                        transition: 'all 0.2s ease',
                        whiteSpace: 'nowrap',
                        opacity: needsEnv && !hasInstanceEnv ? 0.5 : 1,
                        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)'
                      }}
                      onMouseEnter={(e) => {
                        if (!(needsEnv && !hasInstanceEnv)) {
                          e.currentTarget.style.background = '#f4f4f5';
                          e.currentTarget.style.transform = 'scale(1.05)';
                          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.2)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = '#fff';
                        e.currentTarget.style.transform = 'scale(1)';
                        e.currentTarget.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.15)';
                      }}
                      title={needsEnv && !hasInstanceEnv ? "Configure environment variables first" : "Run this tool"}
                    >
                      Run tool →
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

      {/* Footer */}
      <Footer />
    </div>
  );
}