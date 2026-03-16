import type {
  ServersListResponse,
  ServerDetailsResponse,
  ServerStatus,
  ToolsResponse,
  ToolExecutionRequest,
  ToolExecutionResponse,
  ApiError,
  ServerEnvMetadataResponse,
  UpdateEnvResponse,
  CloneFromGithubRequest,
  CloneFromGithubResponse,
} from '../types/server';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || window.location.origin;

/** Error subclass that preserves the HTTP status code from API responses. */
export class ApiHttpError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiHttpError';
    this.status = status;
  }
}

/**
 * Merges multiple AbortSignals into one
 * If any signal aborts, the returned signal aborts
 */
function mergeAbortSignals(...signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController();

  signals.forEach(signal => {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener('abort', () => controller.abort(), { once: true });
    }
  });

  return controller.signal;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options?: RequestInit & { signal?: AbortSignal }
  ): Promise<T> {
    // DEBUG: Log all cookies before request
    console.log('[API Debug] All cookies:', document.cookie);
    console.log('[API Debug] Request:', {
      endpoint,
      method: options?.method || 'GET',
      credentials: 'include',
      baseUrl: this.baseUrl
    });

    // Create timeout controller (30 seconds default)
    const timeoutController = new AbortController();
    const timeoutId = setTimeout(() => timeoutController.abort(), 30000);

    // Merge external signal with timeout signal (if provided)
    const signal = options?.signal
      ? mergeAbortSignals(options.signal, timeoutController.signal)
      : timeoutController.signal;

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        credentials: 'include', // IMPORTANT: Send httpOnly cookies with all requests
        ...options,
        signal,
      });

      clearTimeout(timeoutId);

      // DEBUG: Log response details
      console.log('[API Debug] Response:', {
        endpoint,
        status: response.status,
        statusText: response.statusText,
        ok: response.ok
      });

      if (!response.ok) {
        const error: ApiError = await response.json().catch(() => ({
          detail: `HTTP ${response.status}: ${response.statusText}`,
        }));
        console.error('[API Debug] Error response:', error);
        throw new Error(error.detail);
      }

      return response.json();
    } catch (err) {
      clearTimeout(timeoutId);
      console.error('[API Debug] Request failed:', err);

      // Handle timeout errors specifically
      if (err instanceof Error && err.name === 'AbortError') {
        throw new Error('Request timeout - please try again');
      }

      throw err;
    }
  }

  // Server Management APIs
  async listServers(options?: { signal?: AbortSignal; enabled_only?: boolean; include_deleted?: boolean }): Promise<ServersListResponse> {
    const enabled_only = options?.enabled_only ?? true;
    const include_deleted = options?.include_deleted ?? false;
    const url = `/api/servers?enabled_only=${enabled_only}&include_deleted=${include_deleted}`;
    return this.request<ServersListResponse>(url, options);
  }

  async getServerDetails(serverId: string, options?: { signal?: AbortSignal }): Promise<ServerDetailsResponse> {
    return this.request<ServerDetailsResponse>(`/api/servers/${serverId}`, options);
  }

  async getServerStatus(serverId: string, options?: { signal?: AbortSignal }): Promise<ServerStatus> {
    return this.request<ServerStatus>(`/api/servers/${serverId}/status`, options);
  }

  async startServer(serverId: string): Promise<{ message: string; pid: number }> {
    return this.request(`/api/servers/${serverId}/start`, { method: 'POST' });
  }

  async stopServer(serverId: string): Promise<{ message: string; forced: boolean }> {
    return this.request(`/api/servers/${serverId}/stop`, { method: 'POST' });
  }

  async restartServer(serverId: string): Promise<{ message: string; pid: number }> {
    return this.request(`/api/servers/${serverId}/restart`, { method: 'POST' });
  }

  // Tool Discovery & Execution APIs
  async getServerTools(serverId: string, options?: { signal?: AbortSignal }): Promise<ToolsResponse> {
    return this.request<ToolsResponse>(`/api/servers/${serverId}/tools`, options);
  }

  async runTool(
    serverId: string,
    toolName: string,
    params: ToolExecutionRequest
  ): Promise<ToolExecutionResponse> {
    return this.request<ToolExecutionResponse>(
      `/api/servers/${serverId}/tools/${toolName}/run`,
      {
        method: 'POST',
        body: JSON.stringify(params),
      }
    );
  }

  // Server Logs API
  async getServerLogs(serverId: string, lines = 100, options?: { signal?: AbortSignal }): Promise<any> {
    return this.request(`/api/servers/${serverId}/logs?lines=${lines}`, options);
  }

  // Environment Variables APIs
  async getServerInstanceEnv(serverId: string, options?: { signal?: AbortSignal }): Promise<ServerEnvMetadataResponse> {
    return this.request<ServerEnvMetadataResponse>(`/api/servers/${serverId}/instance/env`, options);
  }

  async updateServerInstanceEnv(serverId: string, env: Record<string, string>): Promise<UpdateEnvResponse> {
    return this.request<UpdateEnvResponse>(
      `/api/servers/${serverId}/instance/env`,
      {
        method: 'PUT',
        body: JSON.stringify(env),
      }
    );
  }

  // Authentication APIs
  async getAuthConfig(options?: { signal?: AbortSignal }): Promise<any> {
    return this.request('/auth/config', options);
  }

  async getCurrentUser(options?: { signal?: AbortSignal }): Promise<any> {
    return this.request('/auth/me', options);
  }

  async logout(): Promise<void> {
    return this.request('/auth/logout', { method: 'POST' });
  }

  /**
   * Clone a GitHub repository and register its MCP server(s).
   *
   * The GitHub token is sent in the X-GitHub-Token header (never the body)
   * and a 120-second timeout is used since cloning large repos can be slow.
   */
  async cloneFromGithub(
    payload: CloneFromGithubRequest,
    githubToken: string
  ): Promise<CloneFromGithubResponse> {
    // Override the built-in 30s timeout — cloning can take up to ~60s
    const timeoutController = new AbortController();
    const timeoutId = setTimeout(() => timeoutController.abort(), 120_000);

    try {
      const response = await fetch(`${this.baseUrl}/api/servers/from-github`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-GitHub-Token': githubToken,
        },
        body: JSON.stringify(payload),
        signal: timeoutController.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const error = await response.json().catch(() => ({
          detail: `HTTP ${response.status}: ${response.statusText}`,
        }));
        throw new ApiHttpError(
          error.detail ?? 'Clone failed',
          response.status,
        );
      }

      return response.json();
    } catch (err) {
      clearTimeout(timeoutId);
      if (err instanceof Error && err.name === 'AbortError') {
        throw new Error('Request timed out — cloning may still be in progress');
      }
      throw err;
    }
  }
}

export const apiClient = new ApiClient(BASE_URL);
export default apiClient;