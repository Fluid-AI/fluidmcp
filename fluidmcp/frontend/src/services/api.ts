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

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    // Add timeout using AbortController (30 seconds default)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
        signal: controller.signal,
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
  async listServers(): Promise<ServersListResponse> {
    return this.request<ServersListResponse>('/api/servers');
  }

  async getServerDetails(serverId: string): Promise<ServerDetailsResponse> {
    return this.request<ServerDetailsResponse>(`/api/servers/${serverId}`);
  }

  async getServerStatus(serverId: string): Promise<ServerStatus> {
    return this.request<ServerStatus>(`/api/servers/${serverId}/status`);
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
  async getServerTools(serverId: string): Promise<ToolsResponse> {
    return this.request<ToolsResponse>(`/api/servers/${serverId}/tools`);
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
  async getServerLogs(serverId: string, lines = 100): Promise<any> {
    return this.request(`/api/servers/${serverId}/logs?lines=${lines}`);
  }
}

export const apiClient = new ApiClient(BASE_URL);
export default apiClient;