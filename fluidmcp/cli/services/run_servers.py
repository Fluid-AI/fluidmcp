"""
Unified server runner for FluidMCP CLI.

This module provides a single entry point for launching MCP servers
regardless of the configuration source.
"""
import os
import json
import atexit
import asyncio
import time
from pathlib import Path
from typing import Optional, Tuple, Dict
from loguru import logger

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx
import subprocess
import threading

from .config_resolver import ServerConfig, INSTALLATION_DIR
from .package_installer import install_package, parse_package_string
from .package_list import get_latest_version_dir
from .package_launcher import launch_mcp_using_fastapi_proxy
from .network_utils import is_port_in_use, kill_process_on_port
from .env_manager import update_env_from_config
from .llm_launcher import launch_llm_models, stop_all_llm_models, LLMProcess, LLMHealthMonitor
from .vllm_config import validate_and_transform_llm_config, VLLMConfigError
from .replicate_client import initialize_replicate_models, stop_all_replicate_models
from .llm_provider_registry import initialize_llm_registry, update_model_endpoints
from .frontend_utils import setup_frontend_routes
from ..auth import verify_token

# Default ports
client_server_port = int(os.environ.get("MCP_CLIENT_SERVER_PORT", "8090"))
client_server_all_port = int(os.environ.get("MCP_CLIENT_SERVER_ALL_PORT", "8099"))

# Constants for LLM operations
MAX_ERROR_MESSAGE_LENGTH = 1000  # Maximum length for error messages returned to clients
HTTP_CLIENT_TIMEOUT = 120.0  # Timeout in seconds for LLM HTTP requests
# Streaming timeout: None means indefinite (allows variable generation times)
# Set to a positive number (e.g., 300.0) to enforce a timeout in seconds
_timeout_env = os.getenv("LLM_STREAMING_TIMEOUT", "0")
try:
    _streaming_timeout_value = float(_timeout_env)
except ValueError:
    logger.warning(f"Invalid LLM_STREAMING_TIMEOUT value '{_timeout_env}', using indefinite timeout")
    _streaming_timeout_value = 0.0  # Normalize invalid values to 0.0
# Convert to None for indefinite timeout: value > 0 = timeout in seconds; value <= 0 (including normalized invalid values) = None (indefinite)
STREAMING_TIMEOUT = _streaming_timeout_value if _streaming_timeout_value > 0 else None
# Pre-create httpx.Timeout object to avoid recreating on each request
# Use granular timeouts: short for connect, indefinite/configurable for read (streaming data)
if STREAMING_TIMEOUT is None:
    STREAMING_TIMEOUT_CONFIG = httpx.Timeout(connect=30.0, read=None, write=30.0, pool=30.0)
else:
    STREAMING_TIMEOUT_CONFIG = httpx.Timeout(connect=30.0, read=STREAMING_TIMEOUT, write=30.0, pool=30.0)

# Pre-constructed SSE error messages for better performance
_SSE_ERROR_TEMPLATES = {
    "stream_not_set": json.dumps({"error": {"message": "Internal error: streaming function called for non-streaming request", "type": "internal_error"}}),
    "model_removed": json.dumps({"error": {"message": "Model configuration was removed", "type": "model_unavailable"}}),
    "endpoint_missing": json.dumps({"error": {"message": "Endpoint not configured", "type": "configuration_error"}}),
    "connection_error": json.dumps({"error": {"message": "LLM backend is not ready or unreachable. The model server may still be starting up. Please verify: (1) the vLLM process is running, (2) the configured port is accessible, and (3) check logs for details.", "type": "connection_error"}}),
}

# Explicit process registry for server tracking
_server_processes: Dict[str, subprocess.Popen] = {}

# LLM process registry
_llm_processes: Dict[str, LLMProcess] = {}

# LLM endpoint configurations
_llm_endpoints: Dict[str, Dict[str, str]] = {}

# LLM health monitor
_llm_health_monitor: Optional[LLMHealthMonitor] = None

# Getter functions for management API (avoids circular import issues)
def get_llm_processes() -> Dict[str, LLMProcess]:
    """Get the LLM processes registry. Used by management API."""
    return _llm_processes

def get_llm_health_monitor() -> Optional[LLMHealthMonitor]:
    """Get the LLM health monitor instance. Used by management API."""
    return _llm_health_monitor
# Thread-safety locks for process stdin/stdout communication
_process_locks: Dict[str, threading.Lock] = {}

# Thread-safety lock for LLM registry operations
_llm_registry_lock = threading.Lock()

# Shared HTTP client for LLM proxy (connection pooling)
_http_client: Optional[httpx.AsyncClient] = None
_http_client_lock: Optional[asyncio.Lock] = None  # Initialized on first async use

# Cleanup synchronization
_cleanup_lock = threading.Lock()
_cleanup_done = False

# Server start times for uptime tracking (server_name -> start timestamp)
_server_start_times: Dict[str, float] = {}
_server_start_times_lock = threading.Lock()


