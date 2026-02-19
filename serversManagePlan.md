Perfect! I've created a comprehensive implementation plan at /home/codespace/.claude/plans/sorted-dazzling-pascal.md. The plan includes:

✅ Context - Why this change is needed and user requirements

✅ 6 Implementation Phases - Backend first (soft delete), then frontend (Navbar + Manage page)

✅ Enabled toggle behavior - Hidden from Dashboard when disabled, shown in Manage for re-enabling

✅ Critical files - 15 files total (4 backend, 11 frontend)

✅ Verification plan - Backend tests + manual frontend testing checklist

✅ Clear implementation order - Reduces risk and ensures dependencies are met

The plan addresses all your requirements:

✅ Soft delete with deleted_at timestamp
✅ Enabled toggle (disabled = hidden from Dashboard, visible in Manage)
✅ Navbar extraction (eliminates 500+ lines of duplication)
✅ Search + filters matching Dashboard
✅ 10 servers per page pagination
✅ Direct save with toast notifications
✅ ID immutable after creation
Claude’s Plan
Implementation Plan: MCP Server Management Page
Context
FluidMCP currently lacks a centralized interface for managing MCP server configurations. Users cannot add, edit, or delete server configurations through the UI - they must manually edit configuration files or use CLI commands. This creates friction for:

Adding new servers: Users must understand the configuration format and manually create entries
Editing configurations: Requires stopping servers, editing files, and restarting - no validation or guidance
Removing servers: No soft delete capability means configurations are permanently lost
Discovery: No way to browse all configured servers with their full configurations
This implementation adds a /servers/manage page that provides CRUD operations for server configurations while respecting runtime constraints (cannot edit running servers, auto-stop before deletion).

Key User Decisions:

✅ No duplicate/clone feature in v1 (ship MVP first)
✅ Save directly without confirmation (toast notifications only)
✅ Search + filters matching Dashboard (all/running/stopped/error)
✅ 10 servers per page pagination
✅ Soft delete (set enabled=false + deleted_at timestamp)
✅ Enabled toggle behavior: Disabled servers hidden from Dashboard, shown in Manage page for re-enabling
Architecture Overview
Backend Status
APIs already exist in /workspaces/fluidmcp/fluidmcp/cli/api/management.py:

✅ POST /api/servers - Add server configuration (lines 363-435)
✅ PUT /api/servers/{id} - Update server (blocks if running, lines 486-557)
✅ DELETE /api/servers/{id} - Delete server (auto-stops if running, lines 560-615)
✅ GET /api/servers - List all servers with status (lines 438-452)
Backend Gap: DELETE does hard delete (permanent removal) instead of soft delete.

Frontend Status
❌ No Navbar component - 500+ lines duplicated across 5 pages
❌ No Manage page exists
❌ No CRUD API methods in services layer
✅ useServers() hook provides pattern to follow
✅ Status data included in GET /api/servers response (no separate call needed)
Implementation Phases
Phase 1: Backend - Soft Delete Implementation
1.1 Update Database Schema
File: /workspaces/fluidmcp/fluidmcp/cli/models/models.py (line 12-30)

Add soft delete timestamp to ServerConfigDocument:


@dataclass
class ServerConfigDocument:
    id: str
    name: str
    description: str = ""
    enabled: bool = True                     # Already exists (line 21)
    deleted_at: Optional[datetime] = None    # NEW: Soft delete timestamp
    # ... rest of existing fields
Rationale: Enables audit trails and future recovery without data loss.

1.2 Fix DatabaseManager List Method
File: /workspaces/fluidmcp/fluidmcp/cli/repositories/database.py (lines 444-465)

Current signature uses filter_dict but base interface expects enabled_only. Update to match interface:


