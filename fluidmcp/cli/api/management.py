"""
Management API endpoints for dynamic MCP server control.

Provides REST API for:
- Adding/removing server configurations
- Starting/stopping/restarting servers
- Querying server status and logs
- Listing all configured servers
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, Body, Query
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter()


def get_server_manager(request: Request):
    """Dependency injection for ServerManager."""
    if not hasattr(request.app.state, "server_manager"):
        raise HTTPException(500, "ServerManager not initialized")
    return request.app.state.server_manager


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
    )
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

    # Validate required fields
    if "id" not in config:
        raise HTTPException(400, "Server id is required")
    if "name" not in config:
        raise HTTPException(400, "Server name is required")

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
        id: Server identifier (name)

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
    config: Dict[str, Any] = Body(...)
):
    """
    Update server configuration (only when stopped).

    Args:
        id: Server identifier (name)
        config: New configuration

    Returns:
        Success message
    """
    manager = get_server_manager(request)

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
async def delete_server(request: Request, id: str):
    """
    Delete server configuration (stops server if running).

    Args:
        id: Server identifier (name)

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
async def start_server(request: Request, id: str):
    """
    Start an MCP server.

    Args:
        id: Server identifier (name)

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

    # Start server
    success = await manager.start_server(id, config)
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
    force: bool = Query(False, description="Use SIGKILL instead of SIGTERM")
):
    """
    Stop a running MCP server.

    Args:
        id: Server identifier (name)
        force: If true, use SIGKILL

    Returns:
        Success message with exit code
    """
    manager = get_server_manager(request)

    # Check if server is running
    if id not in manager.processes:
        raise HTTPException(400, f"Server '{id}' is not running")

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
async def restart_server(request: Request, id: str):
    """
    Restart an MCP server.

    Args:
        id: Server identifier (name)

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
async def start_all_servers(request: Request):
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
        name = config.get("name")
        if not name:
            continue

        # Skip if already running
        if name in manager.processes:
            process = manager.processes[name]
            if process.poll() is None:
                continue

        # Start server
        success = await manager.start_server(name, config)
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
async def stop_all_servers(request: Request):
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
        id: Server identifier (name)

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
        id: Server identifier (name)
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
    arguments: Dict[str, Any] = Body(default={})
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
        raise HTTPException(504, f"Tool execution timeout (>{30}s)")
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Failed to parse tool response: {str(e)}")
    except Exception as e:
        logger.exception(f"Tool execution failed for '{tool_name}' on '{id}': {e}")
        raise HTTPException(500, f"Tool execution failed: {str(e)}")