def _initialize_server_metrics(server_name: str) -> None:
    """
    Initialize metrics for a newly launched server.

    Args:
        server_name: Name of the server to initialize metrics for
    """
    from .metrics import MetricsCollector

    # Record server start time for uptime calculation
    with _server_start_times_lock:
        _server_start_times[server_name] = time.monotonic()

    # Initialize metrics collector
    collector = MetricsCollector(server_name)

    # Set initial server status to running (2)
    collector.set_server_status(2)

    # Set initial uptime to 0
    collector.set_uptime(0.0)

    logger.debug(f"Initialized metrics for server: {server_name}")


async def _start_llm_health_monitor_async():
    """
    Start background health monitor for LLM processes (async version).

    Only starts if there are LLM processes with restart policies enabled.
    This is called during FastAPI startup event when event loop is running.
    """
    global _llm_health_monitor

    # Check if there are any processes with restart policies
    processes_with_restart = {
        model_id: process
        for model_id, process in _llm_processes.items()
        if process.restart_policy != "no"
    }

    if not processes_with_restart:
        logger.info("No LLM processes with restart policies, health monitor not started")
        return

    # Stop existing monitor if running
    if _llm_health_monitor and _llm_health_monitor.is_running():
        logger.info("Stopping existing LLM health monitor...")
        await _llm_health_monitor.stop()

    # Create and start new health monitor (only monitor processes with restart policies)
    logger.info(f"Starting health monitor for {len(processes_with_restart)} LLM process(es) with restart policies")
    _llm_health_monitor = LLMHealthMonitor(processes_with_restart)
    _llm_health_monitor.start()