async def list_server_configs(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
    """List server configurations with optional filtering."""
    query = {}

    # ALWAYS exclude soft-deleted servers
    query["deleted_at"] = {"$exists": False}

    # Additionally filter by enabled status if requested
    if enabled_only:
        query["enabled"] = True

    cursor = self.db.fluidmcp_servers.find(query, {"_id": 0})
    configs = await cursor.to_list(length=None)

    # Convert to flat format for backend compatibility
    return [self._flatten_config_for_backend(c) for c in configs]
Existing function to reuse: _flatten_config_for_backend() (already handles nested→flat conversion)

1.3 Add Soft Delete Method
File: /workspaces/fluidmcp/fluidmcp/cli/repositories/database.py

Add new method (place after delete_server_config around line 467):


async def soft_delete_server_config(self, id: str) -> bool:
    """Soft delete server by setting deleted_at timestamp."""
    result = await self.db.fluidmcp_servers.update_one(
        {"id": id, "deleted_at": {"$exists": False}},
        {
            "$set": {
                "deleted_at": datetime.utcnow(),
                "enabled": False,  # Also disable on deletion
                "updated_at": datetime.utcnow()
            }
        }
    )
    return result.modified_count > 0
1.4 Update DELETE Endpoint
File: /workspaces/fluidmcp/fluidmcp/cli/api/management.py (lines 560-616)

Replace hard delete with soft delete:


@router.delete("/servers/{id}")
async def delete_server(request, id, token, user_id):
    """Soft delete server configuration (preserves data)."""
    manager = get_server_manager(request)

    # Check server exists and not already deleted
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    if config.get("deleted_at"):
        raise HTTPException(410, f"Server '{id}' already deleted")

    # Auto-stop if running (existing behavior at line 600-603)
    if id in manager.processes:
        logger.info(f"Stopping server '{id}' before deletion...")
        await manager.stop_server(id)

    # Soft delete (replace line 606)
    success = await manager.db.soft_delete_server_config(id)
    if not success:
        raise HTTPException(500, "Failed to delete server")

    # Remove from in-memory cache
    if id in manager.configs:
        del manager.configs[id]

    logger.info(f"Soft deleted server: {id}")
    return {
        "message": f"Server '{id}' deleted successfully",
        "deleted_at": datetime.utcnow().isoformat()
    }
Existing function to reuse: manager.stop_server() (line 603)

1.5 Add Start Validation for Enabled Field
File: /workspaces/fluidmcp/fluidmcp/cli/api/management.py (line 620)

Add validation in start_server endpoint (after line 644):


# After checking if server exists (line 644)
if not config.get("enabled", True):
    raise HTTPException(403, f"Cannot start server '{id}': Server is disabled")
Phase 2: Frontend Infrastructure
2.1 Extract Reusable Navbar Component
New File: /workspaces/fluidmcp/fluidmcp/frontend/src/components/Navbar.tsx

Extract duplicated navigation code (~500 lines across 5 pages):


import { Link, useLocation } from 'react-router-dom';

interface NavbarProps {
  showAddButton?: boolean;
  onOpenAddDialog?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ showAddButton, onOpenAddDialog }) => {
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path;

  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
      <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
        <div className="flex items-center space-x-8">
          <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
            <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP</span>
          </Link>
          <nav className="hidden md:flex items-center space-x-1 text-sm">
            <Link to="/servers" className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white ${isActive('/servers') ? 'text-foreground' : 'text-foreground/60'}`}>
              Servers
            </Link>
            <Link to="/status" className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white ${isActive('/status') ? 'text-foreground' : 'text-foreground/60'}`}>
              Status
            </Link>
            <Link to="/servers/manage" className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white ${isActive('/servers/manage') ? 'text-foreground' : 'text-foreground/60'}`}>
              Manage
            </Link>
            <Link to="/documentation" className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white ${isActive('/documentation') ? 'text-foreground' : 'text-foreground/60'}`}>
              Documentation
            </Link>
          </nav>
        </div>
        <div className="flex items-center space-x-3">
          {showAddButton && onOpenAddDialog && (
            <button onClick={onOpenAddDialog} className="inline-flex items-center bg-black text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-zinc-900">
              + Add Server
            </button>
          )}
          <button className="inline-flex items-center bg-black text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-zinc-900">
            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
            Fluid MCP for your Enterprise
          </button>
        </div>
      </div>
    </header>
  );
};
Pattern reference: /workspaces/fluidmcp/fluidmcp/frontend/src/components/Footer.tsx - shows good reusable component pattern

