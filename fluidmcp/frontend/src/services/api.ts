import type {
  ServersListResponse,
  ServerDetailsResponse,
  ServerStatus,
  ToolsResponse,
  ToolExecutionRequest,
  ToolExecutionResponse,
  ApiError,
} from '../types/server';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8099';

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
    // AbortController lifecycle is owned by hooks/components, not apiClient
    // This method accepts optional signal for request cancellation

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
        ...options,
        signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const error: ApiError = await response.json().catch(() => ({
          detail: `HTTP ${response.status}: ${response.statusText}`,
        }));
        throw new Error(error.detail);
      }

      return response.json();
    } catch (err) {
      clearTimeout(timeoutId);

      // Handle timeout errors specifically
      if (err instanceof Error && err.name === 'AbortError') {
        throw new Error('Request timeout - please try again');
      }

      throw err;
    }
  }

  // Server Management APIs
  async listServers(options?: { signal?: AbortSignal }): Promise<ServersListResponse> {
    return this.request<ServersListResponse>('/api/servers', options);
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
}

export const apiClient = new ApiClient(BASE_URL);
export default apiClient;