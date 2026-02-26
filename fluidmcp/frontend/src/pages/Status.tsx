import { Link } from "react-router-dom";
import { useState, useCallback } from "react";
import { useServers } from "../hooks/useServers";
import { showSuccess, showError, showLoading } from "../services/toast";
import { Footer } from "@/components/Footer";
import { Skeleton } from "@/components/ui/skeleton";
import { Navbar } from "@/components/Navbar";
import { ErrorBoundary } from "../components/ErrorBoundary";

export default function Status() {
  const { servers, activeServers, loading, error, refetch, stopServer, restartServer } = useServers();

  const [actionState, setActionState] = useState<{
    serverId: string | null;
    type: 'stopping' | 'restarting' | null;
  }>({ serverId: null, type: null });

  const handleStopServer = useCallback(async (serverId: string) => {
    if (actionState.type !== null) return;

    const server = servers.find(s => s.id === serverId);
    const serverName = server?.name || serverId;
    const toastId = `server-${serverId}`;

    setActionState({ serverId, type: 'stopping' });
    showLoading(`Stopping server "${serverName}"...`, toastId);

    try {
      await stopServer(serverId);
      showSuccess(`Server "${serverName}" stopped successfully`, toastId);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to stop server', toastId);
    } finally {
      setActionState({ serverId: null, type: null });
    }
  }, [actionState.type, servers, stopServer]);

  const handleRestartServer = useCallback(async (serverId: string) => {
    if (actionState.type !== null) return;

    const server = servers.find(s => s.id === serverId);
    const serverName = server?.name || serverId;
    const toastId = `server-${serverId}`;

    setActionState({ serverId, type: 'restarting' });
    showLoading(`Restarting server "${serverName}"...`, toastId);

    try {
      await restartServer(serverId);
      showSuccess(`Server "${serverName}" restarted successfully`, toastId);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to restart server', toastId);
    } finally {
      setActionState({ serverId: null, type: null });
    }
  }, [actionState.type, servers, restartServer]);

  if (loading) {
    return (
      <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <Navbar />
        <div style={{ paddingTop: '64px', flex: 1, display: 'flex', flexDirection: 'column' }}>
          <header className="dashboard-header">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <Skeleton className="h-8 w-64 mb-2" />
                <Skeleton className="h-4 w-48" />
              </div>
              <Skeleton className="h-10 w-24" />
            </div>
          </header>
          
          <section className="dashboard-section" style={{ flex: 1 }}>
            <Skeleton className="h-6 w-48 mb-6" />
            <div className="flex flex-col gap-4">
              {[...Array(3)].map((_, index) => (
                <Skeleton key={index} className="h-16 w-full" />
              ))}
            </div>
          </section>
          
          <Footer />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <Navbar />
        <div style={{ paddingTop: '64px', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <div className="error-container">
            <div className="error-message">{error}</div>
            <button onClick={refetch} className="retry-btn">
              Try again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />

      {/* Dashboard Content */}
      <div style={{ paddingTop: '64px', flex: 1, display: 'flex', flexDirection: 'column' }}>
        <header className="dashboard-header">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h1>Server Status</h1>
              <p className="subtitle">
                {activeServers.length} of {servers.length} {servers.length === 1 ? 'server' : 'servers'} running
              </p>
            </div>
            <button 
              onClick={refetch}
              style={{ background: 'transparent', color: '#d1d5db', border: '1px solid rgba(63, 63, 70, 0.6)', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', gap: '0.5rem', transition: 'all 0.2s', margin: 0, cursor: 'pointer' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(39, 39, 42, 0.8)'; e.currentTarget.style.borderColor = 'rgba(82, 82, 91, 0.8)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(63, 63, 70, 0.6)'; }}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </button>
          </div>
        </header>

        {/* Currently Active Servers */}
        <ErrorBoundary fallback={
          <section className="dashboard-section" style={{ flex: 1 }}>
            <h2>Currently active servers</h2>
            <div className="result-error">
              <h3>Error Loading Active Servers</h3>
              <p>Failed to render active server list. Please refresh the page.</p>
            </div>
          </section>
        }>
          <section className="dashboard-section" style={{ flex: 1 }}>
            <h2>Currently active servers</h2>

          <div className="active-server-container">
            {activeServers.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">💤</div>
                <h3 className="empty-state-title">No servers running</h3>
                <p className="empty-state-description">
                  Start a server from the <Link to="/servers" style={{ color: '#60a5fa', textDecoration: 'underline' }}>Servers page</Link>
                </p>
              </div>
            ) : (
              <div className="active-server-list">
                {activeServers.map((server) => (
                  <div key={server.id} className="active-server-row">
                    <div>
                      <strong>{server.name}</strong>
                      <span className={`status ${server.status?.state}`}>
                        {server.status?.state}
                      </span>
                    </div>

                    <div className="active-server-actions">
                      <button
                        className="stop-btn"
                        onClick={() => handleStopServer(server.id)}
                        disabled={actionState.serverId === server.id && actionState.type === 'stopping'}
                      >
                        {actionState.serverId === server.id && actionState.type === 'stopping' ? 'Stopping...' : 'Stop'}
                      </button>
                      <button
                        className="restart-btn"
                        onClick={() => handleRestartServer(server.id)}
                        disabled={actionState.serverId === server.id && actionState.type === 'restarting'}
                      >
                        {actionState.serverId === server.id && actionState.type === 'restarting' ? 'Restarting...' : 'Restart'}
                      </button>
                      <Link to={`/servers/${server.id}`} className="details-btn">
                        Details
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
        </ErrorBoundary>
      </div>

      {/* Footer */}
      <Footer />
    </div>
  );
}
