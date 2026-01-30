"""
Management API endpoints for dynamic MCP server control.

Provides REST API for:
- Adding/removing server configurations
- Starting/stopping/restarting servers
- Querying server status and logs
- Listing all configured servers
"""
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException, Body, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
import os

router = APIRouter()
security = HTTPBearer(auto_error=False)


def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate bearer token if secure mode is enabled"""
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"

    if not secure_mode:
        return None
    if not credentials or credentials.scheme.lower() != "bearer" or credentials.credentials != bearer_token:
        raise HTTPException(status_code=401, detail="Invalid or missing authorization token")
    return credentials.credentials


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Extract user identifier from bearer token.

    For now, uses a simple approach:
    - In secure mode: Uses the token itself as user ID (simple but works)
    - In non-secure mode: Returns "anonymous"

    Future: Parse JWT tokens to extract user email/ID from claims

    Returns:
        User identifier string
    """
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"

    if not secure_mode:
        return "anonymous"

    if not credentials or not credentials.credentials:
        return "anonymous"

    # For now, use token as user ID (simple approach)
    # TODO: Implement proper JWT authentication with role claims
    # Current implementation uses first 8 chars of token (~33 bits entropy)
    # which is insufficient for production security. Replace with JWT decode
    # to extract user_id/email/role claims.
    token = credentials.credentials

    # Simple user extraction: use first 8 chars of token as user ID
    # This ensures different tokens = different users but provides weak security
    user_id = f"user_{token[:8]}"

    return user_id


def get_server_manager(request: Request):
    """Dependency injection for ServerManager."""
    if not hasattr(request.app.state, "server_manager"):
        raise HTTPException(500, "ServerManager not initialized")
    return request.app.state.server_manager


def sanitize_input(value: Any) -> Any:
    """
    Sanitize user input to prevent MongoDB injection attacks.

    Removes MongoDB operators and special characters from input.

    Args:
        value: Input value to sanitize

    Returns:
        Sanitized value
    """
    if isinstance(value, str):
        # Remove MongoDB operator prefixes
        if value.startswith("$"):
            value = value.lstrip("$")
        # Remove braces that could be part of injection attempts
        value = value.replace("{", "").replace("}", "")
    elif isinstance(value, dict):
        # Recursively sanitize dictionary values
        return {k: sanitize_input(v) for k, v in value.items()}
    elif isinstance(value, list):
        # Recursively sanitize list items
        return [sanitize_input(item) for item in value]
    return value