def _extract_port_from_args(args) -> int:
    """
    Extract port number from command line arguments.

    Supports common CLI patterns:
    - --port 8001
    - -p 8001
    - --port=8001

    Args:
        args: Command line arguments (list or string)

    Returns:
        int: Extracted port number, or 8001 as default
    """
    # Normalize args to list of strings
    if isinstance(args, str):
        args_list = args.split()
    else:
        try:
            args_list = list(args)
        except TypeError:
            return 8001

    # Try to extract port from common CLI patterns
    for i, arg in enumerate(args_list):
        # Pattern: --port 8001 or -p 8001
        if arg in ("--port", "-p") and i + 1 < len(args_list):
            try:
                return int(args_list[i + 1])
            except ValueError:
                continue
        # Pattern: --port=8001
        if arg.startswith("--port="):
            _, _, value = arg.partition("=")
            try:
                return int(value)
            except ValueError:
                continue

    # Default fallback
    return 8001


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
        logger.info("Secure mode enabled with bearer token")

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

    # Serve frontend from backend (single-port deployment)
    setup_frontend_routes(app, host="0.0.0.0", port=port)

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

            # Create or get lock for this server
            if server_name not in _process_locks:
                _process_locks[server_name] = threading.Lock()

            package_name, router, process = launch_mcp_using_fastapi_proxy(
                install_path,
                _process_locks[server_name]
            )

            if router and process:
                app.include_router(router, tags=[server_name])
                _register_server_process(server_name, process)  # Register in explicit registry

                # Initialize metrics for the server
                _initialize_server_metrics(server_name)

                logger.info(f"Added {package_name} endpoints")
                launched_servers += 1
                logger.debug(f"Successfully launched server {server_name} ({launched_servers} total)")
            else:
                logger.error(f"Failed to create router for {server_name}")

        except Exception:
            logger.exception(f"Error launching server '{server_name}'")

    logger.debug(f"Total MCP servers launched: {launched_servers}")
    if launched_servers == 0 and not config.llm_models:
        logger.warning("No servers or LLM models configured - nothing to launch")
        return

    if launched_servers > 0:
        logger.info(f"Successfully launched {launched_servers} MCP server(s)")

    # Launch LLM models if configured (supports multiple types: vllm, replicate, etc.)
    if config.llm_models:
        logger.info(f"Processing {len(config.llm_models)} LLM model(s)...")

        # Separate models by type
        vllm_models = {}
        replicate_models = {}

        for model_id, model_config in config.llm_models.items():
            model_type = model_config.get("type", "vllm")  # Default to vllm for backward compat

            if model_type == "vllm":
                vllm_models[model_id] = model_config
            elif model_type == "replicate":
                replicate_models[model_id] = model_config
            else:
                logger.warning(f"Model '{model_id}' has unsupported type '{model_type}', skipping")

        # Initialize unified LLM provider registry for all models
        initialize_llm_registry(config.llm_models)

        # Launch vLLM models
        if vllm_models:
            logger.info(f"Validating and transforming {len(vllm_models)} vLLM model config(s)...")
            validated_llm_config = None
            try:
                # Validate and transform high-level configs to vLLM args
                validated_llm_config = validate_and_transform_llm_config(vllm_models)
                logger.info(f"✓ vLLM configuration validated successfully")
            except VLLMConfigError as e:
                logger.error(f"vLLM configuration validation failed: {e}")
                logger.error("Skipping vLLM models - will continue with other model types if configured")
                if launched_servers > 0:
                    logger.info(
                        f"Note: {launched_servers} MCP server(s) were launched successfully. "
                        "They will continue running."
                    )
                # Don't return - continue to initialize Replicate models if configured
                validated_llm_config = None  # Clear to skip vLLM launch

            # Only launch if validation succeeded
            if validated_llm_config:
                logger.info(f"Launching {len(validated_llm_config)} vLLM model(s)...")
                llm_processes = launch_llm_models(validated_llm_config)

                # Thread-safe update of LLM registries
                with _llm_registry_lock:
                    _llm_processes.update(llm_processes)

                    # Register LLM endpoints only for successfully running processes
                    for model_id in llm_processes.keys():
                        model_config = validated_llm_config[model_id]
                        endpoints = model_config.get("endpoints", {})

                        # Determine base_url with smart port extraction
                        base_url = endpoints.get("base_url")
                        if not base_url:
                            # Try to extract port from command args
                            port = _extract_port_from_args(model_config.get("args", []))
                            base_url = f"http://localhost:{port}/v1"
                            logger.debug(f"Inferred base_url for '{model_id}': {base_url}")

                        _llm_endpoints[model_id] = {
                            "base_url": base_url,
                            "chat": endpoints.get("chat", "/chat/completions"),
                            "completions": endpoints.get("completions", "/completions"),
                            "models": endpoints.get("models", "/models"),
                        }
                        logger.info(f"Registered vLLM endpoints for '{model_id}' at {base_url}")

                        # Update registry with inferred base_url for unified API
                        update_model_endpoints(model_id, {"base_url": base_url})

                # Add OpenAI proxy routes if any models started successfully
                if _llm_endpoints:
                    _add_llm_proxy_routes(app)
                else:
                    logger.warning("No vLLM models started successfully - skipping proxy routes")

                # Register startup event to start health monitor after event loop is running
                @app.on_event("startup")
                async def startup_health_monitor():
                    """Start LLM health monitor when FastAPI server starts."""
                    await _start_llm_health_monitor_async()

        # Initialize Replicate models
        if replicate_models:
            logger.info(f"Initializing {len(replicate_models)} Replicate model(s)...")

            # Register startup event to initialize Replicate clients
            @app.on_event("startup")
            async def startup_replicate_models():
                """Initialize Replicate models when FastAPI server starts."""
                try:
                    replicate_clients = await initialize_replicate_models(replicate_models)
                    if replicate_clients:
                        logger.info(f"Successfully initialized {len(replicate_clients)} Replicate model(s)")
                    else:
                        logger.warning("No Replicate models initialized successfully")
                except Exception as e:
                    logger.error(f"Error initializing Replicate models: {e}")

            # Register shutdown event to cleanup Replicate clients on same event loop
            @app.on_event("shutdown")
            async def shutdown_replicate_models():
                """Cleanup Replicate models when FastAPI server shuts down."""
                try:
                    await stop_all_replicate_models()
                    logger.info("Replicate clients shutdown completed")
                except Exception as e:
                    logger.error(f"Error during Replicate clients shutdown: {e}")

        # Register global shutdown event for HTTP client cleanup (used by vLLM proxy and other features)
        # This runs regardless of whether Replicate models are configured
        @app.on_event("shutdown")
        async def shutdown_http_client():
            """Cleanup management API's shared HTTP client (used for vLLM proxying and more)."""
            try:
                from ..api.management import cleanup_http_client
                await cleanup_http_client()
                logger.info("Management HTTP client shutdown completed")
            except Exception as e:
                logger.error(f"Error during management HTTP client shutdown: {e}")

        # Final check: warn if no models of any type actually launched/initialized
        vllm_launched = bool(_llm_processes)
        replicate_will_init = bool(replicate_models)  # Will be initialized on startup

        if not vllm_launched and not replicate_will_init:
            if launched_servers == 0:
                logger.error("No MCP servers or LLM models successfully configured - aborting")
                return
            else:
                logger.warning("No LLM models successfully launched, but MCP servers are running")

    # Add unified tool discovery endpoint
    _add_unified_tools_endpoint(app, secure_mode)

    # Add health check endpoint
    _add_health_endpoint(app)

    # Add Prometheus metrics endpoint
    _add_metrics_endpoint(app)

    # Add management API endpoints
    from ..api.management import router as management_router
    app.include_router(management_router, prefix="/api", tags=["management"])
    logger.debug("Management API endpoints added")

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


