"""
Unified server runner for FluidMCP CLI.

This module provides a single entry point for launching MCP servers
regardless of the configuration source.
"""
import os
import json
from pathlib import Path
from typing import Optional
from loguru import logger

from fastapi import FastAPI
import uvicorn

from .config_resolver import ServerConfig, INSTALLATION_DIR
from .package_installer import install_package, parse_package_string
from .package_list import get_latest_version_dir
from .package_launcher import launch_mcp_using_fastapi_proxy
from .network_utils import is_port_in_use, kill_process_on_port
from .env_manager import update_env_from_config
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends
from fastapi.responses import JSONResponse
from typing import Dict
import subprocess
import asyncio
import threading

# Default ports
client_server_port = int(os.environ.get("MCP_CLIENT_SERVER_PORT", "8090"))
client_server_all_port = int(os.environ.get("MCP_CLIENT_SERVER_ALL_PORT", "8099"))

# Explicit process registry for server tracking
_server_processes: Dict[str, subprocess.Popen] = {}

# Thread-safety locks for process stdin/stdout communication
_process_locks: Dict[str, threading.Lock] = {}


def run_servers(
    config: ServerConfig,
    secure_mode: bool = False,
    token: Optional[str] = None,
    single_package: bool = False,
    start_server: bool = True,
    force_reload: bool = False
) -> None:
    """
    Unified server launcher for all run modes.

    Args:
        config: ServerConfig with resolved server configurations
        secure_mode: Enable bearer token authentication
        token: Bearer token for secure mode
        single_package: True if running a single package (uses port 8090)
        start_server: Whether to start the FastAPI server
        force_reload: Force kill existing process on port without prompting
    """
    # Set up secure mode environment
    if secure_mode and token:
        os.environ["FMCP_BEARER_TOKEN"] = token
        os.environ["FMCP_SECURE_MODE"] = "true"
        logger.info("Secure mode enabled with bearer token")

    # Install packages if needed
    if config.needs_install:
        _install_packages_from_config(config)

    # Determine port based on mode
    port = client_server_port if single_package else client_server_all_port

    # Create FastAPI app
    app = FastAPI(
        title=f"FluidMCP Gateway ({config.source_type})",
        description=f"Unified gateway for MCP servers from {config.source_type}",
        version="2.0.0"
    )
    #CORS setup to allow React dev server access
    # "http://localhost:5173"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Launch each server and add its router
    launched_servers = 0
    for server_name, server_cfg in config.servers.items():
        install_path = server_cfg.get("install_path")
        if not install_path:
            logger.warning(f"No installation path for server '{server_name}', skipping")
            continue

        install_path = Path(install_path)
        if not install_path.exists():
            logger.warning(f"Installation path '{install_path}' does not exist, skipping")
            continue

        metadata_path = install_path / "metadata.json"
        if not metadata_path.exists():
            logger.warning(f"No metadata.json in '{install_path}', skipping")
            continue

        try:
            logger.info(f"Launching server '{server_name}' from: {install_path}")
            package_name, router, process = launch_mcp_using_fastapi_proxy(install_path)

            if router and process:
                app.include_router(router, tags=[server_name])
                _register_server_process(server_name, process)  # Register in explicit registry
                logger.info(f"Added {package_name} endpoints")
                launched_servers += 1
            else:
                logger.error(f"Failed to create router for {server_name}")

        except Exception:
            logger.exception(f"Error launching server '{server_name}'")

    if launched_servers == 0:
        logger.warning("No servers were successfully launched")
        return

    logger.info(f"Successfully launched {launched_servers} MCP server(s)")

    # Add unified tool discovery endpoint
    _add_unified_tools_endpoint(app, secure_mode)

    # Start FastAPI server if requested
    if start_server:
        _start_server(app, port, force_reload)


def _register_server_process(name: str, process: subprocess.Popen) -> None:
    """
    Register a server process in the explicit registry.

    Args:
        name: Server name
        process: Subprocess.Popen object for the server
    """
    _server_processes[name] = process
    logger.debug(f"Registered process for server: {name} (PID: {process.pid})")