def validate_server_config(config: Dict[str, Any]) -> None:
    """
    Validate server configuration to prevent command injection and ensure safety.

    Args:
        config: Server configuration dict

    Raises:
        HTTPException: If validation fails
    """
    import re

    # Validate required fields
    if "command" not in config:
        raise HTTPException(400, "Server configuration must include 'command' field")

    command = config["command"]

    # Command path validation - reject absolute paths
    if os.path.isabs(command):
        raise HTTPException(
            400,
            f"Absolute paths not allowed in command field. Use command name only: {command}"
        )

    # Command must not contain path separators
    if "/" in command or "\\" in command:
        raise HTTPException(
            400,
            f"Command must be a simple command name without path separators: {command}"
        )

    # Whitelist of allowed commands (can be extended via environment variable)
    allowed_commands_default = ["npx", "node", "python", "python3", "uvx", "docker"]
    allowed_commands_env = os.environ.get("FMCP_ALLOWED_COMMANDS", "").split(",")
    allowed_commands = allowed_commands_default + [cmd.strip() for cmd in allowed_commands_env if cmd.strip()]

    # Check if command is in whitelist
    if command not in allowed_commands:
        raise HTTPException(
            400,
            f"Command '{command}' is not allowed. Allowed commands: {', '.join(allowed_commands)}. "
            f"To add more commands, set FMCP_ALLOWED_COMMANDS environment variable."
        )

    # Validate args if present
    if "args" in config:
        args = config["args"]
        if not isinstance(args, list):
            raise HTTPException(400, "Server configuration 'args' must be a list")

        # Enhanced argument validation
        dangerous_patterns = [";", "&", "|", "`", "&&", "||", "$(", "${", "\n", "\r"]
        # Shell metacharacters that should be rejected unless in specific contexts
        shell_metacharacters = ["<", ">", ">>", "<<"]

        for arg in args:
            if not isinstance(arg, str):
                raise HTTPException(400, "All arguments must be strings")

            # Length validation - max 1000 chars per argument
            if len(arg) > 1000:
                raise HTTPException(
                    400,
                    f"Argument exceeds maximum length of 1000 characters: {arg[:50]}..."
                )

            # Check for dangerous shell patterns
            for pattern in dangerous_patterns:
                if pattern in arg:
                    raise HTTPException(
                        400,
                        f"Argument contains potentially dangerous pattern '{pattern}': {arg}"
                    )

            # Check for shell metacharacters (with exceptions for flags)
            for pattern in shell_metacharacters:
                if pattern in arg:
                    raise HTTPException(
                        400,
                        f"Argument contains shell metacharacter '{pattern}': {arg}"
                    )

            # Validate argument structure for flags
            if arg.startswith("-"):
                # Flags should match pattern: -x or --xxx or --xxx=value
                if not re.match(r"^-[a-zA-Z0-9]$|^--[a-zA-Z0-9-]+(=.+)?$", arg):
                    raise HTTPException(
                        400,
                        f"Invalid flag format: {arg}. Flags should be -x or --flag or --flag=value"
                    )

    # Validate env if present
    if "env" in config:
        env = config["env"]
        if not isinstance(env, dict):
            raise HTTPException(400, "Server configuration 'env' must be a dictionary")

        # Enhanced environment variable validation
        for key, value in env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise HTTPException(400, "Environment variable keys and values must be strings")

            # Validate env var name (alphanumeric + underscore only)
            if not re.match(r"^[A-Z_][A-Z0-9_]*$", key):
                raise HTTPException(
                    400,
                    f"Invalid environment variable name '{key}'. Must be uppercase alphanumeric with underscores."
                )

            # Length validation - max 10,000 chars per value
            if len(value) > 10000:
                raise HTTPException(
                    400,
                    f"Environment variable '{key}' value exceeds maximum length of 10,000 characters"
                )

            # Check for shell metacharacters in env values
            dangerous_env_patterns = [";", "&", "|", "`", "$(", "${", "\n", "\r", "&&", "||"]
            for pattern in dangerous_env_patterns:
                if pattern in value:
                    raise HTTPException(
                        400,
                        f"Environment variable '{key}' contains dangerous pattern '{pattern}'"
                    )


# ==================== Configuration Management ====================

@router.post("/servers")
async def add_server(
    request: Request,
    config: Dict[str, Any] = Body(
        ...,
        example={
            "id": "filesystem",
            "name": "Filesystem Server",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {},
            "working_dir": "/tmp",
            "install_path": "/tmp",
            "restart_policy": "on-failure",
            "max_restarts": 3
        }
    ),
    token: str = Depends(get_token)
):
    """
    Add a new server configuration.

    Request Body:
        id (str): Unique server identifier (URL-friendly)
        name (str): Human-readable display name
        command (str): Command to run
        args (list): Command arguments
        env (dict): Environment variables
        working_dir (str): Working directory
        install_path (str): Installation path
        restart_policy (str): 'no', 'on-failure', or 'always'
        max_restarts (int): Maximum restart attempts
    """
    manager = get_server_manager(request)

    # Sanitize input to prevent MongoDB injection
    config = sanitize_input(config)

    # Validate required fields
    if "id" not in config:
        raise HTTPException(400, "Server id is required")
    if "name" not in config:
        raise HTTPException(400, "Server name is required")

    # Validate configuration for security
    validate_server_config(config)

    id = config["id"]
    name = config["name"]

    # Check if server already exists (check both DB and in-memory)
    if id in manager.configs:
        raise HTTPException(400, f"Server with id '{id}' already exists")

    existing = await manager.db.get_server_config(id)
    if existing:
        raise HTTPException(400, f"Server with id '{id}' already exists")

    # Try to save to database, fall back to in-memory storage
    success = await manager.db.save_server_config(config)
    if not success:
        # Store in-memory as fallback
        logger.warning(f"Database save failed for '{name}', storing in-memory only")

    # Always store in configs dict for immediate access
    manager.configs[id] = config

    logger.info(f"Added server configuration: {name} (id: {id})")
    return {
        "message": f"Server '{name}' configured successfully",
        "id": id,
        "name": name
    }


@router.get("/servers")
async def list_servers(request: Request):
    """
    List all configured servers with their status.

    Returns:
        List of servers with config and status
    """
    manager = get_server_manager(request)
    servers = await manager.list_servers()

    return {
        "servers": servers,
        "count": len(servers)
    }