async def _query_server_tools(server_name: str, process: subprocess.Popen, lock: threading.Lock) -> Tuple[str, list, Optional[str]]:
    """
    Query a single MCP server for its available tools.

    Args:
        server_name: Name of the server
        process: Server process handle
        lock: Thread lock for safe stdin/stdout communication

    Returns:
        Tuple of (server_name, tools_list, error_message)
        - tools_list is empty if there was an error
        - error_message is None if successful
    """
    try:
        # Check if process is still alive
        if process.poll() is not None:
            return (server_name, [], "Process is not running")

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
                return (server_name, [], "Timeout waiting for response")

        # Strip whitespace/newlines before checking and parsing
        response_line_stripped = response_line.strip()
        if not response_line_stripped:
            logger.warning(f"Empty response (after stripping) from server: {server_name}")
            return (server_name, [], "Empty response from server")

        response_data = json.loads(response_line_stripped)

        # Check for JSON-RPC error
        if "error" in response_data:
            error_msg = response_data["error"].get("message", "Unknown error")
            logger.warning(f"Error from server {server_name}: {error_msg}")
            return (server_name, [], f"JSON-RPC error: {error_msg}")

        # Extract tools from response
        if "result" in response_data and "tools" in response_data["result"]:
            server_tools = response_data["result"]["tools"]

            # Create new tool dicts with server label (don't mutate originals)
            tools_with_server = []
            for tool in server_tools:
                new_tool = dict(tool)
                new_tool["server"] = server_name
                tools_with_server.append(new_tool)

            logger.debug(f"Found {len(server_tools)} tools from {server_name}")
            return (server_name, tools_with_server, None)
        else:
            logger.warning(f"Unexpected response format from {server_name}")
            return (server_name, [], "Unexpected response format")

    except json.JSONDecodeError as e:
        logger.error(
            f"Invalid JSON response from {server_name}: {e}. "
            f"Raw response: {response_line_stripped!r}"
        )
        return (server_name, [], f"Invalid JSON: {e}")
    except Exception as e:
        logger.error(f"Error querying tools from {server_name}: {e}")
        return (server_name, [], str(e))


async def _get_http_client() -> httpx.AsyncClient:
    """Get or create shared HTTP client for LLM proxy requests (thread-safe)."""
    global _http_client, _http_client_lock

    # Initialize lock on first use (can't do at module level due to event loop requirements)
    if _http_client_lock is None:
        _http_client_lock = asyncio.Lock()

    # Double-check locking pattern for thread-safe singleton
    if _http_client is None:
        async with _http_client_lock:
            if _http_client is None:  # Double check after acquiring lock
                # Use granular timeout: reasonable for connect/write/pool, longer for read (non-streaming)
                _http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=30.0, read=HTTP_CLIENT_TIMEOUT, write=30.0, pool=30.0)
                )

    return _http_client


async def _proxy_llm_request(
    model_id: str,
    endpoint_key: str,
    method: str = "POST",
    body: Optional[dict] = None
) -> dict:
    """
    Common proxy logic for LLM requests.

    Args:
        model_id: LLM model identifier
        endpoint_key: Key in endpoints config ('chat', 'completions', 'models')
        method: HTTP method (POST or GET)
        body: Request body for POST requests

    Returns:
        Response JSON from LLM backend

    Raises:
        HTTPException: Various HTTP errors based on backend response
    """
    # Thread-safe snapshot of endpoint and process info
    with _llm_registry_lock:
        endpoint_config = _llm_endpoints.get(model_id)
        process = _llm_processes.get(model_id)

    if endpoint_config is None:
        raise HTTPException(404, f"LLM model '{model_id}' not configured")

    if endpoint_key not in endpoint_config:
        raise HTTPException(404, f"Endpoint '{endpoint_key}' not configured for model '{model_id}'")

    # Check if process is still running (if registered)
    if process is not None and not process.is_running():
        raise HTTPException(503, f"LLM model '{model_id}' process is not running")

    url = f"{endpoint_config['base_url']}{endpoint_config[endpoint_key]}"

    client = await _get_http_client()

    try:
        if method == "POST":
            response = await client.post(url, json=body)
        else:  # GET
            response = await client.get(url)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError as e:
        logger.error(f"LLM connection error for {model_id}: {e}")
        raise HTTPException(503, f"LLM backend not ready or unreachable. The model may still be loading.")
    except httpx.TimeoutException as e:
        logger.error(f"LLM timeout for {model_id}: {e}")
        raise HTTPException(504, f"LLM backend timeout: {str(e)}")
    except httpx.HTTPStatusError as e:
        response_text = e.response.text or ""
        logger.error(f"LLM HTTP error for {model_id}: {e}. Status: {e.response.status_code}, Response: {response_text}")

        # Truncate large error messages to prevent response size issues
        if len(response_text) > MAX_ERROR_MESSAGE_LENGTH:
            truncated_text = response_text[:MAX_ERROR_MESSAGE_LENGTH] + "... [truncated]"
        else:
            truncated_text = response_text

        raise HTTPException(e.response.status_code, f"LLM backend error: {truncated_text}")
    except httpx.HTTPError as e:
        logger.error(f"LLM proxy error for {model_id}: {e}")
        raise HTTPException(502, f"LLM backend error: {str(e)}")


