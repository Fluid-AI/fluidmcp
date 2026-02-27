import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient, { ApiHttpError } from '../services/api';
import type { CloneFromGithubServerResult } from '../types/server';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Same slugify logic as the Python backend (ServerBuilder.slugify). */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[\s_]+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/** Derive a server-id suggestion from a repo path like "awslabs/mcp". */
function suggestServerId(repo: string): string {
  const cleaned = repo
    .replace(/^https?:\/\/github\.com\//i, '')
    .replace(/\.git$/, '');
  return slugify(cleaned);
}

/** Bump a trailing numeric suffix: "aws-docs" → "aws-docs-2", "aws-docs-2" → "aws-docs-3". */
function bumpServerId(id: string): string {
  const match = id.match(/^(.+)-(\d+)$/);
  if (match) {
    return `${match[1]}-${Number(match[2]) + 1}`;
  }
  return `${id}-2`;
}

// ─── Progress Steps ───────────────────────────────────────────────────────────

const PROGRESS_STEPS = [
  'Connecting to GitHub...',
  'Cloning repository...',
  'Extracting MCP configuration...',
  'Validating and registering...',
];

// Milliseconds to hold each step before advancing (last step waits for API)
const STEP_DURATIONS = [1200, 7000, 2000, Infinity];

// ─── Types ────────────────────────────────────────────────────────────────────

interface Props {
  onSuccess: () => void;   // called after clone+register so ManageServers can refetch
  onCancel: () => void;
}

type FormState = 'idle' | 'loading' | 'success' | 'error';

// ─── Component ────────────────────────────────────────────────────────────────

export function CloneFromGithubForm({ onSuccess, onCancel }: Props) {
  const navigate = useNavigate();

  // Form fields
  const [repo, setRepo] = useState('');
  const [branch, setBranch] = useState('main');
  const [serverId, setServerId] = useState('');
  const [serverIdTouched, setServerIdTouched] = useState(false);
  const [token, setToken] = useState('');
  const [subdirectory, setSubdirectory] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [envText, setEnvText] = useState('');

  // Validation errors
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Async state
  const [formState, setFormState] = useState<FormState>('idle');
  const [progressStep, setProgressStep] = useState(0);
  const [apiError, setApiError] = useState('');
  const [createdServers, setCreatedServers] = useState<CloneFromGithubServerResult[]>([]);
  const [startingId, setStartingId] = useState<string | null>(null);

  // Track whether progress timer should keep running
  const progressRunning = useRef(false);

  // ─── Auto-suggest server_id from repo ──────────────────────────────────────

  useEffect(() => {
    if (!serverIdTouched && repo.trim()) {
      setServerId(suggestServerId(repo.trim()));
    }
  }, [repo, serverIdTouched]);

  // ─── Progress animation ────────────────────────────────────────────────────

  useEffect(() => {
    if (formState !== 'loading') return;

    progressRunning.current = true;
    setProgressStep(0);

    let step = 0;

    const advance = () => {
      if (!progressRunning.current) return;
      const nextStep = step + 1;
      // Don't advance past the last finite step — the last step waits for the API
      if (nextStep < PROGRESS_STEPS.length - 1) {
        step = nextStep;
        setProgressStep(step);
        setTimeout(advance, STEP_DURATIONS[step]);
      }
    };

    setTimeout(advance, STEP_DURATIONS[0]);

    return () => {
      progressRunning.current = false;
    };
  }, [formState]);

  // ─── Validation ────────────────────────────────────────────────────────────

  function validate(): boolean {
    const errs: Record<string, string> = {};

    if (!repo.trim()) {
      errs.repo = 'GitHub repository is required';
    }

    if (!serverId.trim()) {
      errs.serverId = 'Server ID is required';
    } else if (!/^[a-z0-9-]+$/.test(serverId.trim())) {
      errs.serverId = 'Only lowercase letters, numbers, and hyphens';
    }

    if (!token.trim()) {
      errs.token = 'GitHub token is required';
    }

    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  // ─── Parse env textarea ────────────────────────────────────────────────────

  function parseEnv(text: string): Record<string, string> {
    const env: Record<string, string> = {};
    for (const line of text.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx > 0) {
        const key = trimmed.slice(0, eqIdx).trim();
        const value = trimmed.slice(eqIdx + 1).trim();
        if (key) env[key] = value;
      }
    }
    return env;
  }

  // ─── Submit ────────────────────────────────────────────────────────────────

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setFormState('loading');
    setApiError('');

    const env = parseEnv(envText);

    try {
      const result = await apiClient.cloneFromGithub(
        {
          github_repo: repo.trim(),
          branch: branch.trim() || 'main',
          server_id: serverId.trim(),
          subdirectory: subdirectory.trim() || undefined,
          env: Object.keys(env).length > 0 ? env : undefined,
          test_before_save: false,
        },
        token.trim()
      );

      // Jump to final progress step before showing success
      setProgressStep(PROGRESS_STEPS.length - 1);
      progressRunning.current = false;

      // Small delay so user sees the last step flash
      setTimeout(() => {
        setCreatedServers(result.servers);
        setFormState('success');
        // Clear the token immediately — never keep it in state longer than needed
        setToken('');
        // Notify parent to refetch server list
        onSuccess();
      }, 400);
    } catch (err) {
      progressRunning.current = false;

      if (err instanceof ApiHttpError && err.status === 409) {
        // Server ID already taken — bump the suffix and let the user retry
        const suggested = bumpServerId(serverId.trim());
        setServerId(suggested);
        setServerIdTouched(true);
        setApiError(
          `Server ID "${serverId.trim()}" is already taken. ` +
          `We've suggested "${suggested}" — hit Clone & Register to try again.`,
        );
      } else {
        setApiError(err instanceof Error ? err.message : 'Clone failed');
      }

      setFormState('error');
    }
  }

  // ─── Post-success: start a server ─────────────────────────────────────────

  async function handleStart(id: string) {
    setStartingId(id);
    try {
      await apiClient.startServer(id);
      onSuccess(); // refetch so status updates in table
    } catch (err) {
      // Ignore — user can start manually from manage page
    } finally {
      setStartingId(null);
    }
  }

  // ─── Render helpers ────────────────────────────────────────────────────────

  function inputClass(field: string) {
    return `w-full px-3 py-2 bg-zinc-800/50 border ${
      errors[field] ? 'border-red-500' : 'border-zinc-700'
    } text-white placeholder-zinc-400 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm`;
  }

  // ─── Loading view ──────────────────────────────────────────────────────────

  if (formState === 'loading') {
    return (
      <div className="py-8 flex flex-col items-center space-y-6">
        {/* Spinner */}
        <div className="relative">
          <div className="w-16 h-16 rounded-full border-4 border-zinc-700"></div>
          <div className="absolute inset-0 w-16 h-16 rounded-full border-4 border-blue-500 border-t-transparent animate-spin"></div>
        </div>

        {/* Steps */}
        <div className="w-full max-w-sm space-y-2">
          {PROGRESS_STEPS.map((step, i) => {
            const isDone = i < progressStep;
            const isActive = i === progressStep;
            return (
              <div
                key={step}
                className={`flex items-center space-x-3 text-sm transition-opacity duration-300 ${
                  isDone ? 'opacity-100' : isActive ? 'opacity-100' : 'opacity-30'
                }`}
              >
                {isDone ? (
                  <svg className="w-4 h-4 text-green-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : isActive ? (
                  <div className="w-4 h-4 shrink-0 rounded-full border-2 border-blue-400 border-t-transparent animate-spin" />
                ) : (
                  <div className="w-4 h-4 shrink-0 rounded-full border-2 border-zinc-600" />
                )}
                <span className={isDone ? 'text-zinc-400 line-through' : isActive ? 'text-white' : 'text-zinc-500'}>
                  {step}
                </span>
              </div>
            );
          })}
        </div>

        <p className="text-xs text-zinc-500">This may take up to 60 seconds for large repos</p>
      </div>
    );
  }

  // ─── Success view ──────────────────────────────────────────────────────────

  if (formState === 'success') {
    return (
      <div className="py-4 space-y-6">
        {/* Header */}
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-full bg-green-900/40 border border-green-500/30 flex items-center justify-center">
            <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div>
            <p className="text-white font-semibold">
              {createdServers.length === 1
                ? '1 server registered'
                : `${createdServers.length} servers registered`}
            </p>
            <p className="text-xs text-zinc-400">
              {createdServers[0]?.status === 'validated'
                ? 'Configuration validated via test-start'
                : 'Saved to database — start manually when ready'}
            </p>
          </div>
        </div>

        {/* Server list */}
        <div className="space-y-2">
          {createdServers.map((server) => (
            <div
              key={server.id}
              className="flex items-center justify-between bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-4 py-3"
            >
              <div>
                <p className="text-sm font-medium text-white">{server.name}</p>
                <p className="text-xs text-zinc-400 font-mono">{server.id}</p>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleStart(server.id)}
                  disabled={startingId === server.id}
                  className="px-3 py-1 text-xs bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-wait text-white rounded-lg transition-colors"
                >
                  {startingId === server.id ? 'Starting…' : 'Start'}
                </button>
                <button
                  onClick={() => navigate(`/servers/${server.id}`)}
                  className="px-3 py-1 text-xs bg-zinc-700 hover:bg-zinc-600 text-white rounded-lg transition-colors"
                >
                  View Details
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Done */}
        <div className="flex justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    );
  }

  // ─── Form (idle / error) ───────────────────────────────────────────────────

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>

      {/* API error banner */}
      {formState === 'error' && apiError && (
        <div className="flex items-start space-x-3 px-4 py-3 bg-red-900/30 border border-red-500/40 rounded-lg">
          <svg className="w-4 h-4 text-red-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-red-300">{apiError}</p>
        </div>
      )}

      {/* GitHub Repository */}
      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-1">
          GitHub Repository <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          placeholder="owner/repo  or  https://github.com/owner/repo"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          className={inputClass('repo')}
          autoComplete="off"
          spellCheck={false}
        />
        {errors.repo && <p className="mt-1 text-xs text-red-400">{errors.repo}</p>}
      </div>

      {/* Server ID + Branch row */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1">
            Server ID <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            placeholder="my-server"
            value={serverId}
            onChange={(e) => {
              setServerIdTouched(true);
              setServerId(e.target.value.toLowerCase());
            }}
            className={inputClass('serverId')}
            autoComplete="off"
            spellCheck={false}
          />
          {errors.serverId
            ? <p className="mt-1 text-xs text-red-400">{errors.serverId}</p>
            : <p className="mt-1 text-xs text-zinc-500">Lowercase, numbers, hyphens only</p>
          }
        </div>

        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1">Branch</label>
          <input
            type="text"
            placeholder="main"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            className={inputClass('branch')}
            autoComplete="off"
          />
        </div>
      </div>

      {/* GitHub Token */}
      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-1">
          GitHub Token <span className="text-red-400">*</span>
        </label>
        <input
          type="password"
          placeholder="ghp_… or github_pat_…"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className={inputClass('token')}
          autoComplete="new-password"
        />
        {errors.token
          ? <p className="mt-1 text-xs text-red-400">{errors.token}</p>
          : <p className="mt-1 text-xs text-zinc-500">Sent only in request header · never stored</p>
        }
      </div>

      {/* Subdirectory */}
      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-1">
          Subdirectory
          <span className="ml-1 text-xs text-zinc-500 font-normal">(optional)</span>
        </label>
        <input
          type="text"
          placeholder="src/aws-documentation-mcp-server"
          value={subdirectory}
          onChange={(e) => setSubdirectory(e.target.value)}
          className={inputClass('subdirectory')}
          autoComplete="off"
          spellCheck={false}
        />
        <p className="mt-1 text-xs text-zinc-500">
          For monorepos — specify the folder that contains <code className="text-zinc-400">metadata.json</code>
        </p>
      </div>

      {/* Advanced toggle */}
      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center space-x-1 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          <svg
            className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-90' : ''}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span>Advanced options</span>
        </button>

        {showAdvanced && (
          <div className="mt-3 space-y-4 pl-1">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">
                Extra Environment Variables
              </label>
              <textarea
                rows={4}
                placeholder={'API_KEY=your-value\nREGION=us-east-1'}
                value={envText}
                onChange={(e) => setEnvText(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-800/50 border border-zinc-700 text-white placeholder-zinc-500 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm font-mono resize-none"
                spellCheck={false}
              />
              <p className="mt-1 text-xs text-zinc-500">
                KEY=value, one per line. These merge on top of the repo's own defaults.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex justify-end space-x-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="px-5 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors inline-flex items-center space-x-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          <span>Clone &amp; Register</span>
        </button>
      </div>
    </form>
  );
}
