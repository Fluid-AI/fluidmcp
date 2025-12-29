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

# Default ports
client_server_port = int(os.environ.get("MCP_CLIENT_SERVER_PORT", "8090"))
client_server_all_port = int(os.environ.get("MCP_CLIENT_SERVER_ALL_PORT", "8099"))


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
    logger.debug(f"Starting run_servers with config source: {config.source_type}")
    logger.debug(f"Single package mode: {single_package}, Start server: {start_server}")
    logger.debug(f"Secure mode: {secure_mode}, Force reload: {force_reload}")

    # Set up secure mode environment
    if secure_mode and token:
        os.environ["FMCP_BEARER_TOKEN"] = token
        os.environ["FMCP_SECURE_MODE"] = "true"
        logger.success(f"Secure mode enabled with bearer token")
        logger.debug(f"Bearer token set in environment")

    # Install packages if needed
    if config.needs_install:
        logger.debug(f"Configuration requires package installation")
        _install_packages_from_config(config)

    # Determine port based on mode
    port = client_server_port if single_package else client_server_all_port
    logger.debug(f"Using port {port} for {'single package' if single_package else 'unified'} mode")

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
    logger.debug(f"Processing {len(config.servers)} server(s) from configuration")

    for server_name, server_cfg in config.servers.items():
        logger.debug(f"Processing server: {server_name}")
        install_path = server_cfg.get("install_path")
        if not install_path:
            logger.warning(f"No installation path for server '{server_name}', skipping")
            continue

        install_path = Path(install_path)
        logger.debug(f"Installation path for {server_name}: {install_path}")

        if not install_path.exists():
            logger.warning(f"Installation path '{install_path}' does not exist, skipping")
            continue

        metadata_path = install_path / "metadata.json"
        if not metadata_path.exists():
            logger.warning(f"No metadata.json in '{install_path}', skipping")
            continue

        try:
            logger.info(f"Launching server '{server_name}' from: {install_path}")
            logger.debug(f"Calling launch_mcp_using_fastapi_proxy for {server_name}")
            package_name, router = launch_mcp_using_fastapi_proxy(install_path)

            if router:
                app.include_router(router, tags=[server_name])
                logger.info(f"Added {package_name} endpoints")
                launched_servers += 1
                logger.debug(f"Successfully launched server {server_name} ({launched_servers} total)")
            else:
                logger.error(f"Failed to create router for {server_name}")

        except Exception as e:
            logger.error(f"Error launching server '{server_name}': {e}")
            logger.debug(f"Exception details: {type(e).__name__}: {e}")

    logger.debug(f"Total servers launched: {launched_servers}")
    if launched_servers == 0:
        logger.error("No servers were successfully launched")
        return

    logger.success(f"Successfully launched {launched_servers} MCP server(s)")

    # Start FastAPI server if requested
    if start_server:
        _start_server(app, port, force_reload)


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
            logger.debug(f"Server '{server_name}' has no fmcp_package reference, skipping installation")
            continue

        logger.info(f"Installing package: {fmcp_package}")
        pkg = parse_package_string(fmcp_package)
        logger.debug(f"Parsed package: {pkg}")

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

            logger.debug(f"Package installed at: {dest_dir}")
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
                    logger.debug(f"Updated env variables for {fmcp_package}")
                except Exception as e:
                    logger.error(f"Error updating env for {fmcp_package}: {e}")

            # For master mode, update from shared .env
            if config.source_type == "s3_master":
                logger.debug(f"Updating from common .env for master mode")
                _update_env_from_common_env(dest_dir, pkg)

        except Exception as e:
            logger.error(f"Error installing {fmcp_package}: {e}")
            logger.debug(f"Exception details: {type(e).__name__}: {e}")


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
    logger.debug(f"_start_server called with port {port}, force_reload={force_reload}")

    if is_port_in_use(port):
        logger.warning(f"Port {port} is already in use.")
        if force_reload:
            logger.info(f"Force reloading server on port {port}")
            kill_process_on_port(port)
        else:
            choice = input("Kill existing process and reload? (y/n): ").strip().lower()
            if choice == 'y':
                logger.debug("User chose to kill existing process")
                kill_process_on_port(port)
            elif choice == 'n':
                logger.info(f"Keeping existing process on port {port}")
                return
            else:
                logger.error("Invalid choice. Aborting.")
                return

    logger.success(f"Starting FastAPI server on port {port}")
    logger.info(f"Swagger UI available at: http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)