Files to update (replace inline navbar with <Navbar />):

/workspaces/fluidmcp/fluidmcp/frontend/src/pages/Dashboard.tsx (lines 119-327)
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/Status.tsx
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/Documentation.tsx
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/ServerDetails.tsx
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/ToolRunner.tsx
2.2 Extend API Service Layer
File: /workspaces/fluidmcp/fluidmcp/frontend/src/services/api.ts

Add CRUD methods to ApiClient class (after line 150):


// Server Configuration Management
async addServer(config: ServerConfig): Promise<{ message: string; id: string; name: string }> {
  return this.request('/api/servers', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

async updateServer(serverId: string, config: Partial<ServerConfig>): Promise<{ message: string; config: any }> {
  return this.request(`/api/servers/${serverId}`, {
    method: 'PUT',
    body: JSON.stringify(config),
  });
}

async deleteServer(serverId: string): Promise<{ message: string; deleted_at: string }> {
  return this.request(`/api/servers/${serverId}`, {
    method: 'DELETE',
  });
}
Existing pattern to follow: Lines 101-111 show existing lifecycle methods (startServer, stopServer, restartServer)

2.3 Update Type Definitions
File: /workspaces/fluidmcp/fluidmcp/frontend/src/types/server.ts

Add deleted_at to Server interface (after line 40):


export interface Server {
  id: string;
  name: string;
  description?: string;
  config: ServerConfig;
  enabled: boolean;
  deleted_at?: string;  // NEW: Soft delete timestamp
  status?: ServerStatus;
  tools?: Tool[];
  created_at?: string;
  updated_at?: string;
  restart_policy?: string | null;
  max_restarts?: number | null;
}
Phase 3: Frontend Components
3.1 Server Management Hook
New File: /workspaces/fluidmcp/fluidmcp/frontend/src/hooks/useServerManagement.ts

Follow pattern from /workspaces/fluidmcp/fluidmcp/frontend/src/hooks/useServers.ts:


import { useState, useEffect, useCallback } from 'react';
import apiClient from '../services/api';
import { Server } from '../types/server';
import { showSuccess, showError } from '../services/toast';

export function useServerManagement() {
  const [servers, setServers] = useState<Server[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchServers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.listServers();
      setServers(response.servers);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load servers';
      setError(message);
      showError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const createServer = useCallback(async (config: any) => {
    try {
      await apiClient.addServer(config);
      showSuccess(`Server '${config.name}' created successfully`);
      await fetchServers();
      return true;
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to create server');
      return false;
    }
  }, [fetchServers]);

  const updateServer = useCallback(async (serverId: string, config: any) => {
    try {
      await apiClient.updateServer(serverId, config);
      showSuccess('Server updated successfully');
      await fetchServers();
      return true;
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to update server');
      return false;
    }
  }, [fetchServers]);

  const deleteServer = useCallback(async (serverId: string, serverName: string) => {
    try {
      await apiClient.deleteServer(serverId);
      showSuccess(`Server '${serverName}' deleted successfully`);
      await fetchServers();
      return true;
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to delete server');
      return false;
    }
  }, [fetchServers]);

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  return {
    servers,
    loading,
    error,
    refetch: fetchServers,
    createServer,
    updateServer,
    deleteServer,
  };
}
Pattern reference: /workspaces/fluidmcp/fluidmcp/frontend/src/hooks/useServers.ts - similar data fetching and action pattern

3.2 Server Form Component
New File: /workspaces/fluidmcp/fluidmcp/frontend/src/components/ServerForm.tsx

Reusable form for both create and edit:


import React, { useState } from 'react';

interface ServerFormProps {
  mode: 'create' | 'edit';
  initialData?: any;
  onSubmit: (data: any) => Promise<boolean>;
  onCancel: () => void;
}

export const ServerForm: React.FC<ServerFormProps> = ({ mode, initialData, onSubmit, onCancel }) => {
  const [formData, setFormData] = useState({
    id: initialData?.id || '',
    name: initialData?.name || '',
    command: initialData?.config?.command || '',
    args: initialData?.config?.args?.join(' ') || '',
    env: Object.entries(initialData?.config?.env || {}).map(([k, v]) => `${k}=${v}`).join('\n'),
    enabled: initialData?.enabled ?? true,
  });

  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate ID format (lowercase alphanumeric + hyphens)
    if (mode === 'create') {
      const idRegex = /^[a-z0-9-]+$/;
      if (!idRegex.test(formData.id)) {
        alert('Server ID must contain only lowercase letters, numbers, and hyphens');
        return;
      }
      if (formData.id.startsWith('-') || formData.id.endsWith('-')) {
        alert('Server ID cannot start or end with a hyphen');
        return;
      }
    }

    // Parse args and env
    const args = formData.args.trim() ? formData.args.trim().split(/\s+/) : [];
    const env: Record<string, string> = {};
    formData.env.split('\n').forEach(line => {
      const [key, ...valueParts] = line.split('=');
      if (key && valueParts.length > 0) {
        env[key.trim()] = valueParts.join('=').trim();
      }
    });

    setSubmitting(true);
    const success = await onSubmit({
      id: formData.id,
      name: formData.name,
      command: formData.command,
      args,
      env,
      enabled: formData.enabled,
    });
    setSubmitting(false);

    if (success) {
      onCancel();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Server ID */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Server ID *</label>
        <input
          type="text"
          value={formData.id}
          onChange={(e) => setFormData({ ...formData, id: e.target.value.toLowerCase() })}
          disabled={mode === 'edit'}
          className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          placeholder="my-server-id"
          required
        />
        <p className="mt-1 text-xs text-gray-500">
          Lowercase letters, numbers, hyphens only. Cannot be changed after creation.
        </p>
      </div>

      {/* Server Name */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Display Name *</label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          placeholder="My Server"
          required
        />
      </div>

      {/* Command */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Command *</label>
        <input
          type="text"
          value={formData.command}
          onChange={(e) => setFormData({ ...formData, command: e.target.value })}
          className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          placeholder="npx"
          required
        />
        <p className="mt-1 text-xs text-gray-500">Allowed: npx, node, python, python3, uvx, docker</p>
      </div>

      {/* Arguments */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Arguments</label>
        <input
          type="text"
          value={formData.args}
          onChange={(e) => setFormData({ ...formData, args: e.target.value })}
          className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          placeholder="-y @modelcontextprotocol/server-filesystem /tmp"
        />
      </div>

      {/* Environment Variables */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Environment Variables</label>
        <textarea
          value={formData.env}
          onChange={(e) => setFormData({ ...formData, env: e.target.value })}
          className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 font-mono text-sm"
          rows={4}
          placeholder="API_KEY=your-key&#10;DEBUG=true"
        />
        <p className="mt-1 text-xs text-gray-500">One per line in KEY=value format</p>
      </div>

      {/* Enabled Toggle */}
      <div className="flex items-center space-x-3">
        <input
          type="checkbox"
          id="enabled"
          checked={formData.enabled}
          onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
          className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
        />
        <label htmlFor="enabled" className="text-sm font-medium text-gray-700">
          Enabled (Disabled servers are hidden from Dashboard and cannot be started)
        </label>
      </div>

      {/* Actions */}
      <div className="flex justify-end space-x-3 pt-4 border-t">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          disabled={submitting}
        >
          {submitting ? 'Saving...' : mode === 'create' ? 'Create Server' : 'Save Changes'}
        </button>
      </div>
    </form>
  );
};
Key validation: ID format matches backend regex ^[a-z0-9-]+$ (from management.py line 269)

3.3 Main Management Page
New File: /workspaces/fluidmcp/fluidmcp/frontend/src/pages/ManageServers.tsx


import React, { useState } from 'react';
import { Navbar } from '../components/Navbar';
import { ServerForm } from '../components/ServerForm';
import { useServerManagement } from '../hooks/useServerManagement';
import { Pagination } from '../components/Pagination';

type FilterMode = 'all' | 'running' | 'stopped' | 'error';

export default function ManageServers() {
  const { servers, loading, createServer, updateServer, deleteServer } = useServerManagement();

  const [showForm, setShowForm] = useState(false);
  const [editingServer, setEditingServer] = useState<any>(null);
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

  const handleCreate = () => {
    setEditingServer(null);
    setShowForm(true);
  };

  const handleEdit = (server: any) => {
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

  const handleDelete = async (server: any) => {
    const message = server.status?.state === 'running'
      ? `Server '${server.name}' is running. It will be stopped and deleted. Continue?`
      : `Delete server '${server.name}'? This action cannot be undone.`;

    if (!confirm(message)) return;

    await deleteServer(server.id, server.name);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <div style={{ paddingTop: '64px' }} className="max-w-7xl mx-auto px-6 py-8">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Manage Servers</h1>
          <p className="mt-2 text-gray-600">
            Create, edit, and delete server configurations
          </p>
        </header>

        {/* Controls */}
        <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
          <div className="flex items-center justify-between">
            <input
              type="text"
              placeholder="Search by name or ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 max-w-md px-4 py-2 border rounded-lg"
            />

            <div className="flex items-center space-x-2">
              {(['all', 'running', 'stopped', 'error'] as FilterMode[]).map(mode => (
                <button
                  key={mode}
                  onClick={() => setFilterMode(mode)}
                  className={`px-3 py-1 text-sm rounded-lg capitalize ${
                    filterMode === mode ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>

            <button
              onClick={handleCreate}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              + Add Server
            </button>
          </div>
        </div>

        {/* Form Dialog */}
        {showForm && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6">
              <h2 className="text-2xl font-bold mb-6">
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

        {/* Server Table */}
        {loading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : filteredServers.length === 0 ? (
          <div className="bg-white rounded-lg p-12 text-center">
            <p className="text-gray-600">No servers found</p>
          </div>
        ) : (
          <>
            <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Server</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Command</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {paginatedServers.map(server => {
                    const isRunning = server.status?.state === 'running';
                    const statusColor = isRunning ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800';

                    return (
                      <tr key={server.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4">
                          <div className="text-sm font-medium text-gray-900">{server.name}</div>
                          <div className="text-xs text-gray-500 font-mono">{server.id}</div>
                        </td>
                        <td className="px-6 py-4">
                          <code className="text-xs bg-gray-100 px-2 py-1 rounded">
                            {server.config?.command} {server.config?.args?.join(' ').substring(0, 40)}
                          </code>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusColor}`}>
                            {server.status?.state || 'unknown'}
                          </span>
                          {!server.enabled && (
                            <span className="ml-2 text-xs text-gray-500 italic">(Disabled)</span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex space-x-2">
                            <button
                              onClick={() => handleEdit(server)}
                              disabled={isRunning}
                              className={`px-3 py-1 text-sm rounded-lg ${
                                isRunning
                                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                  : 'bg-blue-50 text-blue-700 hover:bg-blue-100'
                              }`}
                              title={isRunning ? 'Cannot edit while running' : 'Edit server'}
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleDelete(server)}
                              className="px-3 py-1 text-sm rounded-lg bg-red-50 text-red-700 hover:bg-red-100"
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
      </div>
    </div>
  );
}
Existing component to reuse: /workspaces/fluidmcp/fluidmcp/frontend/src/components/Pagination.tsx - already handles pagination UI

Phase 4: Integration
4.1 Add Route to App
File: /workspaces/fluidmcp/fluidmcp/frontend/src/App.tsx (line 20-27)

Add route:


<Routes>
  <Route path="/" element={<Dashboard />} />
  <Route path="/servers" element={<Dashboard />} />
  <Route path="/status" element={<Status />} />
  <Route path="/servers/manage" element={<ManageServers />} />  {/* NEW */}
  <Route path="/documentation" element={<Documentation />} />
  <Route path="/servers/:serverId" element={<ServerDetails />} />
  <Route path="/servers/:serverId/tools/:toolName" element={<ToolRunner />} />
  <Route path="*" element={<Navigate to="/" />} />
</Routes>
Enabled Field Behavior (Confirmed)
When enabled = true:

Server appears on Dashboard
Server can be started/stopped via runtime controls
Fully functional in all contexts
When enabled = false:

✅ Hidden from Dashboard (backend filters with enabled_only=true when Dashboard fetches)
✅ Shown in Manage page (allows users to re-enable)
❌ Cannot be started (backend blocks with 403 error)
Use case: "Pause" state without data loss
When deleted_at is set:

❌ Hidden everywhere (soft-deleted, future admin recovery)
Both enabled=false AND deleted_at set on deletion
Verification Plan
Backend Testing
File: /workspaces/fluidmcp/tests/test_server_management.py (new)

Test cases:

Soft delete sets deleted_at + enabled=false
list_server_configs() excludes soft-deleted servers
Cannot start server with enabled=false (403 error)
Cannot edit running server (409 error)
Auto-stop before deletion works
ID validation regex enforcement
Manual Frontend Testing
Create flow:

Valid ID (lowercase-alphanumeric-hyphens) → Success
Invalid ID (uppercase, special chars) → Error
Duplicate ID → Backend error shown
Edit flow:

Edit stopped server → Success
Try editing running server → Button disabled with tooltip
ID field disabled (immutable)
Delete flow:

Delete stopped server → Confirmation, then soft delete
Delete running server → Special warning about auto-stop
Enabled toggle:

Disable server → Disappears from Dashboard, stays in Manage
Enable server → Reappears on Dashboard
Search/Filter:

Search by name and ID
Filter by all/running/stopped/error
Pagination with 10+ servers
Navbar:

All 5 pages show consistent navigation
Active link highlighting works
"Manage" link added to all pages
Integration Testing
Create server in Manage → Verify appears on Dashboard
Disable server in Manage → Verify hidden from Dashboard
Start server on Dashboard → Edit button disabled in Manage
Delete server in Manage → Verify removed from Dashboard
Critical Files Summary
Backend (4 files):
/workspaces/fluidmcp/fluidmcp/cli/models/models.py - Add deleted_at field
/workspaces/fluidmcp/fluidmcp/cli/repositories/database.py - Implement soft delete logic
/workspaces/fluidmcp/fluidmcp/cli/api/management.py - Convert DELETE to soft delete, add validation
Frontend (6 files):
/workspaces/fluidmcp/fluidmcp/frontend/src/components/Navbar.tsx - NEW reusable component
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/ManageServers.tsx - NEW management page
/workspaces/fluidmcp/fluidmcp/frontend/src/components/ServerForm.tsx - NEW form component
/workspaces/fluidmcp/fluidmcp/frontend/src/hooks/useServerManagement.ts - NEW hook
/workspaces/fluidmcp/fluidmcp/frontend/src/services/api.ts - Add CRUD methods
/workspaces/fluidmcp/fluidmcp/frontend/src/types/server.ts - Add deleted_at field
/workspaces/fluidmcp/fluidmcp/frontend/src/App.tsx - Add route
Updates (5 files):
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/Dashboard.tsx - Replace navbar
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/Status.tsx - Replace navbar
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/Documentation.tsx - Replace navbar
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/ServerDetails.tsx - Replace navbar
/workspaces/fluidmcp/fluidmcp/frontend/src/pages/ToolRunner.tsx - Replace navbar
Implementation Order
Backend soft delete (Phase 1) - Foundational change, must be tested first
Navbar extraction (Phase 2.1) - Removes duplication, needed by all pages including Manage
API + types (Phase 2.2-2.3) - Infrastructure for management operations
Management page components (Phase 3) - Build on infrastructure
Integration (Phase 4) - Wire everything together
Testing (verification) - Validate end-to-end
Estimated Complexity: Medium-High (backend changes + significant frontend work)
Risk Areas: Soft delete migration (ensure no data loss), navbar extraction (update 5 pages consistently)