def _validate_streaming_request(model_id: str, endpoint_key: str) -> None:
    """
    Validate that a model is available for streaming before starting SSE response.

    This MUST be called before creating a StreamingResponse, as FastAPI cannot
    raise HTTPException after the response has started.

    Args:
        model_id: LLM model identifier
        endpoint_key: Key in endpoints config ('chat', 'completions')

    Raises:
        HTTPException: 404 if model not configured or endpoint key invalid, 503 if process not running
    """
    with _llm_registry_lock:
        endpoint_config = _llm_endpoints.get(model_id)
        process = _llm_processes.get(model_id)

    if endpoint_config is None:
        raise HTTPException(404, f"LLM model '{model_id}' not configured")

    if endpoint_key not in endpoint_config:
        raise HTTPException(404, f"Endpoint '{endpoint_key}' not configured for model '{model_id}'")

    if process is not None and not process.is_running():
        raise HTTPException(503, f"LLM model '{model_id}' process is not running")


async def _proxy_llm_request_streaming(model_id: str, endpoint_key: str, body: dict):
    """
    Proxy LLM streaming requests using Server-Sent Events (SSE).

    Note: Model availability validation should be done BEFORE calling this function
    to avoid errors after the streaming response has started.

    Args:
        model_id: LLM model identifier
        endpoint_key: Key in endpoints config ('chat', 'completions')
        body: Request body (must have stream=true)

    Yields:
        SSE-formatted chunks from LLM backend
    """
    # Defensive check: ensure stream parameter is set
    if not body.get("stream"):
        logger.error(f"_proxy_llm_request_streaming called without stream=true for {model_id}")
        yield f"data: {_SSE_ERROR_TEMPLATES['stream_not_set']}\n\n".encode()
        return

    # Get endpoint configuration (already validated by caller)
    with _llm_registry_lock:
        endpoint_config = _llm_endpoints.get(model_id)

    # Defensive check: endpoint could be removed between validation and here (rare race condition)
    # NOTE: If this happens, we send an SSE error event instead of raising HTTPException
    # because we cannot raise exceptions inside an async generator that's already been
    # passed to StreamingResponse. This is the intended behavior for post-validation failures.
    # Mid-stream errors are part of SSE protocol - clients should handle error events gracefully.
    if endpoint_config is None:
        logger.warning(f"LLM endpoint removed for {model_id} after validation (race condition)")
        yield f"data: {_SSE_ERROR_TEMPLATES['model_removed']}\n\n".encode()
        return

    # Defensive check: ensure endpoint_key exists in config
    # This should never happen in practice (endpoints are created at startup),
    # but defensive programming prevents KeyError
    if endpoint_key not in endpoint_config:
        logger.warning(f"Missing endpoint '{endpoint_key}' for model {model_id} (should not happen)")
        yield f"data: {_SSE_ERROR_TEMPLATES['endpoint_missing']}\n\n".encode()
        return

    url = f"{endpoint_config['base_url']}{endpoint_config[endpoint_key]}"

    client = await _get_http_client()

    try:
        # Stream the request to vLLM backend with stream=true
        # Use pre-configured timeout object (created at module init to avoid recreation on each request)
        async with client.stream("POST", url, json=body, timeout=STREAMING_TIMEOUT_CONFIG) as response:
            response.raise_for_status()

            # Stream SSE chunks from backend to client
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk

    except httpx.ConnectError as e:
        logger.error(f"LLM streaming connection error for {model_id}: {e}")
        # Send error as SSE event
        yield f"data: {_SSE_ERROR_TEMPLATES['connection_error']}\n\n".encode()
    except httpx.TimeoutException as e:
        logger.error(f"LLM streaming timeout for {model_id}: {e}")
        error_data = {"error": {"message": f"LLM backend timeout: {str(e)}", "type": "timeout_error"}}
        yield f"data: {json.dumps(error_data)}\n\n".encode()
    except httpx.HTTPStatusError as e:
        logger.error(f"LLM streaming HTTP error for {model_id}: {e}. Status: {e.response.status_code}")

        # Try to get response text, handling cases where it's unavailable in streaming context
        try:
            response_text = e.response.text or ""
        except (AttributeError, RuntimeError) as text_error:
            logger.debug(f"Failed to read error response text for {model_id}: {text_error}")
            response_text = f"HTTP {e.response.status_code}"

        # Truncate large error messages
        if len(response_text) > MAX_ERROR_MESSAGE_LENGTH:
            truncated_text = response_text[:MAX_ERROR_MESSAGE_LENGTH] + "... [truncated]"
        else:
            truncated_text = response_text

        error_data = {"error": {"message": truncated_text, "type": "http_error", "status": e.response.status_code}}
        yield f"data: {json.dumps(error_data)}\n\n".encode()
    except httpx.HTTPError as e:
        logger.error(f"LLM streaming proxy error for {model_id}: {e}")
        error_data = {"error": {"message": str(e), "type": "proxy_error"}}
        yield f"data: {json.dumps(error_data)}\n\n".encode()


