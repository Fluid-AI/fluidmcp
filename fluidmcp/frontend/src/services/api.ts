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
} from '../types/server';
import type {
  LLMModelsListResponse,
  LLMModelDetailsResponse,
  LLMModelLogsResponse,
  LLMHealthCheckResponse,
  LLMModelRestartResponse,
  LLMModelStopResponse,
  ChatCompletionRequest,
  ChatCompletionResponse,
  ReplicateModelConfig,
} from '../types/llm';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || window.location.origin;

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

  // LLM Model Management APIs
  async listLLMModels(options?: { signal?: AbortSignal }): Promise<LLMModelsListResponse> {
    return this.request<LLMModelsListResponse>('/api/llm/models', options);
  }

  async getLLMModelDetails(modelId: string, options?: { signal?: AbortSignal }): Promise<LLMModelDetailsResponse> {
    return this.request<LLMModelDetailsResponse>(`/api/llm/models/${modelId}`, options);
  }

  async restartLLMModel(modelId: string): Promise<LLMModelRestartResponse> {
    return this.request<LLMModelRestartResponse>(`/api/llm/models/${modelId}/restart`, { method: 'POST' });
  }

  async stopLLMModel(modelId: string, force = false): Promise<LLMModelStopResponse> {
    return this.request<LLMModelStopResponse>(
      `/api/llm/models/${modelId}/stop?force=${force}`,
      { method: 'POST' }
    );
  }

  async getLLMModelLogs(
    modelId: string,
    lines = 100,
    options?: { signal?: AbortSignal }
  ): Promise<LLMModelLogsResponse> {
    return this.request<LLMModelLogsResponse>(`/api/llm/models/${modelId}/logs?lines=${lines}`, options);
  }

  async triggerLLMHealthCheck(modelId: string): Promise<LLMHealthCheckResponse> {
    return this.request<LLMHealthCheckResponse>(`/api/llm/models/${modelId}/health-check`, { method: 'POST' });
  }

  async chatCompletion(
    payload: ChatCompletionRequest,
    options?: { stream?: boolean; signal?: AbortSignal }
  ): Promise<ChatCompletionResponse> {
    const { stream = false, signal } = options || {};

    // Future-proof: structured for both streaming and non-streaming
    if (stream) {
      // TODO: Implement streaming with requestRaw when ready
      // return this.requestRaw('/api/llm/v1/chat/completions', { ... });
      throw new Error('Streaming not yet implemented');
    }

    // Non-streaming: use existing request method with full error handling, timeout, AbortController
    return this.request<ChatCompletionResponse>(
      '/api/llm/v1/chat/completions',
      {
        method: 'POST',
        body: JSON.stringify(payload),
        signal,
      }
    );
  }

  // LLM Model Management (CRUD)
  async createLLMModel(config: ReplicateModelConfig): Promise<{ message: string; model_id: string }> {
    return this.request('/api/llm/models', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async updateLLMModel(
    modelId: string,
    updates: Partial<Pick<ReplicateModelConfig, 'default_params' | 'timeout' | 'max_retries'>>
  ): Promise<{ message: string; model_id: string; updated_fields: string[] }> {
    return this.request(`/api/llm/models/${modelId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
  }

  async deleteLLMModel(modelId: string): Promise<{ message: string; model_id: string }> {
    return this.request(`/api/llm/models/${modelId}`, {
      method: 'DELETE',
    });
  }

  // Server Configuration Management (CRUD)
  async addServer(config: any): Promise<{ message: string; id: string; name: string }> {
    return this.request('/api/servers', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async updateServer(serverId: string, config: any): Promise<{ message: string; config: any }> {
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
}

export const apiClient = new ApiClient(BASE_URL);
export default apiClient;