@router.get("/servers/{id}")
async def get_server(request: Request, id: str):
    """
    Get detailed information about a specific server.

    Args:
        id: Server identifier

    Returns:
        Server config and status
    """
    manager = get_server_manager(request)

    # Get config from in-memory or database
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Get status
    status = await manager.get_server_status(id)

    return {
        "id": id,
        "name": config.get("name"),
        "config": config,
        "status": status
    }


@router.put("/servers/{id}")
async def update_server(
    request: Request,
    id: str,
    config: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    Update server configuration (only when stopped).

    Args:
        id: Server identifier
        config: New configuration (must include 'name' and 'command' fields)

    Required Fields:
        name (str): Human-readable display name
        command (str): Command to run (must be whitelisted)

    Optional Fields:
        args (list): Command arguments
        env (dict): Environment variables
        description (str): Server description
        enabled (bool): Whether server is enabled
        restart_policy (str): 'no', 'on-failure', or 'always'
        max_restarts (int): Maximum restart attempts
        working_dir (str): Working directory
        install_path (str): Installation path

    Returns:
        Success message
    """
    manager = get_server_manager(request)

    # Sanitize input to prevent MongoDB injection
    config = sanitize_input(config)

    # Check if server exists (in-memory or database)
    existing = manager.configs.get(id)
    if not existing:
        existing = await manager.db.get_server_config(id)
    if not existing:
        raise HTTPException(404, f"Server '{id}' not found")

    # Check if server is running
    if id in manager.processes:
        process = manager.processes[id]
        if process.poll() is None:
            raise HTTPException(400, "Cannot update running server. Stop it first.")

    # Validate required fields
    if "name" not in config:
        raise HTTPException(400, "Server name is required")

    # Validate configuration for security
    validate_server_config(config)

    # Update config (preserve id)
    config["id"] = id

    # Save updated config (both database and in-memory)
    success = await manager.db.save_server_config(config)
    if not success:
        logger.warning(f"Database save failed for '{config['name']}', storing in-memory only")

    # Always update in-memory
    manager.configs[id] = config

    logger.info(f"Updated server configuration: {config['name']} (id: {id})")
    return {
        "message": f"Server '{id}' updated successfully",
        "config": config
    }


@router.delete("/servers/{id}")
async def delete_server(
    request: Request,
    id: str,
    token: str = Depends(get_token),
    user_id: str = Depends(get_current_user)
):
    """
    Delete server configuration (stops server if running).

    Authorization: Only admins can delete server configurations.
    Regular users cannot delete servers (they can only stop instances they started).

    Args:
        id: Server identifier
        user_id: Current user (from token)

    Returns:
        Success message
    """
    manager = get_server_manager(request)

    # Check if server exists (in-memory or database)
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Authorization: Only allow in anonymous mode (no authentication) for now
    # This is intentionally restrictive - deletion is a destructive operation.
    # TODO: Implement proper role-based access control (RBAC) with admin roles
    # when JWT authentication with role claims is added. Current token-based
    # auth (user_id = first 8 chars of token) is too weak for delete permissions.
    if user_id != "anonymous":
        raise HTTPException(
            403,
            "Server deletion requires administrator privileges"
        )

    # Stop server if running
    if id in manager.processes:
        logger.info(f"Stopping server '{id}' before deletion...")
        await manager.stop_server(id)

    # Delete from database
    await manager.db.delete_server_config(id)

    # Delete from in-memory
    if id in manager.configs:
        del manager.configs[id]

    logger.info(f"Deleted server configuration: {id}")
    return {
        "message": f"Server '{id}' deleted successfully"
    }


# ==================== Lifecycle Control ====================

@router.post("/servers/{id}/start")
async def start_server(
    request: Request,
    id: str,
    token: str = Depends(get_token),
    user_id: str = Depends(get_current_user)
):
    """
    Start an MCP server.

    Args:
        id: Server identifier
        user_id: User identifier (extracted from token)

    Returns:
        Success message with PID
    """
    manager = get_server_manager(request)

    # Check if server exists (in-memory or database)
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Check if already running
    if id in manager.processes:
        process = manager.processes[id]
        if process.poll() is None:
            raise HTTPException(400, f"Server '{id}' is already running (PID: {process.pid})")

    # Start server with user tracking
    success = await manager.start_server(id, config, user_id=user_id)
    if not success:
        raise HTTPException(500, f"Failed to start server '{id}'")

    # Get PID
    process = manager.processes.get(id)
    pid = process.pid if process else None

    logger.info(f"Started server '{id}' via API")
    return {
        "message": f"Server '{id}' started successfully",
        "pid": pid
    }


@router.post("/servers/{id}/stop")
async def stop_server(
    request: Request,
    id: str,
    force: bool = Query(False, description="Use SIGKILL instead of SIGTERM"),
    token: str = Depends(get_token),
    user_id: str = Depends(get_current_user)
):
    """
    Stop a running MCP server.

    Authorization: Users can only stop servers they started (unless admin).

    Args:
        id: Server identifier
        force: If true, use SIGKILL
        user_id: Current user (from token)

    Returns:
        Success message with exit code
    """
    manager = get_server_manager(request)

    # Check if server is running
    if id not in manager.processes:
        raise HTTPException(400, f"Server '{id}' is not running")

    # Authorization: Check if user started this server
    instance = await manager.db.get_instance_state(id)
    if instance:
        started_by = instance.get("started_by")
        # Allow if user started it, or if no owner (backward compatibility), or if anonymous mode
        if started_by and started_by != user_id and user_id != "anonymous":
            raise HTTPException(
                403,
                f"Forbidden: Server '{id}' was started by another user. Only the user who started it can stop it."
            )

    # Stop server
    success = await manager.stop_server(id, force=force)
    if not success:
        raise HTTPException(500, f"Failed to stop server '{id}'")

    logger.info(f"Stopped server '{id}' via API (force={force})")
    return {
        "message": f"Server '{id}' stopped successfully",
        "forced": force
    }


@router.post("/servers/{id}/restart")
async def restart_server(
    request: Request,
    id: str,
    token: str = Depends(get_token),
    user_id: str = Depends(get_current_user)
):
    """
    Restart an MCP server.

    Authorization: Users can only restart servers they started (unless admin).

    Args:
        id: Server identifier
        user_id: Current user (from token)

    Returns:
        Success message with new PID
    """
    manager = get_server_manager(request)

    # Check if server exists (in-memory or database)
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Authorization: Check if user started this server
    instance = await manager.db.get_instance_state(id)
    if instance:
        started_by = instance.get("started_by")
        # Allow if user started it, or if no owner (backward compatibility), or if anonymous mode
        if started_by and started_by != user_id and user_id != "anonymous":
            raise HTTPException(
                403,
                f"Forbidden: Server '{id}' was started by another user. Only the user who started it can restart it."
            )

    # Restart server
    success = await manager.restart_server(id)
    if not success:
        raise HTTPException(500, f"Failed to restart server '{id}'")

    # Get new PID
    process = manager.processes.get(id)
    pid = process.pid if process else None

    logger.info(f"Restarted server '{id}' via API")
    return {
        "message": f"Server '{id}' restarted successfully",
        "pid": pid
    }


@router.post("/servers/start-all")
async def start_all_servers(request: Request, token: str = Depends(get_token)):
    """
    Start all configured servers.

    Returns:
        Summary of started servers
    """
    manager = get_server_manager(request)

    configs = await manager.db.list_server_configs()
    started = []
    failed = []

    for config in configs:
        server_id = config.get("id")
        if not server_id:
            continue

        name = config.get("name", server_id)

        # Skip if already running
        if server_id in manager.processes:
            process = manager.processes[server_id]
            if process.poll() is None:
                continue

        # Start server
        success = await manager.start_server(server_id, config)
        if success:
            started.append(name)
        else:
            failed.append(name)

    logger.info(f"Started {len(started)} servers via API")
    return {
        "message": f"Started {len(started)} server(s)",
        "started": started,
        "failed": failed
    }


@router.post("/servers/stop-all")
async def stop_all_servers(request: Request, token: str = Depends(get_token)):
    """
    Stop all running servers.

    Returns:
        Summary of stopped servers
    """
    manager = get_server_manager(request)

    await manager.stop_all_servers()

    logger.info("Stopped all servers via API")
    return {
        "message": "All servers stopped successfully"
    }


# ==================== Status & Information ====================

@router.get("/servers/{id}/status")
async def get_server_status(request: Request, id: str):
    """
    Get detailed status of a server.

    Args:
        id: Server identifier

    Returns:
        Status information (state, pid, uptime, etc.)
    """
    manager = get_server_manager(request)

    status = await manager.get_server_status(id)

    if status["state"] == "not_found":
        raise HTTPException(404, f"Server '{id}' not found")

    return status


@router.get("/servers/{id}/logs")
async def get_server_logs(
    request: Request,
    id: str,
    lines: int = Query(100, description="Number of recent log lines")
):
    """
    Get recent logs for a server.

    Args:
        id: Server identifier
        lines: Number of recent lines to retrieve

    Returns:
        List of log entries
    """
    manager = get_server_manager(request)

    # Check if server exists (in-memory or database)
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Get logs from database
    logs = await manager.db.get_logs(id, lines=lines)

    return {
        "server": id,
        "logs": logs,
        "count": len(logs)
    }


# ==================== Environment Variable Management ====================

@router.get("/servers/{id}/instance/env")
async def get_server_instance_env(request: Request, id: str):
    """
    Get environment variable metadata for a server instance.

    Returns metadata about each environment variable:
    - present: Whether it has a value in the instance
    - required: Whether it's required for server operation
    - masked: Masked value if present (e.g., "****")
    - description: Help text for the user

    Args:
        id: Server identifier

    Returns:
        Dict of env var names to metadata
    """
    manager = get_server_manager(request)

    # Get server config to determine required env vars
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Get instance env (actual values set by user)
    instance_env = await manager.db.get_instance_env(id) or {}

    # Get config env (default/required env vars from config)
    config_env = config.get("env", {})

    # Build metadata response
    metadata = {}

    # Add all config env vars (these are the ones we expect)
    for key in config_env.keys():
        has_value = key in instance_env and instance_env[key]
        metadata[key] = {
            "present": has_value,
            "required": True,  # All env vars in config are considered required
            "masked": "****" if has_value else None,
            "description": f"Environment variable for {config.get('name', id)}"
        }

    # Add any instance env vars not in config (user-added)
    for key in instance_env.keys():
        if key not in metadata:
            metadata[key] = {
                "present": True,
                "required": False,
                "masked": "****",
                "description": "Custom environment variable"
            }

    return metadata


@router.put("/servers/{id}/instance/env")
async def update_server_instance_env(
    request: Request,
    id: str,
    env: Dict[str, str] = Body(...),
    token: str = Depends(get_token)
):
    """
    Update environment variables for a server instance.

    This updates the instance-specific env vars (user's API keys, etc.)
    without modifying the server config template.

    Args:
        id: Server identifier
        env: Dict of environment variable key-value pairs

    Returns:
        Success message with update status
    """
    manager = get_server_manager(request)

    # Check if server exists
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Validate env vars (basic validation)
    if not isinstance(env, dict):
        raise HTTPException(400, "Environment variables must be a dictionary")

    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise HTTPException(400, "Environment variable keys and values must be strings")

    # Update instance env in database
    success = await manager.db.update_instance_env(id, env)

    if not success:
        # If no instance exists yet, we still return success
        # The env will be used when the server starts
        logger.info(f"No instance exists yet for '{id}', env will be used on next start")

    logger.info(f"Updated instance env for server '{id}'")
    return {
        "message": f"Environment variables updated for server '{id}'",
        "env_updated": True
    }


# ==================== Tool Discovery & Execution (PDF Spec) ====================

@router.get("/servers/{id}/tools")
async def get_server_tools(request: Request, id: str):
    """
    Get discovered tools for a server.

    Tools are automatically discovered when the server starts and cached in MongoDB.
    Returns the cached tool list from the database.

    Args:
        id: Server identifier

    Returns:
        List of discovered tools with their schemas
    """
    manager = get_server_manager(request)

    # Get config with cached tools (database layer flattens it but tools field passes through)
    config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    tools = config.get("tools", [])

    return {
        "server_id": id,
        "tools": tools,
        "count": len(tools)
    }


@router.post("/servers/{id}/tools/{tool_name}/run")
async def run_tool(
    request: Request,
    id: str,
    tool_name: str,
    arguments: Dict[str, Any] = Body(default={}),
    token: str = Depends(get_token)
):
    """
    Execute a tool on a running MCP server.

    Sends a tools/call JSON-RPC request to the running server process
    and returns the result.

    Args:
        id: Server identifier
        tool_name: Name of the tool to execute
        arguments: Tool arguments as dict

    Returns:
        Tool execution result
    """
    manager = get_server_manager(request)

    # Check if server is running
    if id not in manager.processes:
        raise HTTPException(400, f"Server '{id}' is not running")

    process = manager.processes[id]
    if process.poll() is not None:
        raise HTTPException(400, f"Server '{id}' has stopped")

    # Send tools/call request
    try:
        import json
        import asyncio

        tool_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        logger.info(f"Executing tool '{tool_name}' on server '{id}'")
        process.stdin.write(json.dumps(tool_request) + "\n")
        process.stdin.flush()

        # Read response with 30 second timeout
        response_line = await asyncio.wait_for(
            asyncio.to_thread(process.stdout.readline),
            timeout=30.0
        )

        response = json.loads(response_line.strip())

        if "error" in response:
            raise HTTPException(500, f"Tool execution error: {response['error']}")

        logger.info(f"Tool '{tool_name}' executed successfully on server '{id}'")
        return response.get("result", {})

    except asyncio.TimeoutError:
        raise HTTPException(504, "Tool execution timeout (>30s)")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse tool response for '{tool_name}' on '{id}': {e}")
        raise HTTPException(500, "Failed to parse tool response")
    except Exception as e:
        logger.exception(f"Tool execution failed for '{tool_name}' on '{id}': {e}")
        raise HTTPException(500, "Tool execution failed")


# ==================== LLM Management ====================

def get_llm_processes():
    """Get LLM processes from run_servers module."""
    # Import here to avoid circular dependency
    from ..services import get_llm_processes as _get_llm_processes
    return _get_llm_processes()


@router.get("/llm/models")
async def list_llm_models(
    token: str = Depends(get_token)
):
    """
    List all configured LLM models with their status.

    Returns:
        List of LLM models with status information
    """
    llm_processes = get_llm_processes()

    models = []
    for model_id, process in llm_processes.items():
        is_healthy, health_msg = await process.check_health()
        models.append({
            "id": model_id,
            "is_running": process.is_running(),
            "is_healthy": is_healthy,
            "health_message": health_msg,
            "restart_policy": process.restart_policy,
            "restart_count": process.restart_count,
            "max_restarts": process.max_restarts,
            "consecutive_health_failures": process.consecutive_health_failures,
            "uptime_seconds": process.get_uptime(),
            "last_restart_time": process.last_restart_time,
            "last_health_check_time": process.last_health_check_time
        })

    return {
        "models": models,
        "total": len(models)
    }


@router.get("/llm/models/{model_id}")
async def get_llm_model_status(
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Get detailed status for a specific LLM model.

    Args:
        model_id: Model identifier

    Returns:
        Detailed model status
    """
    llm_processes = get_llm_processes()

    if model_id not in llm_processes:
        raise HTTPException(404, f"LLM model '{model_id}' not found")

    process = llm_processes[model_id]
    is_healthy, health_msg = await process.check_health()

    return {
        "id": model_id,
        "is_running": process.is_running(),
        "is_healthy": is_healthy,
        "health_message": health_msg,
        "restart_policy": process.restart_policy,
        "restart_count": process.restart_count,
        "max_restarts": process.max_restarts,
        "consecutive_health_failures": process.consecutive_health_failures,
        "uptime_seconds": process.get_uptime(),
        "last_restart_time": process.last_restart_time,
        "last_health_check_time": process.last_health_check_time,
        # Issue #3 fix: Use asyncio.to_thread to avoid blocking event loop with file I/O
        "has_cuda_oom": await asyncio.to_thread(process.check_for_cuda_oom)
    }


@router.post("/llm/models/{model_id}/restart")
async def restart_llm_model(
    request: Request,
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Manually restart a specific LLM model.

    Args:
        model_id: Model identifier

    Returns:
        Restart result
    """
    llm_processes = get_llm_processes()

    if model_id not in llm_processes:
        raise HTTPException(404, f"LLM model '{model_id}' not found")

    process = llm_processes[model_id]

    # Check if restart is allowed
    if not process.can_restart():
        raise HTTPException(
            400,
            f"Cannot restart model '{model_id}': restart policy is '{process.restart_policy}' "
            f"or max restarts ({process.max_restarts}) reached"
        )

    logger.info(f"Manual restart requested for LLM model '{model_id}'")

    # Attempt restart
    success = await process.attempt_restart()

    if success:
        return {
            "message": f"LLM model '{model_id}' restarted successfully",
            "restart_count": process.restart_count,
            "uptime_seconds": process.get_uptime()
        }
    else:
        raise HTTPException(
            500,
            f"Failed to restart LLM model '{model_id}'. Check logs for details."
        )


@router.post("/llm/models/{model_id}/stop")
async def stop_llm_model(
    request: Request,
    model_id: str,
    force: bool = Query(False, description="Force kill the process"),
    token: str = Depends(get_token)
):
    """
    Stop a specific LLM model.

    Args:
        model_id: Model identifier
        force: If true, force kill the process (SIGKILL)

    Returns:
        Stop result
    """
    llm_processes = get_llm_processes()

    if model_id not in llm_processes:
        raise HTTPException(404, f"LLM model '{model_id}' not found")

    process = llm_processes[model_id]

    if not process.is_running():
        return {"message": f"LLM model '{model_id}' is already stopped"}

    logger.info(f"Stop requested for LLM model '{model_id}' (force={force})")

    try:
        if force:
            process.force_kill()
            return {"message": f"LLM model '{model_id}' force killed"}
        else:
            process.stop()
            return {"message": f"LLM model '{model_id}' stopped gracefully"}
    except Exception as e:
        logger.error(f"Error stopping LLM model '{model_id}': {e}", exc_info=True)
        raise HTTPException(500, "Failed to stop LLM model")


@router.get("/llm/models/{model_id}/logs")
async def get_llm_model_logs(
    model_id: str,
    lines: int = Query(100, description="Number of recent lines to retrieve", ge=1, le=10000),
    token: str = Depends(get_token)
):
    """
    Get recent stderr logs for a specific LLM model.

    Args:
        model_id: Model identifier
        lines: Number of recent lines to retrieve (1-10000)

    Returns:
        Log lines
    """
    llm_processes = get_llm_processes()

    if model_id not in llm_processes:
        raise HTTPException(404, f"LLM model '{model_id}' not found")

    process = llm_processes[model_id]
    log_path = process.get_stderr_log_path()

    if not os.path.exists(log_path):
        return {
            "model_id": model_id,
            "log_path": log_path,
            "lines": [],
            "message": "Log file does not exist yet"
        }

    try:
        # Efficiently read only the last N lines using backwards seeking
        # This avoids loading large log files entirely into memory
        # TODO: For very large files (>100MB), consider mmap for better performance
        block_size = 8192
        buffer = b""
        newline_count = 0

        with open(log_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            position = file_size

            # Read backwards until we have enough lines or reach start of file
            while position > 0 and newline_count <= lines:
                read_size = block_size if position >= block_size else position
                position -= read_size
                f.seek(position)
                data = f.read(read_size)
                buffer = data + buffer
                newline_count = buffer.count(b"\n")

        # Decode and split into lines
        text = buffer.decode("utf-8", errors="ignore")
        all_lines_read = text.splitlines(keepends=True)
        recent_lines = all_lines_read[-lines:] if len(all_lines_read) > lines else all_lines_read

        # Note: total_lines is approximate when file is larger than what we read
        total_lines_approx = len(all_lines_read)

        return {
            "model_id": model_id,
            "lines": recent_lines,
            "total_lines": total_lines_approx,
            "returned_lines": len(recent_lines)
        }
    except Exception as e:
        logger.error(f"Error reading logs for '{model_id}': {e}", exc_info=True)
        raise HTTPException(500, "Failed to read logs")


@router.post("/llm/models/{model_id}/health-check")
async def trigger_health_check(
    request: Request,
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Manually trigger a health check for a specific LLM model.

    Args:
        model_id: Model identifier

    Returns:
        Health check result
    """
    llm_processes = get_llm_processes()

    if model_id not in llm_processes:
        raise HTTPException(404, f"LLM model '{model_id}' not found")

    process = llm_processes[model_id]

    logger.info(f"Manual health check triggered for LLM model '{model_id}'")

    is_healthy, error_msg = await process.check_health()

    return {
        "model_id": model_id,
        "is_healthy": is_healthy,
        "health_message": error_msg,
        "consecutive_health_failures": process.consecutive_health_failures,
        "last_health_check_time": process.last_health_check_time,
        # Issue #3 fix: Use asyncio.to_thread to avoid blocking event loop with file I/O
        "has_cuda_oom": await asyncio.to_thread(process.check_for_cuda_oom)
    }