def _add_llm_proxy_routes(app: FastAPI) -> None:
    """
    Add OpenAI-compatible proxy routes for LLM models.

    Creates endpoints with /llm prefix to avoid conflicts with MCP server names:
    - POST /llm/v1/chat/completions
    - POST /llm/v1/completions
    - GET /llm/v1/models

    Args:
        app: FastAPI application instance
    """
    @app.post("/llm/v1/chat/completions", tags=["llm"])
    async def proxy_chat_completions(request: Request):
        """Proxy OpenAI chat completions to LLM backend with optional streaming support."""
        body = await request.json()

        # Extract model_id from request body (OpenAI-style)
        model_id = body.get("model")
        if not model_id:
            raise HTTPException(status_code=400, detail="Missing required field 'model' in request body")

        # Check if streaming is requested
        if body.get("stream", False):
            # Validate model availability BEFORE starting stream
            _validate_streaming_request(model_id, "chat")

            return StreamingResponse(
                _proxy_llm_request_streaming(model_id, "chat", body),
                media_type="text/event-stream"
            )

        # Non-streaming request
        return await _proxy_llm_request(model_id, "chat", "POST", body)

    @app.post("/llm/v1/completions", tags=["llm"])
    async def proxy_completions(request: Request):
        """Proxy OpenAI completions to LLM backend with optional streaming support."""
        body = await request.json()

        # Extract model_id from request body (OpenAI-style)
        model_id = body.get("model")
        if not model_id:
            raise HTTPException(status_code=400, detail="Missing required field 'model' in request body")

        # Check if streaming is requested
        if body.get("stream", False):
            # Validate model availability BEFORE starting stream
            _validate_streaming_request(model_id, "completions")

            return StreamingResponse(
                _proxy_llm_request_streaming(model_id, "completions", body),
                media_type="text/event-stream"
            )

        # Non-streaming request
        return await _proxy_llm_request(model_id, "completions", "POST", body)

    @app.get("/llm/v1/models", tags=["llm"])
    async def proxy_models(model: str = None):
        """Proxy models list endpoint to LLM backend."""
        if model:
            # Return specific model details
            return await _proxy_llm_request(model, "models", "GET")
        else:
            # Return all configured models in OpenAI format
            with _llm_registry_lock:
                endpoints_snapshot = dict(_llm_endpoints)

            created_timestamp = int(time.time())
            all_models = []
            for model_id in endpoints_snapshot.keys():
                all_models.append({
                    "id": model_id,
                    "object": "model",
                    "created": created_timestamp,
                    "owned_by": "fluidmcp",
                    "permission": [],
                    "root": model_id,
                    "parent": None
                })

            return {
                "object": "list",
                "data": all_models
            }

    @app.get("/api/llm/status", tags=["llm"])
    async def llm_status():
        """Get status of all configured LLM models."""
        status = {}

        # Thread-safe snapshot of registries to avoid race conditions
        with _llm_registry_lock:
            endpoints_snapshot = dict(_llm_endpoints)
            processes_snapshot = dict(_llm_processes)

        for model_id, endpoint_cfg in endpoints_snapshot.items():
            process = processes_snapshot.get(model_id)
            is_running = process.is_running() if process is not None else False

            status[model_id] = {
                "configured": True,
                "running": is_running,
                "base_url": endpoint_cfg["base_url"]
            }

        return {
            "models": status,
            "total_models": len(status),
            "running_models": sum(1 for s in status.values() if s["running"])
        }

    logger.info(f"Added OpenAI proxy routes for {len(_llm_endpoints)} LLM model(s)")


def _add_unified_tools_endpoint(app: FastAPI, secure_mode: bool) -> None:
    """
    Add GET /api/tools endpoint for unified tool discovery across all MCP servers.

    Args:
        app: FastAPI application instance
        secure_mode: Whether secure mode is enabled (unused, kept for API compatibility)
    """
    from .package_launcher import get_token

    @app.get("/api/tools", tags=["unified"])
    async def get_all_tools(token: str = Depends(get_token)):
        """
        Dynamic tool discovery across all running MCP servers.

        Returns:
            JSONResponse: A JSON response with the following structure:
                {
                    "tools": [
                        {
                            "name": str,
                            "description": str,
                            "input_schema": dict,   # Tool input schema as returned by the MCP server
                            "server": str           # Identifier/label of the MCP server providing the tool
                        },
                        ...
                    ],
                    "summary": {
                        "total_tools": int,          # Total number of discovered tools
                        "servers": list[str],        # List of server identifiers that responded successfully
                        "server_count": int,         # Number of servers that responded successfully
                        "error_count": int,          # Number of servers that returned an error or no tools
                        "servers_with_errors": list[str] | None  # Optional: identifiers of servers that had errors
                    }
                }
        """
        all_tools = []
        servers_found = []
        servers_with_errors = set()  # Use set to avoid duplicates

        # Get server processes from explicit registry
        server_processes = _get_server_processes()

        logger.info(f"Discovering tools from {len(server_processes)} MCP server(s)")

        # Clean up stale locks for servers that no longer exist
        current_server_names = set(server_processes.keys())
        stale_server_names = set(_process_locks.keys()) - current_server_names
        for stale_name in stale_server_names:
            del _process_locks[stale_name]
            logger.debug(f"Removed stale lock for server: {stale_name}")

        # Ensure all servers have locks
        for server_name in server_processes:
            if server_name not in _process_locks:
                _process_locks[server_name] = threading.Lock()

        # Query all servers concurrently using asyncio.gather
        query_tasks = [
            _query_server_tools(server_name, process, _process_locks[server_name])
            for server_name, process in server_processes.items()
        ]

        # Execute all queries concurrently with individual timeouts
        results = await asyncio.gather(*query_tasks, return_exceptions=True)

        # Process results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Unexpected error during concurrent query: {result}")
                continue

            server_name, tools, error = result
            if error:
                servers_with_errors.add(server_name)
            else:
                all_tools.extend(tools)
                servers_found.append(server_name)

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
            response["summary"]["servers_with_errors"] = list(servers_with_errors)

        logger.info(f"Tool discovery complete: {len(all_tools)} tools from {len(servers_found)} servers")

        return JSONResponse(content=response)


