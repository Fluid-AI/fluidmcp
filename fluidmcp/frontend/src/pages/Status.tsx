import { Link } from "react-router-dom";
import { useState } from "react";
import { useServers } from "../hooks/useServers";
import { showSuccess, showError, showLoading } from "../services/toast";
import { Footer } from "@/components/Footer";
import { Skeleton } from "@/components/ui/skeleton";

export default function Status() {
  const { servers, activeServers, loading, error, refetch, stopServer, restartServer } = useServers();

  const [actionState, setActionState] = useState<{
    serverId: string | null;
    type: 'stopping' | 'restarting' | null;
  }>({ serverId: null, type: null });

  const handleStopServer = async (serverId: string) => {
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
        <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
          <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
            <div className="flex items-center space-x-8">
              <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
                <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP </span>
              </Link>
              <nav className="hidden md:flex items-center space-x-1 text-sm">
                <Link 
                  to="/servers" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
                >
                  Servers
                </Link>
                <Link 
                  to="/status" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
                >
                  Status
                </Link>
                <a 
                  href="#" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
                >
                  Documentation
                </a>
              </nav>
            </div>
            <div className="flex items-center space-x-3">
              <button 
                style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                Fluid MCP for your Enterprise
              </button>
              <button 
                style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                </svg>
                Report Issue
              </button>
            </div>
          </div>
        </header>
        <div style={{ paddingTop: '64px' }}>
          <header className="dashboard-header">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <Skeleton className="h-8 w-64 mb-2" />
                <Skeleton className="h-4 w-48" />
              </div>
              <Skeleton className="h-10 w-24" />
            </div>
          </header>
          
          <section className="dashboard-section">
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
      <div className="dashboard">
        {/* Navbar */}
        <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
          <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
            <div className="flex items-center space-x-8">
              <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
                <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP </span>
              </Link>
              <nav className="hidden md:flex items-center space-x-1 text-sm">
                <Link 
                  to="/servers" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
                >
                  Servers
                </Link>
                <Link 
                  to="/status" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
                >
                  Status
                </Link>
                <a 
                  href="#" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
                >
                  Documentation
                </a>
              </nav>
            </div>
            <div className="flex items-center space-x-3">
              <button 
                style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                Fluid MCP for your Enterprise
              </button>
              <button 
                style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                </svg>
                Report Issue
              </button>
            </div>
          </div>
        </header>
        <div style={{ paddingTop: '64px' }}>
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
    <div className="dashboard">
      {/* Navbar */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
        <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
          <div className="flex items-center space-x-8">
            <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
              <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP </span>
            </Link>
            <nav className="hidden md:flex items-center space-x-1 text-sm">
              <Link 
                to="/servers" 
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
              >
                Servers
              </Link>
              <Link 
                to="/status" 
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
              >
                Status
              </Link>
              <a 
                href="#" 
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
              >
                Documentation
              </a>
            </nav>
          </div>
          <div className="flex items-center space-x-3">
            <button 
              style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
              Fluid MCP for your Enterprise
            </button>
            <button 
              style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
              </svg>
              Report Issue
            </button>
          </div>
        </div>
      </header>

      {/* Dashboard Content */}
      <div style={{ paddingTop: '64px' }}>
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
      </div>

      {/* Currently Active Servers */}
      <section className="dashboard-section">
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

      {/* Footer */}
      <Footer />
    </div>
  );
}
