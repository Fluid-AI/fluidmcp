"""Data models for FluidMCP."""

from .server_status import ServerState, ServerStatus, RestartPolicy
from .models import ServerConfigDocument, ServerInstanceDocument, ServerLogDocument
from .api import (
    MCPConfigRequest,
    AddServerRequest,
    UpdateServerRequest,
    ServerStatusResponse,
    ServerConfigResponse,
    ServerListResponse,
    ToolExecutionRequest,
    ToolExecutionResponse,
    ErrorResponse
)

__all__ = [
    # Watchdog/monitoring models
    "ServerState",
    "ServerStatus",
    "RestartPolicy",
    # MongoDB document schemas
    "ServerConfigDocument",
    "ServerInstanceDocument",
    "ServerLogDocument",
    # API request/response models
    "MCPConfigRequest",
    "AddServerRequest",
    "UpdateServerRequest",
    "ServerStatusResponse",
    "ServerConfigResponse",
    "ServerListResponse",
    "ToolExecutionRequest",
    "ToolExecutionResponse",
    "ErrorResponse"
]
