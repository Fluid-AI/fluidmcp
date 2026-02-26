// Type definitions for FluidMCP server data structures

export type ServerState = "running" | "stopped" | "failed" | "starting" | "restarting" | "not_found";

export interface ServerStatus {
  id: string;
  state: ServerState;
  pid?: number;
  uptime?: number;
  restart_count: number;
  exit_code?: number | null;
  env?: Record<string, string>; // Instance environment variables (for presence check)
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
  deleted_at?: string;             // Soft delete timestamp
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

// JSON Schema types for dynamic form generation
export interface JsonSchemaProperty {
  type: string;
  title?: string;
  description?: string;
  default?: any;
  enum?: any[];
  format?: string; // v1: only 'email' and 'url'
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  minItems?: number;
  maxItems?: number;
  items?: JsonSchemaProperty;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
}

export interface JsonSchema {
  type: string;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
  items?: JsonSchemaProperty;
  enum?: any[];
}

// Tool execution history for localStorage persistence
export interface ToolExecution {
  id: string;
  serverId: string;
  serverName: string;
  toolName: string;
  arguments: Record<string, any>;
  result: any;
  timestamp: string;
  success: boolean;
  error?: string;
  executionTime?: number;
}

// Environment variable metadata for instance configuration
export interface EnvMetadata {
  present: boolean;        // Has value in instance
  required: boolean;       // Required for server operation
  masked: string | null;   // Masked value ("****") if present
  description: string;     // Help text for user
}

export interface ServerEnvMetadataResponse {
  [key: string]: EnvMetadata;
}

export interface UpdateEnvResponse {
  message: string;
  env_updated: boolean;
}