import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import ServerCard from "../components/ServerCard";
import { ServerListControls } from "../components/ServerListControls";
import { Pagination } from "../components/Pagination";
import ErrorMessage from "../components/ErrorMessage";
import { useServers } from "../hooks/useServers";
import { showSuccess, showError, showLoading } from "../services/toast";
import { Footer } from "@/components/Footer";
import { Navbar } from "@/components/Navbar";
import { Skeleton } from "@/components/ui/skeleton";
import AOS from 'aos';
import 'aos/dist/aos.css';
//dummy comment to change file
export default function Dashboard() {
  const navigate = useNavigate();
  const { servers, activeServers, loading, error, refetch, startServer } = useServers();

  // Controls state
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<'name-asc' | 'name-desc' | 'status' | 'recent'>('name-asc');
  const [filterBy, setFilterBy] = useState<'all' | 'running' | 'stopped' | 'error'>('all');


  // Filtering, sorting, searching logic
  const filteredServers = servers
    .filter(server => {
      if (filterBy === 'running') return server.status?.state === 'running';
      if (filterBy === 'stopped') return server.status?.state === 'stopped';
      if (filterBy === 'error') return server.status?.state === 'failed';
      return true;
    })
    .filter(server => server.name?.toLowerCase().includes(searchQuery.toLowerCase()));

  const sortedServers = [...filteredServers].sort((a, b) => {
    if (sortBy === 'name-asc') return a.name.localeCompare(b.name);
    if (sortBy === 'name-desc') return b.name.localeCompare(a.name);
    if (sortBy === 'status') {
      // Running first, then stopped, then error/other
      const order = (s: any) => s.status?.state === 'running' ? 0 : s.status?.state === 'stopped' ? 1 : 2;
      return order(a) - order(b);
    }
    if (sortBy === 'recent') {
      // Most recently started first (assume updated_at is start time)
      return (new Date(b.updated_at || 0).getTime()) - (new Date(a.updated_at || 0).getTime());
    }
    return 0;
  });

  // Pagination logic

  const itemsPerPage = 9;
  const [currentPage, setCurrentPage] = useState(1);
  const totalPages = Math.ceil(sortedServers.length / itemsPerPage);
  const paginatedServers = sortedServers.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Ref for server list section
  const serverListRef = React.useRef<HTMLDivElement>(null);

  // Scroll to server list on page change
  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    setTimeout(() => {
      serverListRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
  };

  // Reset to page 1 if filters/search/sort change and currentPage is out of range
  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(1);
    // eslint-disable-next-line
  }, [searchQuery, sortBy, filterBy, sortedServers.length]);

  const handleClearFilters = () => {
    setSearchQuery("");
    setSortBy('name-asc');
    setFilterBy('all');
  };

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
        <Navbar />
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
        <Navbar />
        <div style={{ paddingTop: '64px' }}>
          <ErrorMessage message={error} onRetry={refetch} />
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <Navbar />

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
        <h2 ref={serverListRef}>Currently configured servers</h2>

        <div style={{ marginBottom: 24 }}>
          <ServerListControls
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            sortBy={sortBy}
            onSortChange={v => setSortBy(v as any)}
            filterBy={filterBy}
            onFilterChange={v => setFilterBy(v as any)}
            onClearFilters={handleClearFilters}
          />
        </div>
        {sortedServers.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📦</div>
            <h3 className="empty-state-title">No servers found</h3>
            <p className="empty-state-description">
              Try adjusting your search, sort, or filter options.
            </p>
          </div>
        ) : (
          <>
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {paginatedServers.map((server, index) => (
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
            {sortedServers.length > itemsPerPage && (
              <div style={{ marginTop: 32 }}>
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  totalItems={sortedServers.length}
                  itemsPerPage={itemsPerPage}
                  onPageChange={handlePageChange}
                  itemName="servers"
                />
              </div>
            )}
          </>
        )}
      </section>

      {/* Footer */}
      <Footer />
    </div>
  );
}