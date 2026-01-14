"""
Pydantic models for REST API request/response validation.

These models define the structure of data sent to/from API endpoints.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class MCPConfigRequest(BaseModel):
    """MCP configuration within server config (nested structure)."""
    command: str = Field(..., description="Command to execute (e.g., 'npx', 'python')")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")

    class Config:
        json_schema_extra = {
            "example": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "env": {"NODE_ENV": "production"}
            }
        }


class AddServerRequest(BaseModel):
    """Request body for POST /api/servers."""
    id: str = Field(..., description="Unique server identifier", min_length=1, max_length=100)
    name: str = Field(..., description="Display name for the server", min_length=1, max_length=200)
    description: str = Field(default="", description="Server description", max_length=500)
    enabled: bool = Field(default=True, description="Whether server is enabled")
    mcp_config: MCPConfigRequest = Field(..., description="MCP server configuration")
    restart_policy: str = Field(
        default="never",
        description="Restart policy: never, on-failure, or always",
        pattern="^(never|on-failure|always)$"
    )
    restart_window_sec: int = Field(
        default=300,
        description="Restart time window in seconds",
        ge=0,
        le=3600
    )
    max_restarts: int = Field(
        default=3,
        description="Maximum restart attempts",
        ge=0,
        le=10
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "filesystem-server",
                "name": "Filesystem MCP Server",
                "description": "Provides filesystem access via MCP",
                "enabled": True,
                "mcp_config": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                    "env": {}
                },
                "restart_policy": "on-failure",
                "restart_window_sec": 300,
                "max_restarts": 3
            }
        }


class UpdateServerRequest(BaseModel):
    """Request body for PUT /api/servers/{id}."""
    name: Optional[str] = Field(None, description="Updated display name", min_length=1, max_length=200)
    description: Optional[str] = Field(None, description="Updated description", max_length=500)
    enabled: Optional[bool] = Field(None, description="Updated enabled status")
    mcp_config: Optional[MCPConfigRequest] = Field(None, description="Updated MCP configuration")
    restart_policy: Optional[str] = Field(
        None,
        description="Updated restart policy",
        pattern="^(never|on-failure|always)$"
    )
    restart_window_sec: Optional[int] = Field(
        None,
        description="Updated restart window",
        ge=0,
        le=3600
    )
    max_restarts: Optional[int] = Field(
        None,
        description="Updated max restarts",
        ge=0,
        le=10
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Filesystem Server",
                "enabled": False
            }
        }


class ServerStatusResponse(BaseModel):
    """Response body for GET /api/servers/{id}/status."""
    server_id: str = Field(..., description="Server identifier")
    state: str = Field(..., description="Current state: running, stopped, or failed")
    pid: Optional[int] = Field(None, description="Process ID if running")
    start_time: Optional[datetime] = Field(None, description="When server was started")
    uptime_seconds: Optional[float] = Field(None, description="Uptime in seconds")
    restart_count: int = Field(default=0, description="Number of restarts")
    last_error: Optional[str] = Field(None, description="Last error message if any")

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": "filesystem-server",
                "state": "running",
                "pid": 12345,
                "start_time": "2024-01-14T10:30:00Z",
                "uptime_seconds": 3600.5,
                "restart_count": 0,
                "last_error": None
            }
        }


class ServerConfigResponse(BaseModel):
    """Response body for GET /api/servers/{id}."""
    id: str
    name: str
    description: str
    enabled: bool
    mcp_config: Dict[str, Any]
    restart_policy: str
    restart_window_sec: int
    max_restarts: int
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ServerListResponse(BaseModel):
    """Response body for GET /api/servers."""
    servers: List[ServerConfigResponse] = Field(..., description="List of server configurations")
    total: int = Field(..., description="Total number of servers")

    class Config:
        json_schema_extra = {
            "example": {
                "servers": [
                    {
                        "id": "filesystem-server",
                        "name": "Filesystem MCP Server",
                        "description": "Provides filesystem access",
                        "enabled": True,
                        "mcp_config": {
                            "command": "npx",
                            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                            "env": {}
                        },
                        "restart_policy": "never",
                        "restart_window_sec": 300,
                        "max_restarts": 3,
                        "tools": [],
                        "created_by": None,
                        "created_at": "2024-01-14T10:00:00Z",
                        "updated_at": "2024-01-14T10:00:00Z"
                    }
                ],
                "total": 1
            }
        }


class ToolExecutionRequest(BaseModel):
    """Request body for POST /api/servers/{id}/tools/{tool_name}/run."""
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments as key-value pairs"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "arguments": {
                    "path": "/tmp/test.txt",
                    "content": "Hello world"
                }
            }
        }


class ToolExecutionResponse(BaseModel):
    """Response body for tool execution."""
    success: bool = Field(..., description="Whether tool execution succeeded")
    result: Optional[Dict[str, Any]] = Field(None, description="Tool execution result")
    error: Optional[str] = Field(None, description="Error message if execution failed")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "result": {
                    "status": "completed",
                    "output": "File written successfully"
                },
                "error": None
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str = Field(..., description="Error message")

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Server not found"
            }
        }
