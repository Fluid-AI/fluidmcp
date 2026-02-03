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
  const { servers, activeServers, loading, error, refetch, startServer } = useServers();

  const [actionState, setActionState] = useState<{
    serverId: string | null;
    type: 'starting' | 'stopping' | 'restarting' | null;
  }>({ serverId: null, type: null });

  const handleStartServer = async (serverId: string) => {
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
            <Button onClick={refetch} variant="outline" size="sm" className="gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </Button>
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
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
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

      {/* Footer */}
      <Footer />
    </div>
  );
}