def _add_health_endpoint(app: FastAPI) -> None:
    """
    Add GET /health endpoint for health checks.

    Args:
        app: FastAPI application instance
    """
    @app.get("/health", tags=["monitoring"])
    async def health_check() -> JSONResponse:
        """
        Health check endpoint.

        Returns server health status with appropriate HTTP status codes:
        - 200 OK: Server is healthy (at least one server running)
        - 503 Service Unavailable: Server is degraded or unhealthy

        Returns:
            JSONResponse with health status, server count, and running server count
        """
        try:
            processes = _get_server_processes()
            if processes is None:
                processes = {}

            # Count running servers (check if process is not None and still alive)
            running_count = sum(1 for p in processes.values() if p and p.poll() is None)

            # Determine health status
            status = "healthy" if running_count > 0 else "degraded"
            status_code = 200 if running_count > 0 else 503

            response_data = {
                "status": status,
                "servers": len(processes),
                "running_servers": running_count,
            }

            return JSONResponse(
                status_code=status_code,
                content=response_data
            )

        except Exception as e:
            # Log full error for debugging but return generic message to client
            logger.error(f"Health check failed: {e}", exc_info=True)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "error": "Internal server error during health check",
                    "servers": 0,
                    "running_servers": 0
                }
            )


def _add_metrics_endpoint(app: FastAPI) -> None:
    """
    Add GET /metrics endpoint for Prometheus-compatible metrics.

    Args:
        app: FastAPI application instance
    """
    from fastapi.responses import PlainTextResponse
    from .metrics import get_registry

    @app.get("/metrics", tags=["monitoring"], dependencies=[Depends(verify_token)])
    async def metrics():
        """
        Prometheus-compatible metrics endpoint.

        Requires bearer token authentication when FMCP_SECURE_MODE=true.
        Public access when secure mode is disabled.

        Exposes metrics in Prometheus exposition format:
        - Request counters and histograms
        - Server status and uptime (dynamically calculated)
        - GPU memory utilization
        - Tool execution metrics
        - Streaming request metrics
        """
        # Update uptime for all running servers before rendering metrics
        # Compute uptimes under lock (fast), then update metrics outside (can be slow)
        with _server_start_times_lock:
            current_time = time.monotonic()
            uptimes = {name: current_time - start for name, start in _server_start_times.items()}

        # Update metrics outside lock to minimize lock duration
        for server_name, uptime in uptimes.items():
            collector = MetricsCollector(server_name)
            collector.set_uptime(uptime)

        # Update Replicate metrics (cache and rate limiters) before rendering
        # This ensures Prometheus scrapes always reflect current state
        try:
            from .replicate_metrics import update_cache_metrics, update_rate_limiter_metrics
            await update_cache_metrics()
            await update_rate_limiter_metrics()
        except ModuleNotFoundError as e:
            # Missing dependency (truly optional, should not happen in normal deployment)
            # Must catch ModuleNotFoundError first (subclass of ImportError)
            logger.debug(f"Replicate metrics module not found (optional dependency): {e}")
        except ImportError as e:
            # Replicate metrics module import failed (unexpected, should be part of codebase)
            logger.warning(f"Failed to import Replicate metrics (unexpected packaging issue): {e}")
        except Exception as e:
            # Other errors - log with stack trace but don't fail metrics endpoint
            logger.warning(f"Failed to update Replicate metrics: {e}", exc_info=True)

        registry = get_registry()
        # Prometheus text exposition format v0.0.4 (not OpenMetrics)
        return PlainTextResponse(
            content=registry.render_all(),
            media_type="text/plain; version=0.0.4; charset=utf-8"
        )


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
                except Exception:
                    logger.exception(f"Error updating env for {fmcp_package}")

            # For master mode, update from shared .env
            if config.source_type == "s3_master":
                logger.debug(f"Updating from common .env for master mode")
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


