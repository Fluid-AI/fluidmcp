// Type definitions for FluidMCP server data structures

export type ServerState = "running" | "stopped" | "failed" | "starting" | "restarting" | "not_found";

export interface ServerStatus {
  id: string;
  state: ServerState;
  pid?: number;
  uptime?: number;
  restart_count: number;
  exit_code?: number | null;
}

export interface Tool {
  name: string;
  description: string;
  inputSchema?: {
    type: string;
    properties: Record<string, any>;
    required?: string[];
  };
}

export interface ServerConfig {
  command: string;
  args: string[];
  env: Record<string, string>;
}

export interface Server {
  id: string;
  name: string;
  description?: string;
  config: ServerConfig;
  enabled: boolean;
  status?: ServerStatus;
  tools?: Tool[];
  created_at?: string;
  updated_at?: string;
  // Restart policy configuration
  restart_policy?: string | null;  // "on-failure" | "always" | null
  max_restarts?: number | null;    // Maximum restart attempts
  restart_window_sec?: number;     // Restart window in seconds
}

export interface ServersListResponse {
  servers: Server[];
  count: number;
}

export interface ServerDetailsResponse {
  id: string;
  name: string;
  description?: string;
  config: ServerConfig;
  status: ServerStatus;
  // Restart policy configuration
  restart_policy?: string | null;  // "on-failure" | "always" | null
  max_restarts?: number | null;    // Maximum restart attempts
  restart_window_sec?: number;     // Restart window in seconds
}

export interface ToolsResponse {
  server_id: string;
  tools: Tool[];
  count: number;
}

export interface ToolExecutionRequest {
  [key: string]: any;
}

export interface ToolExecutionResponse {
  result: any;
}

export interface ApiError {
  detail: string;
}
