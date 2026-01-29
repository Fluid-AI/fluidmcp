"""
MongoDB collection document schemas.

These dataclasses represent the actual structure stored in MongoDB collections.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class ServerConfigDocument:
    """
    Schema for fluidmcp_servers collection.

    Represents a server configuration stored in MongoDB.
    """
    id: str                                  # Unique server identifier
    name: str                                # Display name
    description: str = ""                    # Server description
    enabled: bool = True                     # Whether server is enabled
    mcp_config: Dict[str, Any] = field(default_factory=dict)  # Nested: {command, args, env}
    env_metadata: Optional[Dict[str, Dict[str, Any]]] = None  # Metadata for env vars: {var_name: {required, description}}
    restart_policy: str = "never"            # "never", "on-failure", "always"
    restart_window_sec: int = 300            # Restart time window
    max_restarts: int = 3                    # Max restart attempts
    tools: List[Dict[str, Any]] = field(default_factory=list)  # Cached tool schemas
    created_by: Optional[str] = None         # User who created config
    created_at: Optional[datetime] = None    # Creation timestamp
    updated_at: Optional[datetime] = None    # Last update timestamp


@dataclass
class ServerInstanceDocument:
    """
    Schema for fluidmcp_server_instances collection.

    Represents runtime state of a server instance.
    """
    server_id: str                           # Reference to server config
    state: str                               # "running", "stopped", "failed"
    pid: Optional[int] = None                # Process ID (None if stopped)
    start_time: Optional[datetime] = None    # When started
    stop_time: Optional[datetime] = None     # When stopped
    exit_code: Optional[int] = None          # Exit code if stopped
    restart_count: int = 0                   # Number of restarts
    last_health_check: Optional[datetime] = None  # Last health check
    health_check_failures: int = 0           # Consecutive failures
    host: str = "localhost"                  # Server host
    port: int = 8090                         # Server port
    last_error: Optional[str] = None         # Last error message
    started_by: str = "system"               # User who started instance
    updated_at: Optional[datetime] = None    # Last state update
    env: Optional[Dict[str, str]] = None     # Instance-specific environment variables


@dataclass
class ServerLogDocument:
    """
    Schema for fluidmcp_server_logs collection (capped).

    Represents a log entry from a server.
    """
    server_name: str                         # Server identifier
    timestamp: datetime                      # Log timestamp
    stream: str                              # "stdout" or "stderr"
    content: str                             # Log content
