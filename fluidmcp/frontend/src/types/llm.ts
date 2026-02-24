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

// Helper type guards
export function isProcessBasedModel(model: LLMModel): model is ProcessBasedModel {
  return model.type === "process";
}

export function isReplicateModel(model: LLMModel): model is ReplicateModel {
  return model.type === "replicate";
}