def _cleanup_resources():
    """Cleanup all LLM processes on shutdown (thread-safe, idempotent)."""
    global _cleanup_done, _http_client, _llm_health_monitor

    with _cleanup_lock:
        if _cleanup_done:
            return

        # Stop health monitor if running
        # Note: This is called from atexit/signal handler (not async context)
        # The monitor task runs on uvicorn's loop, so we signal it to stop
        # and let it clean up naturally rather than forcing from different loop
        if _llm_health_monitor and _llm_health_monitor.is_running():
            logger.info("Stopping LLM health monitor...")
            try:
                # Set the stop flag - the monitor will clean up on its loop
                _llm_health_monitor._running = False
                logger.info("Health monitor stop signal sent")
            except Exception as e:
                logger.warning(f"Error stopping health monitor: {e}")
            finally:
                _llm_health_monitor = None

        if _llm_processes:
            logger.info("Shutting down LLM processes...")
            stop_all_llm_models(_llm_processes)
            _llm_processes.clear()

        # Stop all Replicate clients (fallback - should be handled by FastAPI shutdown event)
        # This is only reached if atexit is triggered before FastAPI shutdown
        logger.debug("Attempting fallback Replicate clients cleanup...")
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(stop_all_replicate_models())
            logger.debug("Replicate clients stopped successfully (fallback)")
        except Exception as e:
            logger.warning(f"Error during Replicate clients cleanup (fallback): {e}")
        finally:
            loop.close()

        # Close shared HTTP client
        if _http_client is not None:
            try:
                # Use a fresh event loop for cleanup to ensure it completes
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(_http_client.aclose())
                    logger.debug("HTTP client closed successfully")
                except Exception as e:
                    logger.warning(f"Error during HTTP client cleanup: {e}")
                finally:
                    try:
                        loop.close()
                    except Exception as e:
                        logger.debug(f"Error closing event loop: {e}")
            finally:
                # Always clear the reference even if cleanup failed
                _http_client = None

        _cleanup_done = True


async def _serve_async(app: FastAPI, port: int) -> None:
    """
    Run the FastAPI server inside an asyncio event loop with graceful shutdown support.

    When used with asyncio.run(), this will block the calling thread while running
    the server until shutdown is requested via signal (SIGINT/SIGTERM).
    Uvicorn handles signal processing internally for graceful shutdown.

    Args:
        app: FastAPI application
        port: Port to listen on
    """
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )
    server = uvicorn.Server(config)

    # Run the server (uvicorn handles signal processing internally)
    await server.serve()


def _start_server(app: FastAPI, port: int, force_reload: bool) -> None:
    """
    Start the FastAPI server on the specified port.

    This function handles port conflict resolution and runs the server
    using asyncio for better control and graceful shutdown support.

    Args:
        app: FastAPI application
        port: Port to listen on
        force_reload: Force kill existing process without prompting
    """
    logger.debug(f"_start_server called with port {port}, force_reload={force_reload}")

    if is_port_in_use(port):
        if force_reload:
            logger.info(f"Port {port} is already in use - force reloading")
            kill_process_on_port(port)

            # Wait for socket to be released with configurable timeout
            default_release_timeout = 5.0
            env_timeout = os.environ.get("MCP_PORT_RELEASE_TIMEOUT")
            if env_timeout is None or env_timeout == "":
                release_timeout = default_release_timeout
            else:
                try:
                    release_timeout = float(env_timeout)
                    if release_timeout <= 0:
                        logger.warning(
                            f"Invalid MCP_PORT_RELEASE_TIMEOUT value {env_timeout!r} (must be positive); "
                            f"using default {default_release_timeout} seconds instead."
                        )
                        release_timeout = default_release_timeout
                except ValueError:
                    logger.warning(
                        f"Invalid MCP_PORT_RELEASE_TIMEOUT value {env_timeout!r}; "
                        f"using default {default_release_timeout} seconds instead."
                    )
                    release_timeout = default_release_timeout

            start_time = time.time()
            logger.info(f"Waiting for port {port} to be released (timeout: {release_timeout}s)")

            while is_port_in_use(port) and (time.time() - start_time) < release_timeout:
                time.sleep(0.1)

            if is_port_in_use(port):
                logger.error(
                    f"Port {port} is still in use after waiting {release_timeout} seconds. "
                    f"Aborting server start. Increase MCP_PORT_RELEASE_TIMEOUT if needed."
                )
                return

            logger.info("Port released, starting new server")
        else:
            logger.error(
                f"Port {port} is already in use. "
                f"Use --force-reload flag to restart the server automatically."
            )
            return

    # Register cleanup handler for graceful shutdown
    # Note: Python's atexit does NOT deduplicate handlers; _cleanup_resources is idempotent,
    # so registering it multiple times is safe even if _start_server is called repeatedly
    atexit.register(_cleanup_resources)

    # Let uvicorn handle SIGTERM/SIGINT for graceful shutdown
    # atexit will handle LLM cleanup when the process exits

    logger.info(f"Swagger UI available at: http://localhost:{port}/docs")
    logger.info("Press Ctrl+C to stop the server")

    try:
        # Run server with asyncio for graceful shutdown support
        asyncio.run(_serve_async(app, port))
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        _cleanup_resources()
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        _cleanup_resources()