def _get_server_processes() -> Dict[str, subprocess.Popen]:
    """
    Get all registered server processes.

    Returns:
        Dictionary mapping server names to their subprocess.Popen objects
    """
    return _server_processes.copy()


def _add_unified_tools_endpoint(app: FastAPI, secure_mode: bool) -> None:
    """
    Add GET /api/tools endpoint for unified tool discovery across all MCP servers.

    Args:
        app: FastAPI application instance
        secure_mode: Whether secure mode is enabled
    """
    from .package_launcher import get_token

    @app.get("/api/tools", tags=["unified"])
    async def get_all_tools(token: str = Depends(get_token) if secure_mode else None):
        """
        Dynamic tool discovery across all running MCP servers.

        Returns:
            JSON response with all tools from all servers, including:
            - tools: List of tool definitions with server labels
            - summary: Metadata about total tools and servers
        """
        all_tools = []
        servers_found = []
        servers_with_errors = []

        # Get server processes from explicit registry
        server_processes = _get_server_processes()

        logger.info(f"Discovering tools from {len(server_processes)} MCP server(s)")

        for server_name, process in server_processes.items():
            # Get or create lock for thread-safe process communication
            if server_name not in _process_locks:
                _process_locks[server_name] = threading.Lock()

            lock = _process_locks[server_name]

            try:
                logger.debug(f"Querying tools from server: {server_name}")

                # Send tools/list JSON-RPC request to the server
                tools_request = {
                    "jsonrpc": "2.0",
                    "id": f"tools_discovery_{server_name}",
                    "method": "tools/list",
                    "params": {}
                }

                # Acquire lock for thread-safe stdin/stdout communication
                with lock:
                    # Wrap blocking I/O in asyncio.to_thread to avoid blocking event loop
                    await asyncio.to_thread(
                        process.stdin.write,
                        json.dumps(tools_request) + "\n"
                    )
                    await asyncio.to_thread(process.stdin.flush)

                    # Add timeout to prevent indefinite hanging
                    try:
                        response_line = await asyncio.wait_for(
                            asyncio.to_thread(process.stdout.readline),
                            timeout=5.0  # 5 second timeout
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout waiting for response from server: {server_name}")
                        servers_with_errors.append(server_name)
                        continue

                if not response_line:
                    logger.warning(f"No response from server: {server_name}")
                    servers_with_errors.append(server_name)
                    continue

                response_data = json.loads(response_line)

                # Check for JSON-RPC error
                if "error" in response_data:
                    error_msg = response_data["error"].get("message", "Unknown error")
                    logger.warning(f"Error from server {server_name}: {error_msg}")
                    servers_with_errors.append(server_name)
                    continue

                # Extract tools from response
                if "result" in response_data and "tools" in response_data["result"]:
                    server_tools = response_data["result"]["tools"]

                    # Create new tool dicts with server label (don't mutate originals)
                    for tool in server_tools:
                        new_tool = dict(tool)
                        new_tool["server"] = server_name
                        all_tools.append(new_tool)

                    servers_found.append(server_name)
                    logger.debug(f"Found {len(server_tools)} tools from {server_name}")
                else:
                    logger.warning(f"Unexpected response format from {server_name}")
                    servers_with_errors.append(server_name)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from {server_name}: {e}")
                servers_with_errors.append(server_name)
            except Exception as e:
                logger.error(f"Error querying tools from {server_name}: {e}")
                servers_with_errors.append(server_name)

        # Build response (error_count always present for API consistency)
        response = {
            "tools": all_tools,
            "summary": {
                "total_tools": len(all_tools),
                "servers": servers_found,
                "server_count": len(servers_found),
                "error_count": len(servers_with_errors)
            }
        }

        if servers_with_errors:
            response["summary"]["servers_with_errors"] = servers_with_errors

        logger.info(f"Tool discovery complete: {len(all_tools)} tools from {len(servers_found)} servers")

        return JSONResponse(content=response)


def _install_packages_from_config(config: ServerConfig) -> None:
    """
    Install packages listed in the server config.

    Args:
        config: ServerConfig with servers that need installation
    """
    install_dir = Path(INSTALLATION_DIR)

    for server_name, server_cfg in config.servers.items():
        fmcp_package = server_cfg.get("fmcp_package")
        if not fmcp_package:
            # Already installed or no package reference
            continue

        logger.info(f"Installing package: {fmcp_package}")
        pkg = parse_package_string(fmcp_package)

        try:
            # Install package (skip env prompts, we'll update from config)
            install_package(fmcp_package, skip_env=True)

            # Find installed package directory
            author, package_name = pkg["author"], pkg["package_name"]
            version = pkg.get("version")

            if version and version != "latest":
                dest_dir = install_dir / author / package_name / version
            else:
                package_dir = install_dir / author / package_name
                try:
                    dest_dir = get_latest_version_dir(package_dir)
                except FileNotFoundError:
                    logger.error(f"Package not found after install: {author}/{package_name}")
                    continue

            if not dest_dir.exists():
                logger.error(f"Package directory not found: {dest_dir}")
                continue

            # Update install_path in config
            server_cfg["install_path"] = str(dest_dir)

            # Update env variables from config file
            metadata_path = dest_dir / "metadata.json"
            if metadata_path.exists() and config.metadata_path:
                try:
                    # Load the original config to get env values
                    with open(config.metadata_path, 'r') as f:
                        source_config = json.load(f)
                    update_env_from_config(metadata_path, fmcp_package, source_config, pkg)
                except Exception:
                    logger.exception(f"Error updating env for {fmcp_package}")

            # For master mode, update from shared .env
            if config.source_type == "s3_master":
                _update_env_from_common_env(dest_dir, pkg)

        except Exception:
            logger.exception(f"Error installing {fmcp_package}")


def _update_env_from_common_env(dest_dir: Path, pkg: dict) -> None:
    """
    Update metadata.json env section from a common .env file.

    Args:
        dest_dir: Package installation directory
        pkg: Parsed package info dict
    """
    install_dir = Path(INSTALLATION_DIR)
    env_path = install_dir / ".env"
    metadata_path = dest_dir / "metadata.json"

    # Load .env if exists
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env_vars[k.strip()] = v.strip()
    else:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.touch()

    # Load metadata.json
    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Get env section
    try:
        env_section = metadata["mcpServers"][pkg["package_name"]]["env"]
    except (KeyError, TypeError):
        return

    for key in env_section:
        if isinstance(env_section[key], dict):
            # Structured format
            if env_section[key].get("required"):
                if key in env_vars:
                    metadata["mcpServers"][pkg["package_name"]]["env"][key]["value"] = env_vars[key]
                else:
                    env_vars[key] = "dummy-key"
                    metadata["mcpServers"][pkg["package_name"]]["env"][key]["value"] = "dummy-key"
        else:
            # Simple format
            if key in env_vars:
                metadata["mcpServers"][pkg["package_name"]]["env"][key] = env_vars[key]
            else:
                env_vars[key] = "dummy-key"
                metadata["mcpServers"][pkg["package_name"]]["env"][key] = "dummy-key"

    # Write back .env
    with open(env_path, "w") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")

    # Write back metadata.json
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)


def _start_server(app: FastAPI, port: int, force_reload: bool) -> None:
    """
    Start the FastAPI server on the specified port.

    Args:
        app: FastAPI application
        port: Port to listen on
        force_reload: Force kill existing process without prompting
    """
    if is_port_in_use(port):
        logger.warning(f"Port {port} is already in use")
        if force_reload:
            logger.info(f"Force reloading server on port {port}")
            kill_process_on_port(port)
        else:
            choice = input("Kill existing process and reload? (y/n): ").strip().lower()
            if choice == 'y':
                kill_process_on_port(port)
            elif choice == 'n':
                logger.info(f"Keeping existing process on port {port}")
                return
            else:
                logger.warning("Invalid choice. Aborting")
                return

    logger.info(f"Swagger UI available at: http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)
