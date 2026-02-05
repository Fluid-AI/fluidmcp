import { useNavigate, Link } from "react-router-dom";
import { useState, useEffect } from "react";
import ServerCard from "../components/ServerCard";
import ErrorMessage from "../components/ErrorMessage";
import { useServers } from "../hooks/useServers";
import { showSuccess, showError, showLoading } from "../services/toast";
import { Footer } from "@/components/Footer";
import { Skeleton } from "@/components/ui/skeleton";
import AOS from 'aos';
import 'aos/dist/aos.css';
//dummy comment to change file
export default function Dashboard() {
  const navigate = useNavigate();
  const { servers, activeServers, loading, error, refetch, startServer } = useServers();

  useEffect(() => {
    AOS.init({
      duration: 800,
      easing: 'ease-in-out',
      once: true,
      offset: 50,
    });
  }, []);

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
        <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
          <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
            <div className="flex items-center space-x-8">
              <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
                <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP </span>
              </Link>
              <nav className="hidden md:flex items-center space-x-1 text-sm">
                <Link 
                  to="/servers" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
                >
                  Servers
                </Link>
                <Link 
                  to="/status" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
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
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {[...Array(6)].map((_, index) => (
                <div key={index} className="relative bg-gradient-to-br from-zinc-900/90 to-zinc-800/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-6">
                  <div className="flex items-start justify-between mb-4">
                    <Skeleton className="h-6 w-40" />
                    <Skeleton className="h-5 w-16 rounded-full" />
                  </div>
                  <Skeleton className="h-4 w-full mb-2" />
                  <Skeleton className="h-4 w-3/4 mb-4" />
                  <div className="flex items-center gap-4 mb-4">
                    <Skeleton className="h-4 w-20" />
                    <Skeleton className="h-4 w-32" />
                  </div>
                  <div className="flex items-center gap-2 pt-4 border-t border-zinc-700/50">
                    <Skeleton className="h-10 flex-1" />
                    <Skeleton className="h-10 flex-1" />
                  </div>
                </div>
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
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
                >
                  Servers
                </Link>
                <Link 
                  to="/status" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
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
          <ErrorMessage message={error} onRetry={refetch} />
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
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
              >
                Servers
              </Link>
              <Link 
                to="/status" 
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
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
              <h1>FluidMCP Dashboard</h1>
              <p className="subtitle">
                {servers.length} {servers.length === 1 ? 'server' : 'servers'} configured, {activeServers.length} running
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
            {servers.map((server, index) => (
              <div
                key={server.id}
                data-aos="fade-up"
                data-aos-delay={index * 100}
              >
                <ServerCard
                  server={server}
                  onStart={() => handleStartServer(server.id)}
                  onViewDetails={() => navigate(`/servers/${server.id}`)}
                  isStarting={actionState.serverId === server.id && actionState.type === 'starting'}
                />
              </div>                     
            ))}
          </div>
        )}
      </section>

      {/* Footer */}
      <Footer />
    </div>
  );
}