import { useNavigate } from "react-router-dom";
import { useState } from "react";
import ServerCard from "../components/ServerCard";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorMessage from "../components/ErrorMessage";
import { useServers } from "../hooks/useServers";

export default function Dashboard() {
  const navigate = useNavigate();
  const { servers, activeServers, loading, error, refetch, startServer, stopServer, restartServer } = useServers();
  const [startingServerId, setStartingServerId] = useState<string | null>(null);
  const [actionServerId, setActionServerId] = useState<string | null>(null);
  const [actionType, setActionType] = useState<'stop' | 'restart' | null>(null);

  const handleStartServer = async (serverId: string) => {
    setStartingServerId(serverId);
    try {
      await startServer(serverId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to start server');
    } finally {
      setStartingServerId(null);
    }
  };

  const handleStopServer = async (serverId: string) => {
    setActionServerId(serverId);
    setActionType('stop');
    try {
      await stopServer(serverId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to stop server');
    } finally {
      setActionServerId(null);
      setActionType(null);
    }
  };

  const handleRestartServer = async (serverId: string) => {
    setActionServerId(serverId);
    setActionType('restart');
    try {
      await restartServer(serverId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to restart server');
    } finally {
      setActionServerId(null);
      setActionType(null);
    }
  };

  if (loading) {
    return (
      <div className="dashboard">
        <LoadingSpinner size="large" message="Loading servers..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard">
        <header className="dashboard-header">
          <h1>FluidMCP Dashboard</h1>
        </header>
        <ErrorMessage message={error} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="dashboard-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1>FluidMCP Dashboard</h1>
            <p className="subtitle">
              {servers.length} {servers.length === 1 ? 'server' : 'servers'} configured, {activeServers.length} running
            </p>
          </div>
          <button onClick={refetch} className="retry-btn" style={{ marginTop: 0 }}>
            🔄 Refresh
          </button>
        </div>
      </header>

      {/* Main content */}
      <section className="dashboard-section">
        <h2>Currently configured servers</h2>

        {servers.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📦</div>
            <h3 className="empty-state-title">No servers configured</h3>
            <p className="empty-state-description">
              Add MCP servers to get started
            </p>
          </div>
        ) : (
          <div className="server-list">
            {servers.map((server) => (
              <ServerCard
                key={server.id}
                server={server}
                onStart={() => handleStartServer(server.id)}
                onViewDetails={() => navigate(`/servers/${server.id}`)}
                isStarting={startingServerId === server.id}
              />
            ))}
          </div>
        )}
      </section>

      <section className="dashboard-section">
        <h2>Currently active servers</h2>

        <div className="active-server-container">
          {activeServers.length === 0 ? (
            <p className="empty-state">
              No servers are currently running
            </p>
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
                      disabled={actionServerId === server.id && actionType === 'stop'}
                    >
                      {actionServerId === server.id && actionType === 'stop' ? 'Stopping...' : 'Stop'}
                    </button>
                    <button
                      className="restart-btn"
                      onClick={() => handleRestartServer(server.id)}
                      disabled={actionServerId === server.id && actionType === 'restart'}
                    >
                      {actionServerId === server.id && actionType === 'restart' ? 'Restarting...' : 'Restart'}
                    </button>
                    <button
                      className="details-btn"
                      onClick={() => navigate(`/servers/${server.id}`)}
                    >
                      Details
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}