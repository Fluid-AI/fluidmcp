import { useState, useRef } from 'react';

interface ServerFormProps {
  mode: 'create' | 'edit';
  initialData?: any;
  existingIds?: string[];
  onSubmit: (data: any) => Promise<boolean>;
  onCancel: () => void;
}

export const ServerForm: React.FC<ServerFormProps> = ({ mode, initialData, existingIds = [], onSubmit, onCancel }) => {
  const [formData, setFormData] = useState({
    id: initialData?.id || '',
    name: initialData?.name || '',
    description: initialData?.description || '',
    command: initialData?.config?.command || '',
    args: initialData?.config?.args?.join(' ') || '',
    env: Object.entries(initialData?.config?.env || {}).map(([k, v]) => `${k}=${v}`).join('\n'),
    enabled: initialData?.enabled ?? true,
  });

  const [submitting, setSubmitting] = useState(false);
  const [jsonError, setJsonError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const idConflict = mode === 'create' && formData.id.length > 0 && existingIds.includes(formData.id);

  const handleJsonUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setJsonError('');

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target?.result as string);

        // Support two formats:
        // 1. { "mcpServers": { "server-id": { command, args, env, ... } } }
        // 2. Direct config: { command, args, env, id, name, description, ... }
        let serverId = '';
        let serverConfig: any = parsed;

        if (parsed.mcpServers && typeof parsed.mcpServers === 'object') {
          const entries = Object.entries(parsed.mcpServers);
          if (entries.length === 0) {
            setJsonError('No servers found in mcpServers object.');
            return;
          }
          [serverId, serverConfig] = entries[0] as [string, any];
        }

        const envEntries = Object.entries(serverConfig?.env || {})
          .map(([k, v]) => `${k}=${v}`)
          .join('\n');

        setFormData(prev => ({
          ...prev,
          id: (serverId || serverConfig?.id || prev.id).toLowerCase().replace(/[^a-z0-9-]/g, '-'),
          name: serverConfig?.name || prev.name,
          description: serverConfig?.description || prev.description,
          command: serverConfig?.command || prev.command,
          args: Array.isArray(serverConfig?.args) ? serverConfig.args.join(' ') : (serverConfig?.args || prev.args),
          env: envEntries,
        }));
      } catch {
        setJsonError('Invalid JSON file. Please check the file and try again.');
      }
    };
    reader.readAsText(file);
    // Reset input so the same file can be re-uploaded if needed
    e.target.value = '';
  };

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
      const trimmedLine = line.trim();
      if (trimmedLine) {
        const [key, ...valueParts] = trimmedLine.split('=');
        if (key && valueParts.length > 0) {
          env[key.trim()] = valueParts.join('=').trim();
        }
      }
    });

    const payload: any = {
      name: formData.name,
      description: formData.description,
      command: formData.command,
      args,
      env,
      enabled: formData.enabled,
    };

    // Include ID only for create mode
    if (mode === 'create') {
      payload.id = formData.id;
    }

    setSubmitting(true);
    const success = await onSubmit(payload);
    setSubmitting(false);

    if (success) {
      onCancel();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* JSON Upload — create mode only */}
      {mode === 'create' && (
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            onChange={handleJsonUpload}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="w-full flex items-center justify-center space-x-2 px-4 py-3 border-2 border-dashed border-zinc-600 rounded-lg text-zinc-400 hover:border-blue-500 hover:text-blue-400 transition-colors"
          >
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            <span className="text-sm font-medium">Upload JSON config to auto-fill</span>
          </button>
          {jsonError && (
            <p className="mt-1 text-xs text-red-400">{jsonError}</p>
          )}
          <p className="mt-1 text-xs text-zinc-500">
            Accepts MCP config format: <code className="font-mono">{"{ mcpServers: { id: { command, args, env } } }"}</code>
          </p>
        </div>
      )}

      {/* Server ID */}
      <div>
        <label className="block text-sm font-medium text-zinc-200 mb-2">
          Server ID *
        </label>
        <input
          type="text"
          value={formData.id}
          onChange={(e) => setFormData({ ...formData, id: e.target.value.toLowerCase() })}
          disabled={mode === 'edit'}
          className={`w-full px-3 py-2 bg-zinc-800/50 border text-white placeholder-zinc-400 rounded-lg focus:ring-2 disabled:bg-zinc-900/50 disabled:cursor-not-allowed disabled:text-zinc-500 ${
            idConflict
              ? 'border-red-500 focus:ring-red-500 focus:border-red-500'
              : 'border-zinc-700 focus:ring-blue-500 focus:border-blue-500'
          }`}
          placeholder="my-server-id"
          required
        />
        {idConflict ? (
          <p className="mt-1 text-xs text-red-400">
            A server with this ID already exists. Choose a different ID.
          </p>
        ) : (
          <p className="mt-1 text-xs text-zinc-400">
            Lowercase letters, numbers, hyphens only. Cannot be changed after creation.
          </p>
        )}
      </div>

      {/* Server Name */}
      <div>
        <label className="block text-sm font-medium text-zinc-200 mb-2">
          Display Name *
        </label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          className="w-full px-3 py-2 bg-zinc-800/50 border border-zinc-700 text-white placeholder-zinc-400 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          placeholder="My Server"
          required
        />
      </div>

      {/* Description */}
      <div>
        <label className="block text-sm font-medium text-zinc-200 mb-2">
          Description
        </label>
        <input
          type="text"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          className="w-full px-3 py-2 bg-zinc-800/50 border border-zinc-700 text-white placeholder-zinc-400 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          placeholder="Optional description"
        />
      </div>

      {/* Command */}
      <div>
        <label className="block text-sm font-medium text-zinc-200 mb-2">
          Command *
        </label>
        <input
          type="text"
          value={formData.command}
          onChange={(e) => setFormData({ ...formData, command: e.target.value })}
          className="w-full px-3 py-2 bg-zinc-800/50 border border-zinc-700 text-white placeholder-zinc-400 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          placeholder="npx"
          required
        />
        <p className="mt-1 text-xs text-zinc-400">
          Allowed: npx, node, python, python3, uvx, docker
        </p>
      </div>

      {/* Arguments */}
      <div>
        <label className="block text-sm font-medium text-zinc-200 mb-2">
          Arguments
        </label>
        <input
          type="text"
          value={formData.args}
          onChange={(e) => setFormData({ ...formData, args: e.target.value })}
          className="w-full px-3 py-2 bg-zinc-800/50 border border-zinc-700 text-white placeholder-zinc-400 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          placeholder="-y @modelcontextprotocol/server-filesystem /tmp"
        />
      </div>

      {/* Environment Variables */}
      <div>
        <label className="block text-sm font-medium text-zinc-200 mb-2">
          Environment Variables
        </label>
        <textarea
          value={formData.env}
          onChange={(e) => setFormData({ ...formData, env: e.target.value })}
          className="w-full px-3 py-2 bg-zinc-800/50 border border-zinc-700 text-white placeholder-zinc-400 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
          rows={4}
          placeholder="API_KEY=your-key&#10;DEBUG=true"
        />
        <p className="mt-1 text-xs text-zinc-400">
          One per line in KEY=value format
        </p>
      </div>

      {/* Enabled Toggle */}
      <div className="flex items-start space-x-3 p-4 bg-zinc-800/30 border border-zinc-700/50 rounded-lg">
        <input
          type="checkbox"
          id="enabled"
          checked={formData.enabled}
          onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
          className="mt-0.5 w-4 h-4 text-blue-600 bg-zinc-800 border-zinc-600 rounded focus:ring-blue-500 focus:ring-2"
        />
        <div className="flex-1">
          <label htmlFor="enabled" className="text-sm font-medium text-zinc-200 cursor-pointer">
            Enabled
          </label>
          <p className="text-xs text-zinc-400 mt-1">
            Disabled servers are hidden from Dashboard and cannot be started
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end space-x-3 pt-4 border-t border-zinc-700">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-zinc-300 bg-zinc-800 rounded-lg hover:bg-zinc-700 transition-colors"
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          disabled={submitting || idConflict}
        >
          {submitting ? 'Saving...' : mode === 'create' ? 'Create Server' : 'Save Changes'}
        </button>
      </div>
    </form>
  );
};
