"""
Standalone FluidMCP backend server.

This module provides a persistent API server that can run independently
and manage MCP servers dynamically via HTTP API.
"""
import argparse
import asyncio
import os
import signal
import secrets
from pathlib import Path
from loguru import logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import Config, Server

from .repositories import DatabaseManager, InMemoryBackend, PersistenceBackend
from .services.server_manager import ServerManager
from .api.management import router as mgmt_router
from .services.package_launcher import create_dynamic_router
from .services.metrics import get_registry
from .services.frontend_utils import setup_frontend_routes


def save_token_to_file(token: str) -> Path:
    """
    Save bearer token to secure file.

    Args:
        token: Bearer token to save

    Returns:
        Path to saved token file
    """
    token_dir = Path.home() / ".fmcp" / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)

    token_file = token_dir / "current_token.txt"
    token_file.write_text(token)

    # Set restrictive permissions (owner read/write only)
    token_file.chmod(0o600)

    logger.info(f"Token saved to: {token_file}")
    return token_file


async def create_app(db_manager: DatabaseManager, server_manager: ServerManager, secure_mode: bool = False, token: str = None, allowed_origins: list = None, port: int = 8099) -> FastAPI:
    """
    Create FastAPI application without starting any MCP servers.

    Args:
        db_manager: Database manager instance
        server_manager: ServerManager instance
        secure_mode: Enable bearer token authentication
        token: Bearer token for secure mode
        allowed_origins: List of allowed CORS origins (default: localhost only)

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="FluidMCP Gateway",
        description="Unified gateway for MCP servers with dynamic management",
        version="2.0.0"
    )

    # CORS setup - secure by default
    if allowed_origins is None:
        # Default to localhost only for security
        allowed_origins = [
            "http://localhost:*",
            "http://127.0.0.1:*",
            "http://localhost:3000",
            "http://localhost:8080",
        ]
    
    if "*" in allowed_origins:
        logger.warning("⚠️  WARNING: CORS wildcard enabled - any website can access this API!")
        logger.warning("⚠️  This is a SECURITY RISK and should only be used for development!")
    
    logger.info(f"CORS allowed origins: {allowed_origins}")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add request size limiting middleware for security (prevent DoS via large payloads)
    # Max 10MB request body size (configurable via MAX_REQUEST_SIZE_MB env var)
    # Uses Starlette's exception to ensure proper handling and prevent bypassing
    default_request_size_mb = 10
    max_request_size_env = os.getenv("MAX_REQUEST_SIZE_MB")
    if max_request_size_env is None:
        max_request_size_mb = default_request_size_mb
    else:
        try:
            max_request_size_mb = int(max_request_size_env)
        except ValueError:
            logger.warning(
                f"Invalid MAX_REQUEST_SIZE_MB value '{max_request_size_env}', "
                f"falling back to default {default_request_size_mb}MB."
            )
            max_request_size_mb = default_request_size_mb
    max_request_size = max_request_size_mb * 1024 * 1024  # bytes

    @app.middleware("http")
    async def limit_request_size(request, call_next):
        """
        Middleware to limit request body size and prevent memory exhaustion attacks.

        Checks Content-Length header when present to provide early rejection.

        IMPORTANT: This middleware only enforces limits when Content-Length is present.
        Chunked transfer encoding (no Content-Length header) can bypass this check.
        For production deployments, ALWAYS configure server-level limits:
        - Uvicorn: Use --limit-max-requests parameter (e.g., --limit-max-requests 10485760)
        - Nginx: Set client_max_body_size directive in nginx.conf
        - Apache: Set LimitRequestBody directive in httpd.conf
        - Cloudflare/CDN: Configure maximum upload size at edge

        Without server-level limits, attackers can stream large bodies via chunked
        encoding to cause memory exhaustion.

        Raises HTTPException 413 to ensure FastAPI's exception handling is triggered,
        preventing bypasses through direct body reading.
        """
        from starlette.exceptions import HTTPException as StarletteHTTPException

        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    content_length_value = int(content_length)
                except (TypeError, ValueError):
                    raise StarletteHTTPException(
                        status_code=400,
                        detail="Invalid Content-Length header"
                    )
                if content_length_value < 0:
                    raise StarletteHTTPException(
                        status_code=400,
                        detail="Invalid Content-Length header"
                    )
                if content_length_value > max_request_size:
                    raise StarletteHTTPException(
                        status_code=413,
                        detail=f"Request body too large (max {max_request_size // (1024*1024)}MB)"
                    )
        return await call_next(request)

    logger.info(f"Request size limit (Content-Length check): {max_request_size // (1024*1024)}MB")
    logger.warning(
        "SECURITY: Content-Length-based limit does not protect against chunked transfer encoding. "
        "Configure server-level limits (Uvicorn --limit-max-requests, Nginx client_max_body_size, etc.) "
        "for production deployments."
    )

    # Store managers in app state for dependency injection
    app.state.db_manager = db_manager
    app.state.server_manager = server_manager

    # Check MongoDB configuration and warn if not available
    if not hasattr(db_manager, 'client') or db_manager.client is None:
        logger.warning("=" * 80)
        logger.warning("⚠️  WARNING: MongoDB NOT CONFIGURED - Running in EPHEMERAL MODE")
        logger.warning("=" * 80)
        logger.warning("⚠️  All model registrations will be LOST on server restart!")
        logger.warning("⚠️  For production deployments, set MONGODB_URI environment variable")
        logger.warning("⚠️  In-memory rate limiting does NOT work across multiple instances")
        logger.warning("=" * 80)

    # Set up secure mode if enabled
    if secure_mode and token:
        os.environ["FMCP_BEARER_TOKEN"] = token
        os.environ["FMCP_SECURE_MODE"] = "true"
        logger.info("Secure mode enabled with bearer token")

    # Include Management API
    app.include_router(mgmt_router, prefix="/api", tags=["management"])
    logger.info("Management API mounted at /api")

    # Include Dynamic MCP Router
    mcp_router = create_dynamic_router(server_manager)
    app.include_router(mcp_router, tags=["mcp"])
    logger.info("Dynamic MCP router mounted")

    # Serve frontend from backend (single-port deployment)
    setup_frontend_routes(app, host="0.0.0.0", port=port)

    # Add a health check endpoint with actual connection verification
    # NOTE: /health (and /metrics below) are intentionally NOT instrumented with
    # RequestTimer to avoid high-cardinality metric pollution from frequent load
    # balancer health checks and Prometheus scrapes. Only business logic endpoints
    # (MCP requests) are instrumented and counted in fluidmcp_requests_total.
    @app.get("/health")
    async def health_check():
        """
        Health check endpoint with comprehensive status information.

        Returns:
            - status: Overall health status
            - database: MongoDB connection status
            - models: Registered model statistics
            - version: FluidMCP version
        """
        from datetime import datetime
        from .services.replicate_client import _replicate_clients
        from .services.llm_provider_registry import _llm_models_config

        # Check database
        db_status = "disconnected"
        db_error = None
        db_type = type(db_manager).__name__

        if hasattr(db_manager, 'client') and db_manager.client:
            try:
                # Actually ping the database to verify connection
                await db_manager.client.admin.command('ping')
                db_status = "connected"
            except Exception as e:
                db_status = "error"
                db_error = str(e)

        # Count registered models
        replicate_count = len(_replicate_clients)
        total_models = len(_llm_models_config)

        # Determine overall health status based on components
        overall_status = "healthy"
        if db_status == "error":
            overall_status = "degraded"  # Database error but service still operational
        elif db_status == "disconnected":
            if total_models == 0:
                overall_status = "starting"  # No database, no models (likely still starting up)
            else:
                overall_status = "degraded"  # No database but models loaded (lost persistence)

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "database": {
                "status": db_status,
                "type": db_type,
                "error": db_error,
                "persistence_enabled": db_status == "connected"
            },
            "models": {
                "total": total_models,
                "by_type": {
                    "replicate": replicate_count
                }
            },
            "version": getattr(app, "version", "2.0.0")
        }

    @app.get("/metrics")
    async def metrics():
        """
        Prometheus-compatible metrics endpoint.

        Exposes metrics in Prometheus exposition format:
        - Request counters and histograms
        - Server status and uptime (dynamically calculated)
        - GPU memory utilization
        - Tool execution metrics
        - Streaming request metrics
        """
        from fastapi.responses import PlainTextResponse
        from .services.metrics import MetricsCollector

        # Update uptime for all running servers before rendering metrics
        # Note: MetricsCollector is lightweight (just holds server_id + registry ref).
        # Creating N instances per scrape is acceptable given low overhead.
        # Alternative optimization: Add batch method like registry.set_uptimes(Dict[str, float])
        for server_id in server_manager.processes.keys():
            uptime = server_manager.get_uptime(server_id)
            if uptime is not None:
                collector = MetricsCollector(server_id)
                collector.set_uptime(uptime)

        registry = get_registry()
        # Prometheus text exposition format v0.0.4 (not OpenMetrics)
        return PlainTextResponse(content=registry.render_all(), media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "FluidMCP Gateway",
            "version": "2.0.0",
            "docs": "/docs",
            "health": "/health",
            "metrics": "/metrics",
            "api": {
                "management": "/api/servers",
                "mcp": "/{server_name}/mcp"
            }
        }

    # Register cleanup handler for HTTP client and Redis connections
    @app.on_event("shutdown")
    async def shutdown_event():
        """Clean up resources on application shutdown."""
        from .api.management import cleanup_http_client
        await cleanup_http_client()
        logger.info("HTTP client cleaned up")

        # CRITICAL FIX #2: Close Redis connection pool gracefully
        try:
            from .utils.rate_limiter import close_redis_client
            await close_redis_client()
        except Exception as e:
            logger.warning(f"Error during Redis cleanup: {e}")

    logger.info("FastAPI application created (no MCP servers started)")
    return app


async def connect_with_retry(
    db_manager: DatabaseManager,
    max_retries: int = 3,
    require_persistence: bool = False
) -> bool:
    """
    Connect to MongoDB with exponential backoff retry.

    Args:
        db_manager: Database manager instance
        max_retries: Maximum number of retry attempts
        require_persistence: If True, fail on connection error

    Returns:
        True if connected, False otherwise
    """
    for attempt in range(1, max_retries + 1):
        logger.info(f"MongoDB connection attempt {attempt}/{max_retries}...")

        db_connected = await db_manager.init_db()

        if db_connected:
            logger.info("✓ Successfully connected to MongoDB")
            return True

        if attempt < max_retries:
            wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
            logger.warning(f"Connection failed. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
        else:
            logger.error(f"Failed to connect after {max_retries} attempts")

    # All retries exhausted
    if require_persistence:
        logger.error("❌ FATAL: --require-persistence enabled but MongoDB unavailable")
        logger.error("❌ Server cannot start without persistence layer")
        raise RuntimeError("MongoDB connection required but unavailable")
    else:
        logger.warning("⚠️  Failed to connect to MongoDB.")
        logger.warning("⚠️  Backend will start WITHOUT persistence.")
        logger.warning("⚠️  Server state will NOT be saved across restarts.")
        logger.warning("⚠️  Use --require-persistence to fail instead of degrading.")
        return False


async def load_models_from_mongodb(db_manager: PersistenceBackend) -> int:
    """
    Load and initialize LLM models from MongoDB.

    Args:
        db_manager: Database manager instance

    Returns:
        Number of models successfully loaded
    """
    from .services.replicate_client import ReplicateClient, _replicate_clients
    from .services.llm_provider_registry import _llm_models_config, _registry_lock

    try:
        # Check if backend supports model persistence (list_llm_models method)
        if not hasattr(db_manager, 'list_llm_models'):
            logger.info("Backend does not support model persistence, skipping MongoDB model loading")
            return 0

        logger.info("Loading LLM models from MongoDB...")
        models = await db_manager.list_llm_models()

        if not models:
            logger.info("No LLM models found in MongoDB")
            return 0

        logger.info(f"Found {len(models)} model(s) in MongoDB")
        loaded_count = 0

        for model_doc in models:
            model_id = model_doc.get("model_id")
            model_type = model_doc.get("type")

            if not model_id or not model_type:
                logger.warning(f"Skipping invalid model doc: {model_doc}")
                continue

            try:
                # Only initialize Replicate models for now
                if model_type == "replicate":
                    # Early check for existing model (optimization to skip expensive operations)
                    # Note: This is NOT authoritative - we check again after health check
                    already_exists = False
                    with _registry_lock:
                        if model_id in _replicate_clients or model_id in _llm_models_config:
                            already_exists = True

                    if already_exists:
                        logger.info(f"⚠ Model '{model_id}' already registered, skipping MongoDB load")
                        loaded_count += 1  # Count as loaded (already exists)
                        continue

                    # COPILOT FIX: Preserve logical configuration fields like "version" used for
                    # version tracking and rollback; only strip MongoDB-specific metadata.
                    mongo_internal_fields = ["created_at", "updated_at", "_id"]
                    model_config = {
                        k: v
                        for k, v in model_doc.items()
                        if k not in mongo_internal_fields and k != "model_id"
                    }

                    # Initialize Replicate client
                    client = ReplicateClient(model_id, model_config)

                    # Health check (outside lock)
                    health_ok = await client.health_check()

                    if health_ok:
                        # Register in global registries (both protected by same lock)
                        client_to_close = None
                        with _registry_lock:
                            # Double-check after acquiring lock (TOCTOU protection)
                            if model_id not in _replicate_clients and model_id not in _llm_models_config:
                                _replicate_clients[model_id] = client
                                _llm_models_config[model_id] = model_config
                                logger.info(f"✓ Loaded model: {model_id} (type: {model_type})")
                                loaded_count += 1
                            else:
                                # Race condition: Another thread registered it first
                                client_to_close = client
                                logger.info(f"⚠ Model '{model_id}' registered by another thread, skipping")
                                loaded_count += 1

                        # Close outside lock if needed
                        if client_to_close:
                            await client_to_close.close()
                    else:
                        await client.close()
                        logger.warning(f"✗ Health check failed for model: {model_id}")

                else:
                    logger.warning(f"Unsupported model type '{model_type}' for model '{model_id}' (skipping)")

            except Exception as e:
                logger.error(f"Failed to load model '{model_id}': {e}")
                continue

        logger.info(f"Successfully loaded {loaded_count}/{len(models)} model(s) from MongoDB")
        return loaded_count

    except Exception as e:
        logger.error(f"Error loading models from MongoDB: {e}")
        return 0


async def main(args):
    """
    Main async entry point for standalone server.

    Args:
        args: Parsed command line arguments
    """
    logger.info("Starting FluidMCP backend server (standalone mode)")

    # Parse CORS origins from CLI or environment
    allowed_origins = None
    if hasattr(args, 'allow_all_origins') and args.allow_all_origins:
        allowed_origins = ["*"]
    elif hasattr(args, 'allowed_origins') and args.allowed_origins:
        origins_str = args.allowed_origins or os.getenv("FMCP_ALLOWED_ORIGINS", "")
        if origins_str:
            allowed_origins = [origin.strip() for origin in origins_str.split(",")]

    # 1. Choose persistence backend
    persistence_mode = getattr(args, 'persistence_mode', 'mongodb')
    in_memory = getattr(args, 'in_memory', False)

    if in_memory or persistence_mode == 'memory':
        logger.info("Using in-memory persistence backend")
        persistence: PersistenceBackend = InMemoryBackend()
        db_connected = await persistence.connect()
    else:  # mongodb (default)
        logger.info(f"Using MongoDB persistence backend at {args.mongodb_uri}")
        persistence: PersistenceBackend = DatabaseManager(
            mongodb_uri=args.mongodb_uri,
            database_name=args.database
        )
        # Connect with retry and configurable requirement
        require_persistence = getattr(args, 'require_persistence', False)
        db_connected = await connect_with_retry(
            persistence,
            max_retries=3,
            require_persistence=require_persistence
        )

    # 2. Create ServerManager
    logger.info("Creating ServerManager...")
    server_manager = ServerManager(persistence)

    # 3. Create FastAPI app (without MCP servers)
    app = await create_app(
        db_manager=persistence,
        server_manager=server_manager,
        secure_mode=args.secure,
        token=args.token,
        allowed_origins=allowed_origins,
        port=args.port
    )

    # 4. Load models from MongoDB (if persistence is enabled)
    if db_connected:
        loaded_models = await load_models_from_mongodb(persistence)
        if loaded_models > 0:
            logger.info(f"✓ Loaded {loaded_models} model(s) from MongoDB on startup")
    else:
        logger.info("Skipping MongoDB model loading (not connected)")

    # 5. Setup graceful shutdown with comprehensive signal handlers
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        """Handle shutdown signals (SIGINT, SIGTERM, SIGHUP)."""
        signal_name = signal.Signals(sig).name
        logger.info(f"Shutdown signal {signal_name} received. Stopping server...")
        shutdown_event.set()

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination request

    # Register SIGHUP on Unix systems only
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, signal_handler)  # Hangup (terminal closed)

    # 6. Run server
    # Get max request size from env var (same as middleware, for consistency)
    max_request_size_mb = 10
    max_request_size_env = os.getenv("MAX_REQUEST_SIZE_MB")
    if max_request_size_env:
        try:
            max_request_size_mb = int(max_request_size_env)
        except ValueError:
            pass  # Already logged in middleware

    config = Config(
        app,
        host=args.host,
        port=args.port,
        loop="asyncio",
        log_level="info"
        # Note: Uvicorn doesn't provide a direct body size limit parameter
        # For production, configure limits at reverse proxy level (Nginx, Cloudflare, etc.)
    )
    server = Server(config)

    logger.info(f"Backend server starting on http://{args.host}:{args.port}")
    logger.info(f"Swagger UI available at: http://{args.host}:{args.port}/docs")
    logger.info(f"Health check at: http://{args.host}:{args.port}/health")

    # Start server in background task
    server_task = asyncio.create_task(server.serve())

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Graceful cleanup
    logger.info("Initiating graceful shutdown...")

    try:
        # Stop all MCP servers with timeout
        logger.info("Stopping all MCP servers...")
        shutdown_task = asyncio.create_task(server_manager.shutdown_all())
        await asyncio.wait_for(shutdown_task, timeout=10.0)
        logger.info("All MCP servers stopped")
    except asyncio.TimeoutError:
        logger.warning("MCP server shutdown timed out, forcing cleanup...")
        server_manager._cleanup_on_exit()
    except Exception as e:
        logger.error(f"Error during MCP server shutdown: {e}")
        server_manager._cleanup_on_exit()

    try:
        # Close database connection
        logger.info("Closing database connection...")
        await persistence.disconnect()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error(f"Error closing database connection: {e}")

    logger.info("Backend server stopped successfully")


def run():
    """Entry point for console script."""
    parser = argparse.ArgumentParser(
        description="FluidMCP Standalone Backend Server"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8099,
        help="Port to listen on (default: 8099)"
    )
    parser.add_argument(
        "--mongodb-uri",
        default=os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        help="MongoDB connection URI (default: env MONGODB_URI or mongodb://localhost:27017)"
    )
    parser.add_argument(
        "--database",
        default="fluidmcp",
        help="MongoDB database name (default: fluidmcp)"
    )
    parser.add_argument(
        "--secure",
        action="store_true",
        help="Enable secure mode with bearer token authentication"
    )
    parser.add_argument(
        "--token",
        type=str,
        help="Bearer token for secure mode (will be generated if not provided)"
    )
    parser.add_argument(
        "--allowed-origins",
        type=str,
        help="Comma-separated list of allowed CORS origins (default: localhost only)"
    )
    parser.add_argument(
        "--allow-all-origins",
        action="store_true",
        help="Allow all CORS origins (SECURITY RISK - development only)"
    )
    parser.add_argument(
        "--require-persistence",
        action="store_true",
        help="Fail if MongoDB connection fails (default: continue without persistence)"
    )

    args = parser.parse_args()

    # Handle token for secure mode: CLI arg > env var > generate new
    if args.secure and not args.token:
        # Try environment variable first (more secure than CLI arg)
        args.token = os.getenv("FMCP_BEARER_TOKEN")

        # Generate new token if still not provided
        if not args.token:
            args.token = secrets.token_urlsafe(32)
            logger.info("Generated new bearer token (see console output for full token)")

            # Save to secure file
            token_file = save_token_to_file(args.token)

            # Print full token to console (NOT in logs)
            print("\n" + "="*70)
            print("🔐 BEARER TOKEN GENERATED (save this securely!):")
            print("="*70)
            print(f"\n{args.token}\n")
            print("="*70)
            print(f"Token saved to: {token_file}")
            print("To retrieve later: fluidmcp token show")
            print("="*70 + "\n")

            # Only log masked version (show first 8 chars for better identification)
            logger.info(f"Bearer token generated (starts with: {args.token[:8]}{'*' * (len(args.token) - 8)})")

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    run()
