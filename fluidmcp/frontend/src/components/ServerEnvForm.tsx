import React, { useState, useEffect, useRef } from 'react';
import type { ServerEnvMetadataResponse } from '../types/server';
import './ServerEnvForm.css';

interface ServerEnvFormProps {
  serverId: string;
  configEnv: Record<string, string>; // Template env from server config
  envMetadata: ServerEnvMetadataResponse; // Metadata from backend
  onSubmit: (env: Record<string, string>) => Promise<void>;
  onCancel?: () => void;
  serverState: string;
}

export const ServerEnvForm: React.FC<ServerEnvFormProps> = ({
  configEnv,
  envMetadata,
  onSubmit,
  onCancel,
  serverState,
}) => {
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showJsonModal, setShowJsonModal] = useState(false);
  const [jsonInput, setJsonInput] = useState('');
  const [jsonError, setJsonError] = useState('');
  const [jsonImportSummary, setJsonImportSummary] = useState<{ matched: number; skipped: number } | null>(null);
  const jsonTextareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Initialize form with empty values (never pre-populate for security)
  useEffect(() => {
    const initialValues: Record<string, string> = {};
    Object.keys(configEnv).forEach((key) => {
      initialValues[key] = '';
    });
    setFormValues(initialValues);
  }, [configEnv]);

  const handleInputChange = (key: string, value: string) => {
    setFormValues((prev) => ({
      ...prev,
      [key]: value,
    }));

    // Clear validation error for this field
    if (validationErrors[key]) {
      setValidationErrors((prev) => {
        const updated = { ...prev };
        delete updated[key];
        return updated;
      });
    }
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    Object.entries(formValues).forEach(([key, value]) => {
      const metadata = envMetadata[key];

      // Check required fields (only enforce if not already configured)
      // This allows "leave empty to keep current value" UX for existing values
      if (metadata?.required && !value && !metadata?.present) {
        errors[key] = 'This field is required';
      }

      // Check for null bytes
      if (value && value.includes('\x00')) {
        errors[key] = 'Value cannot contain null bytes';
      }

      // Check max length (10k chars)
      if (value && value.length > 10000) {
        errors[key] = 'Value is too long (max 10,000 characters)';
      }
    });

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);

    try {
      // Only send non-empty values to preserve existing secrets
      // Empty values are ignored intentionally - users cannot clear values once set
      // This is a security-first design to prevent accidental credential deletion
      // (Support for explicit clearing can be added in a future enhancement)
      const envToSubmit: Record<string, string> = {};
      Object.entries(formValues).forEach(([key, value]) => {
        if (value !== '') {
          envToSubmit[key] = value;
        }
      });

      await onSubmit(envToSubmit);
    } catch (error) {
      console.error('Failed to submit env variables:', error);
    } finally {
      setIsSubmitting(false);
    }
  };


  const extractEnvFromParsed = (parsed: any): Record<string, string> | null => {
    // Format 1: { mcpServers: { id: { env: {...} } } }
    if (parsed.mcpServers && typeof parsed.mcpServers === 'object') {
      const first = Object.values(parsed.mcpServers)[0] as any;
      return first?.env && typeof first.env === 'object' ? first.env : {};
    }
    // Format 2: { env: { KEY: VALUE } }
    if (parsed.env && typeof parsed.env === 'object' && !Array.isArray(parsed.env)) {
      return parsed.env;
    }
    // Format 3: flat { KEY: VALUE }
    if (typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed;
    }
    return null;
  };

  const applyEnvObject = (envObj: Record<string, string>) => {
    let matched = 0;
    let skipped = 0;
    const updates: Record<string, string> = {};
    Object.entries(envObj).forEach(([k, v]) => {
      if (k in formValues) {
        updates[k] = String(v);
        matched++;
      } else {
        skipped++;
      }
    });
    setFormValues(prev => ({ ...prev, ...updates }));
    setJsonImportSummary({ matched, skipped });
    if (matched > 0) {
      setTimeout(() => {
        setShowJsonModal(false);
        setJsonInput('');
        setJsonImportSummary(null);
      }, 1500);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setJsonError('');
    setJsonImportSummary(null);
    if (file.size > 1_000_000) {
      setJsonError('File too large. Max 1MB.');
      return;
    }
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target?.result as string);
        const envObj = extractEnvFromParsed(parsed);
        if (!envObj) {
          setJsonError('Could not extract environment variables from this file.');
          return;
        }
        // Show parsed content in textarea so user can review before applying
        setJsonInput(JSON.stringify(envObj, null, 2));
      } catch {
        setJsonError('Invalid JSON file. Please check the file and try again.');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleJsonImport = () => {
    setJsonError('');
    setJsonImportSummary(null);
    try {
      const parsed = JSON.parse(jsonInput);
      const envObj = extractEnvFromParsed(parsed);
      if (!envObj) {
        setJsonError('JSON must be an object of key-value pairs.');
        return;
      }
      applyEnvObject(envObj);
    } catch {
      setJsonError('Invalid JSON. Please check the format and try again.');
    }
  };

  const isSensitiveField = (key: string): boolean => {
    const lowerKey = key.toLowerCase();
    const sensitivePatterns = [
      'key', 'token', 'secret', 'password', 'credential',
      'apikey', 'api_key', 'auth', 'jwt', 'bearer',
      'private', 'passphrase', 'salt', 'hash'
    ];

    // Check if field name ends with or contains sensitive keywords
    // This catches variations like: api_key_prod, database_token, oauth_secret_backup
    return sensitivePatterns.some(pattern =>
      lowerKey.endsWith(pattern) ||
      lowerKey.includes(`_${pattern}`) ||
      lowerKey.includes(`${pattern}_`)
    );
  };

  const envKeys = Object.keys(configEnv);

  if (envKeys.length === 0) {
    return null;
  }

  const isRunning = serverState === 'running';

  return (
    <div className="server-env-form">
      {/* JSON Import Modal */}
      {showJsonModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="relative bg-gradient-to-br from-zinc-900 to-zinc-800 border border-zinc-700 rounded-xl shadow-2xl w-full max-w-lg p-6">
            <button
              type="button"
              onClick={() => { setShowJsonModal(false); setJsonInput(''); setJsonError(''); setJsonImportSummary(null); }}
              className="absolute top-4 right-4 text-zinc-400 hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <h3 className="text-lg font-semibold text-white mb-1">Import from JSON</h3>
            <p className="text-xs text-zinc-400 mb-3">
              Paste or upload a JSON file. Supports flat <code className="font-mono">{"{ KEY: VALUE }"}</code>, <code className="font-mono">{"{ env: {...} }"}</code>, or full MCP config format. Only keys matching this server's config are applied.
            </p>

            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 mb-3 border-2 border-dashed border-zinc-600 rounded-lg text-zinc-400 hover:border-blue-500 hover:text-blue-400 transition-colors text-sm"
            >
              <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              Upload JSON file
            </button>

            <p className="text-xs text-zinc-500 mb-2">— or paste JSON below —</p>

            <textarea
              ref={jsonTextareaRef}
              value={jsonInput}
              onChange={e => { setJsonInput(e.target.value); setJsonError(''); setJsonImportSummary(null); }}
              placeholder={'{\n  "API_KEY": "sk_...",\n  "DB_URL": "postgresql://..."\n}'}
              rows={10}
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 text-zinc-200 placeholder-zinc-600 rounded-lg font-mono text-sm focus:outline-none focus:border-blue-500 resize-none"
            />

            {jsonError && (
              <p className="mt-2 text-xs text-red-400">{jsonError}</p>
            )}
            {jsonImportSummary && (
              <p className="mt-2 text-xs text-green-400">
                ✓ {jsonImportSummary.matched} field{jsonImportSummary.matched !== 1 ? 's' : ''} populated
                {jsonImportSummary.skipped > 0 && `, ${jsonImportSummary.skipped} unknown key${jsonImportSummary.skipped !== 1 ? 's' : ''} skipped`}
              </p>
            )}

            <div className="flex gap-3 mt-4">
              <button
                type="button"
                onClick={handleJsonImport}
                className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
              >
                Apply
              </button>
              <button
                type="button"
                onClick={() => { setShowJsonModal(false); setJsonInput(''); setJsonError(''); setJsonImportSummary(null); }}
                className="px-4 py-2 bg-zinc-700 text-zinc-300 text-sm font-medium rounded-lg hover:bg-zinc-600 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {/* JSON Import Button */}
        <div className="flex justify-end mb-4">
          <button
            type="button"
            onClick={() => { setShowJsonModal(true); setJsonError(''); setJsonImportSummary(null); setTimeout(() => jsonTextareaRef.current?.focus(), 50); }}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-zinc-300 bg-zinc-800 border border-zinc-700 rounded-lg hover:bg-zinc-700 hover:text-white transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Import from JSON
          </button>
        </div>

        <div className="env-fields">
          {envKeys.map((key) => {
            const metadata = envMetadata[key];
            const isConfigured = metadata?.present || false;
            const isSensitive = isSensitiveField(key);
            const error = validationErrors[key];

            return (
              <div key={key} className={`env-field ${error ? 'has-error' : ''}`}>
                <label htmlFor={`env-${key}`}>
                  {key}
                  {metadata?.required && <span className="required"> *</span>}
                  {isConfigured && (
                    <span className="configured-badge" title="Value is configured">
                      ✓ Configured
                    </span>
                  )}
                </label>

                {metadata?.description && (
                  <p className="field-description">{metadata.description}</p>
                )}

                <input
                  id={`env-${key}`}
                  type={isSensitive ? 'password' : 'text'}
                  value={formValues[key] || ''}
                  onChange={(e) => handleInputChange(key, e.target.value)}
                  placeholder={
                    isConfigured
                      ? 'Leave empty to keep current value'
                      : 'Enter value...'
                  }
                  className={error ? 'error' : ''}
                />

                {error && <p className="field-error">{error}</p>}
              </div>
            );
          })}
        </div>

        {isRunning && (
          <div className="restart-warning">
            <span className="warning-icon">⚠️</span>
            <span>Saving environment variables will restart this server.</span>
          </div>
        )}

        <div className="form-actions">
          <button
            type="submit"
            disabled={isSubmitting}
            className="submit-button"
          >
            {isSubmitting ? 'Saving...' : 'Save Environment Variables'}
          </button>

          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              disabled={isSubmitting}
              className="cancel-button"
            >
              Cancel
            </button>
          )}
        </div>
      </form>
    </div>
  );
};
