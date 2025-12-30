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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
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

    # Check authentication modes
    auth0_mode = os.environ.get("FMCP_AUTH0_MODE") == "true"
    jwt_mode = os.environ.get("FMCP_JWT_MODE") == "true"  # Legacy mode

    # Create FastAPI app
    app = FastAPI(
        title=f"FluidMCP Gateway ({config.source_type})",
        description=f"Unified gateway for MCP servers from {config.source_type}",
        version="2.0.0"
    )

    # CORS setup
    if auth0_mode or jwt_mode:
        # Restrict origins in auth modes (can be customized via env var)
        allowed_origins = os.environ.get("FMCP_ALLOWED_ORIGINS", "http://localhost:*,http://127.0.0.1:*").split(",")
    else:
        # Allow all origins in non-auth mode
        allowed_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth0 mode setup
    if auth0_mode:
        try:
            from fluidai_mcp.auth import Auth0Config, auth_router, init_auth_routes

            # Load Auth0 configuration
            auth_config = Auth0Config.from_env()
            auth_config.validate_required()

            # Initialize auth routes with config
            init_auth_routes(auth_config)

            # Mount auth static files
            auth_static_path = Path(__file__).parent.parent / "auth" / "static"
            if auth_static_path.exists():
                app.mount("/auth/static", StaticFiles(directory=str(auth_static_path)), name="auth_static")

            # Include auth router
            app.include_router(auth_router)

            # Root route - serve login page
            @app.get("/")
            async def root():
                return FileResponse(str(auth_static_path / "login.html"))

        except ValueError as e:
            print(f"❌ Auth0 configuration error: {e}")
            print("\nPlease set required environment variables:")
            print("  - AUTH0_DOMAIN")
            print("  - AUTH0_CLIENT_ID")
            print("  - AUTH0_CLIENT_SECRET")
            print("  - FMCP_JWT_SECRET")
            print("\nSee fluidai_mcp/auth/AUTH0_SETUP.md for setup instructions.")
            import sys
            sys.exit(1)

    # Legacy JWT mode setup (from old implementation)
    elif jwt_mode:
        static_path = Path(__file__).parent.parent / "static"
        if static_path.exists():
            app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

            # Include authentication routes (old implementation)
            try:
                from .auth_routes import router as auth_router
                app.include_router(auth_router)
            except ImportError:
                pass

            # Root route - serve login page
            @app.get("/")
            async def root():
                return FileResponse(str(static_path / "index.html"))
        else:
            # No static files, redirect to docs
            @app.get("/")
            async def root():
                return RedirectResponse(url="/docs")

    # No auth mode
    else:
        # In non-auth mode, redirect root to docs
        @app.get("/")
        async def root():
            return RedirectResponse(url="/docs")
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
            package_name, router = launch_mcp_using_fastapi_proxy(install_path)

            if router:
                app.include_router(router, tags=[server_name])
                print(f"Added {package_name} endpoints")
                launched_servers += 1
            else:
                print(f"Failed to create router for {server_name}")

        except Exception as e:
            print(f"Error launching server '{server_name}': {e}")

    if launched_servers == 0:
        print("No servers were successfully launched")
        return

    print(f"Successfully launched {launched_servers} MCP server(s)")

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


def _start_server(app: FastAPI, port: int, force_reload: bool) -> None:
    """
    Start the FastAPI server on the specified port.

    Args:
        app: FastAPI application
        port: Port to listen on
        force_reload: Force kill existing process without prompting
    """
    # Check for JWT mode and display security warning
    jwt_mode = os.environ.get("FMCP_JWT_MODE") == "true"
    if jwt_mode and not os.environ.get("FMCP_ALLOW_HTTP"):
        print("\n" + "=" * 70)
        print("⚠️  SECURITY WARNING: JWT authentication without HTTPS!")
        print("=" * 70)
        print("JWT tokens can be intercepted over HTTP.")
        print("For production use, consider:")
        print("  1. Using a reverse proxy with SSL (nginx, caddy, etc.)")
        print("  2. Deploying behind a secure gateway")
        print("  3. Using SSH tunneling for remote access")
        print("\nSet FMCP_ALLOW_HTTP=true to suppress this warning.")
        print("=" * 70 + "\n")

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

    logger.info(f"Starting FastAPI server on port {port}")
    print(f"\nStarting FastAPI server on port {port}")

    if jwt_mode:
        print(f"🔐 JWT Authentication: ENABLED")
        print(f"   Login at: http://localhost:{port}/")

    print(f"   Swagger UI: http://localhost:{port}/docs")
    print(f"\nServer running...\n")

    uvicorn.run(app, host="0.0.0.0", port=port)
