import { useState, useEffect } from 'react';
import { Navbar } from '../components/Navbar';
import { ServerForm } from '../components/ServerForm';
import { DeleteConfirmationModal } from '../components/DeleteConfirmationModal';
import { useServerManagement } from '../hooks/useServerManagement';
import { Pagination } from '../components/Pagination';
import { Server } from '../types/server';

type FilterMode = 'all' | 'running' | 'stopped' | 'failed';

export default function ManageServers() {
  const [showDeleted, setShowDeleted] = useState(false);
  const { servers, loading, createServer, updateServer, deleteServer, refetch } = useServerManagement(showDeleted);

  const [showForm, setShowForm] = useState(false);
  const [editingServer, setEditingServer] = useState<Server | null>(null);
  const [deletingServer, setDeletingServer] = useState<Server | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterMode, setFilterMode] = useState<FilterMode>('all');
  const [currentPage, setCurrentPage] = useState(1);

  const SERVERS_PER_PAGE = 10;

  // Filter and search
  const filteredServers = servers.filter(server => {
    const matchesSearch = server.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          server.id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFilter = filterMode === 'all' || server.status?.state === filterMode;
    return matchesSearch && matchesFilter;
  });

  // Pagination
  const totalPages = Math.ceil(filteredServers.length / SERVERS_PER_PAGE);
  const paginatedServers = filteredServers.slice(
    (currentPage - 1) * SERVERS_PER_PAGE,
    currentPage * SERVERS_PER_PAGE
  );

  // Reset to valid page if current page becomes invalid (e.g., after filtering or deletion)
  useEffect(() => {
    if (filteredServers.length > 0 && currentPage > totalPages) {
      setCurrentPage(Math.max(1, totalPages));
    }
  }, [filteredServers.length, currentPage, totalPages]);

  // Refetch servers when showDeleted changes
  useEffect(() => {
    refetch(showDeleted);
  }, [showDeleted, refetch]);

  const handleCreate = () => {
    setEditingServer(null);
    setShowForm(true);
  };

  const handleEdit = (server: Server) => {
    if (server.status?.state === 'running') {
      alert('Cannot edit running server. Stop it first.');
      return;
    }
    setEditingServer(server);
    setShowForm(true);
  };

  const handleFormSubmit = async (formData: any) => {
    if (editingServer) {
      return await updateServer(editingServer.id, formData);
    } else {
      return await createServer(formData);
    }
  };

  const handleDeleteClick = (server: Server) => {
    setDeletingServer(server);
  };

  const handleDisable = async () => {
    if (!deletingServer) return;
    // Backend requires name and command fields for update
    const updateData = {
      name: deletingServer.name,
      command: deletingServer.config.command,
      args: deletingServer.config.args,
      env: deletingServer.config.env,
      description: deletingServer.description || '',
      enabled: false,
    };
    await updateServer(deletingServer.id, updateData);
  };

  const handleDelete = async () => {
    if (!deletingServer) return;
    await deleteServer(deletingServer.id, deletingServer.name);
  };

  return (
    <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />

      <div style={{ paddingTop: '64px', flex: 1 }}>
        <header className="dashboard-header">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h1>Manage Servers</h1>
              <p className="subtitle">
                Create, edit, and delete server configurations
              </p>
            </div>
          </div>
        </header>

        <section className="dashboard-section">
          {/* Controls */}
          <div className="relative bg-gradient-to-br from-zinc-900/90 to-zinc-800/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-6 mb-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <input
              type="text"
              placeholder="Search by name or ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 max-w-md px-4 py-2 bg-zinc-800/50 border border-zinc-700 text-white placeholder-zinc-400 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />

            <div className="flex items-center space-x-2">
              {(['all', 'running', 'stopped', 'failed'] as FilterMode[]).map(mode => (
                <button
                  key={mode}
                  onClick={() => setFilterMode(mode)}
                  className={`px-3 py-1 text-sm rounded-lg capitalize transition-colors ${
                    filterMode === mode ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
                  }`}
                >
                  {mode}
                </button>
              ))}

              <div className="border-l border-zinc-700 h-6 mx-2"></div>

              <button
                onClick={() => setShowDeleted(!showDeleted)}
                className={`px-3 py-1 text-sm rounded-lg transition-colors inline-flex items-center space-x-2 ${
                  showDeleted ? 'bg-yellow-600 text-white' : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
                }`}
                title="Show soft-deleted servers (admin recovery)"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                <span>Deleted</span>
              </button>
            </div>

            <button
              onClick={handleCreate}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors inline-flex items-center"
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add Server
            </button>
          </div>
        </div>

        {/* Form Dialog */}
        {showForm && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="relative bg-gradient-to-br from-zinc-900 to-zinc-800 border border-zinc-700 rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6">
              <button
                onClick={() => setShowForm(false)}
                className="absolute top-4 right-4 text-zinc-400 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <h2 className="text-2xl font-bold text-white mb-6">
                {editingServer ? 'Edit Server' : 'Create New Server'}
              </h2>
              <ServerForm
                mode={editingServer ? 'edit' : 'create'}
                initialData={editingServer}
                onSubmit={handleFormSubmit}
                onCancel={() => setShowForm(false)}
              />
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {deletingServer && (
          <DeleteConfirmationModal
            server={deletingServer}
            onDisable={handleDisable}
            onDelete={handleDelete}
            onCancel={() => setDeletingServer(null)}
          />
        )}

        {/* Server Table */}
        {loading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          </div>
        ) : filteredServers.length === 0 ? (
          <div className="relative bg-gradient-to-br from-zinc-900/90 to-zinc-800/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-12 text-center">
            <p className="text-zinc-400">
              {searchQuery || filterMode !== 'all' ? 'No servers found matching your criteria' : 'No servers configured yet. Click "Add Server" to get started.'}
            </p>
          </div>
        ) : (
          <>
            <div className="relative bg-gradient-to-br from-zinc-900/90 to-zinc-800/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl overflow-hidden">
              <table className="min-w-full divide-y divide-zinc-700">
                <thead className="bg-zinc-800/50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">Server</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">Command</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">Status</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-700">
                  {paginatedServers.map(server => {
                    const isRunning = server.status?.state === 'running';
                    const statusColor =
                      server.status?.state === 'running' ? 'bg-green-900/40 text-green-400 border border-green-500/30' :
                      server.status?.state === 'stopped' ? 'bg-zinc-700/40 text-zinc-300 border border-zinc-600/30' :
                      server.status?.state === 'failed' ? 'bg-red-900/40 text-red-400 border border-red-500/30' :
                      'bg-zinc-700/40 text-zinc-300 border border-zinc-600/30';

                    return (
                      <tr key={server.id} className="hover:bg-zinc-800/50 transition-colors">
                        <td className="px-6 py-4">
                          <div className="text-sm font-medium text-white">{server.name}</div>
                          <div className="text-xs text-zinc-400 font-mono">{server.id}</div>
                          {server.description && (
                            <div className="text-xs text-zinc-400 mt-1">{server.description}</div>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <code className="text-xs bg-zinc-800/70 text-zinc-300 px-2 py-1 rounded">
                            {server.config?.command} {server.config?.args?.join(' ').substring(0, 40)}
                            {server.config?.args?.join(' ').length > 40 && '...'}
                          </code>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusColor}`}>
                            {server.status?.state || 'unknown'}
                          </span>
                          {!server.enabled && (
                            <span className="ml-2 text-xs text-yellow-400 italic">(Disabled)</span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex space-x-2">
                            <button
                              onClick={() => handleEdit(server)}
                              disabled={isRunning}
                              className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                                isRunning
                                  ? 'bg-zinc-800 text-zinc-600 cursor-not-allowed'
                                  : 'bg-blue-600 text-white hover:bg-blue-700'
                              }`}
                              title={isRunning ? 'Cannot edit while running' : 'Edit server'}
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleDeleteClick(server)}
                              className="px-3 py-1 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors"
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="mt-6">
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  totalItems={filteredServers.length}
                  itemsPerPage={SERVERS_PER_PAGE}
                  onPageChange={setCurrentPage}
                  itemName="servers"
                />
              </div>
            )}
          </>
        )}
        </section>
      </div>
    </div>
  );
}
