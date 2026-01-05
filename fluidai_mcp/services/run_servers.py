"""
Unified server runner for FluidMCP CLI.

This module provides a single entry point for launching MCP servers
regardless of the configuration source.
"""

import os
import json
from datetime import datetime
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
from .watchdog_manager import WatchdogManager
from ..models.server_status import RestartPolicy, ServerState
from fastapi.middleware.cors import CORSMiddleware

# Default ports
client_server_port = int(os.environ.get("MCP_CLIENT_SERVER_PORT", "8090"))
client_server_all_port = int(os.environ.get("MCP_CLIENT_SERVER_ALL_PORT", "8099"))


def run_servers(
    config: ServerConfig,
    secure_mode: bool = False,
    token: Optional[str] = None,
    single_package: bool = False,
    start_server: bool = True,
    force_reload: bool = False,
    enable_watchdog: bool = False,
    health_check_interval: int = 30,
    max_restarts: int = 5
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
        enable_watchdog: Enable automatic process monitoring and restart
        health_check_interval: Interval in seconds between health checks (default: 30)
        max_restarts: Maximum number of restart attempts per server (default: 5)
    """
    # Set up secure mode environment
    if secure_mode and token:
        os.environ["FMCP_BEARER_TOKEN"] = token
        os.environ["FMCP_SECURE_MODE"] = "true"
        print(f"Secure mode enabled with bearer token")

    # Install packages if needed
    if config.needs_install:
        _install_packages_from_config(config)

    # Determine port based on mode
    port = client_server_port if single_package else client_server_all_port

    # Initialize watchdog if enabled
    watchdog = None
    if enable_watchdog:
        restart_policy = RestartPolicy(
            max_restarts=max_restarts,
            initial_delay_seconds=2,
            backoff_multiplier=2.0,
            max_delay_seconds=60,
            restart_window_seconds=300
        )
        watchdog = WatchdogManager(
            health_check_interval=health_check_interval,
            default_restart_policy=restart_policy
        )
        print(f"Watchdog enabled: health checks every {health_check_interval}s, max {max_restarts} restarts")

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
            print(f"No installation path for server '{server_name}', skipping")
            continue

        install_path = Path(install_path)
        if not install_path.exists():
            print(f"Installation path '{install_path}' does not exist, skipping")
            continue

        metadata_path = install_path / "metadata.json"
        if not metadata_path.exists():
            print(f"No metadata.json in '{install_path}', skipping")
            continue

        try:
            print(f"Launching server '{server_name}' from: {install_path}")

            # Always request process info; only use it when watchdog is enabled
            package_name, router, process_info = None, None, None
            result = launch_mcp_using_fastapi_proxy(install_path, return_process_info=True)

            if result is None:
                logger.error(f"launch_mcp_using_fastapi_proxy returned None for {server_name}")
            elif not isinstance(result, tuple):
                logger.error(
                    f"Unexpected result type from launch_mcp_using_fastapi_proxy for {server_name}: "
                    f"{type(result).__name__}. Expected 3-tuple."
                )
            elif len(result) != 3:
                logger.error(
                    f"Unexpected result length from launch_mcp_using_fastapi_proxy for {server_name}: "
                    f"{len(result)}. Expected 3 elements (package_name, router, process_info) "
                    f"when return_process_info=True."
                )
            else:
                package_name, router, process_info = result

            if router:
                app.include_router(router, tags=[server_name])
                print(f"Added {package_name} endpoints")
                launched_servers += 1

                # Register with watchdog if enabled
                if watchdog and process_info:
                    # Add server to watchdog (but don't auto-start since already started)
                    # Note: Disable auto-restart for stdio-based MCP servers because they
                    # can't be restarted independently - they need FastAPI router integration
                    watchdog.add_server(
                        server_name=process_info["server_name"],
                        command=process_info["command"],
                        args=process_info["args"],
                        env=process_info["env"],
                        working_dir=Path(process_info["working_dir"]),
                        port=None,  # No HTTP port for stdio-based servers
                        host="localhost",
                        auto_start=False,  # Already started by launch function
                        health_check_enabled=False,  # Only check process alive, not HTTP
                        enable_restart=False  # Disable auto-restart for stdio servers
                    )

                    # Attach the existing process to the monitor
                    monitor = watchdog.get_monitor(process_info["server_name"])
                    if monitor is None:
                        logger.error(
                            f"Watchdog monitor for server '{process_info['server_name']}' "
                            "was not found immediately after registration."
                        )
                        continue

                    monitor.attach_existing_process(
                        process_handle=process_info["process_handle"],
                        pid=process_info["pid"],
                        state=ServerState.RUNNING,
                        started_at=datetime.now()
                    )
                    logger.info(f"Registered {process_info['server_name']} with watchdog (PID: {process_info['pid']})")
            else:
                print(f"Failed to create router for {server_name}")

        except Exception as e:
            print(f"Error launching server '{server_name}': {e}")

    if launched_servers == 0:
        print("No servers were successfully launched")
        return

    print(f"Successfully launched {launched_servers} MCP server(s)")

    # Start watchdog monitoring if enabled
    if watchdog:
        watchdog.start_monitoring()
        print(f"Started watchdog monitoring for {launched_servers} server(s)")

    # Start FastAPI server if requested
    if start_server:
        _start_server(app, port, force_reload, watchdog)


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

        print(f"Installing package: {fmcp_package}")
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
                    print(f"Package not found after install: {author}/{package_name}")
                    continue

            if not dest_dir.exists():
                print(f"Package directory not found: {dest_dir}")
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
                except Exception as e:
                    print(f"Error updating env for {fmcp_package}: {e}")

            # For master mode, update from shared .env
            if config.source_type == "s3_master":
                _update_env_from_common_env(dest_dir, pkg)

        except Exception as e:
            print(f"Error installing {fmcp_package}: {e}")


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


def _cleanup_watchdog(watchdog: Optional[WatchdogManager], cleanup_done_flag: Optional[dict] = None) -> None:
    """
    Clean up watchdog monitoring and stop all servers.

    Args:
        watchdog: Optional WatchdogManager instance to cleanup
        cleanup_done_flag: Optional dict with 'done' key to track if cleanup was already performed
    """
    if cleanup_done_flag and cleanup_done_flag.get('done'):
        # Already cleaned up, skip to prevent duplicate cleanup
        return

    if watchdog:
        logger.info("Shutting down servers...")
        watchdog.stop_monitoring()
        watchdog.stop_all_servers()

    if cleanup_done_flag is not None:
        cleanup_done_flag['done'] = True


def _start_server(
    app: FastAPI,
    port: int,
    force_reload: bool,
    watchdog: Optional[WatchdogManager] = None
) -> None:
    """
    Start the FastAPI server on the specified port.

    Args:
        app: FastAPI application
        port: Port to listen on
        force_reload: Force kill existing process without prompting
        watchdog: Optional WatchdogManager instance for cleanup on shutdown
    """
    if is_port_in_use(port):
        print(f"Port {port} is already in use.")
        if force_reload:
            print(f"Force reloading server on port {port}")
            kill_process_on_port(port)
        else:
            choice = input("Kill existing process and reload? (y/n): ").strip().lower()
            if choice == 'y':
                kill_process_on_port(port)
            elif choice == 'n':
                print(f"Keeping existing process on port {port}")
                return
            else:
                print("Invalid choice. Aborting.")
                return

    # Flag to track if cleanup has been performed (prevents duplicate cleanup)
    cleanup_done = {'done': False}

    # Add shutdown event handler for watchdog cleanup
    # Ensure the shutdown handler is only registered once per app instance
    def shutdown_event() -> None:
        _cleanup_watchdog(watchdog, cleanup_done)

    if not getattr(app, "_watchdog_shutdown_registered", False):
        app.add_event_handler("shutdown", shutdown_event)
        setattr(app, "_watchdog_shutdown_registered", True)

    logger.info(f"Starting FastAPI server on port {port}")
    print(f"Starting FastAPI server on port {port}")
    print(f"Swagger UI available at: http://localhost:{port}/docs")

    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        # Call cleanup explicitly to ensure it happens even if shutdown event doesn't fire
        # The flag prevents duplicate cleanup if shutdown event also fires
        _cleanup_watchdog(watchdog, cleanup_done)
        print("\nServer stopped")

