// Type definitions for FluidMCP LLM model data structures

export type LLMModelType = "process" | "replicate";
export type LLMModelState = "running" | "stopped" | "starting" | "failed";

// Process-based model (vLLM, Ollama, LM Studio)
export interface ProcessBasedModel {
  id: string;
  type: "process";
  is_running: boolean;
  is_healthy: boolean;
  health_message: string;
  restart_policy: string;
  restart_count: number;
  max_restarts: number;
  consecutive_health_failures: number;
  uptime_seconds: number | null;
  last_restart_time: string | null;
  last_health_check_time: string | null;
  has_cuda_oom?: boolean;
}

// Cloud-based model (Replicate)
export interface ReplicateModel {
  id: string;
  type: "replicate";
  is_running: boolean;
  is_healthy: boolean;
  health_message: string;
  model: string;
  endpoint: string;
  timeout?: number;
  max_retries?: number;
}

export type LLMModel = ProcessBasedModel | ReplicateModel;

export interface LLMModelsListResponse {
  models: LLMModel[];
  total: number;
}

export type LLMModelDetailsResponse = LLMModel;

export interface LLMModelLogsResponse {
  model_id: string;
  lines: string[];
  total_lines?: number;
  returned_lines?: number;
  log_path?: string;
  message?: string;
}

export interface LLMHealthCheckResponse {
  model_id: string;
  is_healthy: boolean;
  health_message: string;
  consecutive_health_failures: number;
  last_health_check_time: string | null;
  has_cuda_oom?: boolean;
}

export interface LLMModelRestartResponse {
  message: string;
  restart_count: number;
  uptime_seconds: number | null;
}

export interface LLMModelStopResponse {
  message: string;
}

// Chat completion types
export interface ChatMessage {
  role: string;
  content: string;
}

export interface ChatCompletionRequest {
  model: string;
  messages: ChatMessage[];
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
}

export interface ChatCompletionResponse {
  choices: Array<{
    message: {
      role: string;
      content: string;
    };
    index?: number;
    finish_reason?: string;
  }>;
  model: string;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  id?: string;
  created?: number;
}

// Future-proof chat session structure for multi-model comparison
export interface ChatSession {
  modelId: string;
  messages: ChatMessage[];
  parameters: {
    temperature: number;
    max_tokens: number;
  };
}

// LLM Model Registration/Configuration
export interface ReplicateModelConfig {
  model_id: string;
  type: "replicate";
  model: string;
  api_key: string;
  default_params?: {
    temperature?: number;
    max_tokens?: number;
    top_p?: number;
    top_k?: number;
    stop?: string | string[];
    frequency_penalty?: number;
    presence_penalty?: number;
  };
  timeout?: number;
  max_retries?: number;
}

// Helper type guards
export function isProcessBasedModel(model: LLMModel): model is ProcessBasedModel {
  return model.type === "process";
}

export function isReplicateModel(model: LLMModel): model is ReplicateModel {
  return model.type === "replicate";
}
