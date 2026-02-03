import { useNavigate, Link } from "react-router-dom";
import { useState } from "react";
import ServerCard from "../components/ServerCard";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorMessage from "../components/ErrorMessage";
import { useServers } from "../hooks/useServers";
import { showSuccess, showError, showLoading } from "../services/toast";
import { Button } from "@/components/ui/button";
import { Footer } from "@/components/Footer";

export default function Dashboard() {
  const navigate = useNavigate();
  const { servers, activeServers, loading, error, refetch, startServer, stopServer, restartServer } = useServers();

  const [actionState, setActionState] = useState<{
    serverId: string | null;
    type: 'starting' | 'stopping' | 'restarting' | null;
  }>({ serverId: null, type: null });

  const handleStartServer = async (serverId: string) => {
    // Silent guard - prevent concurrent operations
    if (actionState.type !== null) return;

    const server = servers.find(s => s.id === serverId);
    const serverName = server?.name || serverId;
    const toastId = `server-${serverId}`;

    setActionState({ serverId, type: 'starting' });
    showLoading(`Starting server "${serverName}"...`, toastId);

    try {
      await startServer(serverId);
      showSuccess(`Server "${serverName}" started successfully`, toastId);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to start server', toastId);
    } finally {
      setActionState({ serverId: null, type: null });
    }
  };

  const handleStopServer = async (serverId: string) => {
    // Silent guard - prevent concurrent operations
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
  };

  const handleRestartServer = async (serverId: string) => {
    // Silent guard - prevent concurrent operations
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
  };

  if (loading) {
    return (
      <div className="dashboard">
        {/* Navbar */}
        <header className="fixed top-0 w-full z-50 border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="container mx-auto flex h-16 items-center justify-between px-6">
            <Link to="/" className="flex items-center space-x-2">
              <span className="text-xl font-bold">Fluid MCP</span>
            </Link>
            <nav className="hidden md:flex items-center space-x-6 text-sm">
              <Link to="/" className="transition-colors hover:text-foreground/80 text-foreground/60">
                Home
              </Link>
              <Link to="/servers" className="transition-colors hover:text-foreground/80 text-foreground">
                Servers
              </Link>
              <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">
                Submit
              </a>
              <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">
                Documentation
              </a>
            </nav>
            <div className="flex items-center space-x-4">
              <Button variant="ghost" size="sm" asChild>
                <Link to="/servers">Browse Registry</Link>
              </Button>
            </div>
          </div>
        </header>
        <div style={{ paddingTop: '64px' }}>
          <LoadingSpinner size="large" message="Loading servers..." />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard">
        {/* Navbar */}
        <header className="fixed top-0 w-full z-50 border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="container mx-auto flex h-16 items-center justify-between px-6">
            <Link to="/" className="flex items-center space-x-2">
              <span className="text-xl font-bold">Fluid MCP</span>
            </Link>
            <nav className="hidden md:flex items-center space-x-6 text-sm">
              <Link to="/" className="transition-colors hover:text-foreground/80 text-foreground/60">
                Home
              </Link>
              <Link to="/servers" className="transition-colors hover:text-foreground/80 text-foreground">
                Servers
              </Link>
              <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">
                Submit
              </a>
              <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">
                Documentation
              </a>
            </nav>
            <div className="flex items-center space-x-4">
              <Button variant="ghost" size="sm" asChild>
                <Link to="/servers">Browse Registry</Link>
              </Button>
            </div>
          </div>
        </header>
        <div style={{ paddingTop: '64px' }}>
          <ErrorMessage message={error} onRetry={refetch} />
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* Navbar */}
      <header className="fixed top-0 w-full z-50 border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-16 items-center justify-between px-6">
          <Link to="/" className="flex items-center space-x-2">
            <span className="text-xl font-bold">Fluid MCP</span>
          </Link>
          <nav className="hidden md:flex items-center space-x-6 text-sm">
            <Link to="/" className="transition-colors hover:text-foreground/80 text-foreground/60">
              Home
            </Link>
            <Link to="/servers" className="transition-colors hover:text-foreground/80 text-foreground">
              Servers
            </Link>
            <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">
              Submit
            </a>
            <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">
              Documentation
            </a>
          </nav>
          <div className="flex items-center space-x-4">
            <Button variant="ghost" size="sm" asChild>
              <Link to="/servers">Browse Registry</Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Dashboard Content */}
      <div style={{ paddingTop: '64px' }}>
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
      </div>

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
                isStarting={actionState.serverId === server.id && actionState.type === 'starting'}
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

      {/* Footer */}
      <Footer />
    </div>
  );
}