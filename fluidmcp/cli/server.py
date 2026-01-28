"""
Standalone FluidMCP backend server.

This module provides a persistent API server that can run independently
and manage MCP servers dynamically via HTTP API.
"""
import argparse
import asyncio
import os
import secrets
import signal
from pathlib import Path
from loguru import logger
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import Config, Server

from .repositories import DatabaseManager, InMemoryBackend, PersistenceBackend
from .services.server_manager import ServerManager
from .services.frontend_utils import setup_frontend_routes
from .api.management import router as mgmt_router
from .services.package_launcher import create_dynamic_router
from .services.metrics import get_registry
from .auth import verify_token


def mask_mongodb_uri(uri: str) -> str:
    """
    Mask sensitive information in MongoDB URI for logging.

    Examples:
        mongodb://user:pass@host:27017/db -> mongodb://***:***@host:27017/db
        mongodb+srv://user:pass@cluster.net -> mongodb+srv://***:***@cluster.net

    Args:
        uri: MongoDB connection URI

    Returns:
        Masked URI safe for logging
    """
    if not uri or '@' not in uri:
        return uri

    try:
        # Split by @ to separate credentials from host
        parts = uri.split('@')
        if len(parts) != 2:
            return uri

        prefix_with_creds = parts[0]
        host_and_path = parts[1]

        # Split prefix to get protocol and credentials
        if '://' in prefix_with_creds:
            protocol, creds = prefix_with_creds.split('://', 1)
            # Mask credentials completely
            masked = f"{protocol}://***:***@{host_and_path}"
            return masked

        return uri
    except Exception:
        # If anything goes wrong, return a safe default
        return "mongodb://***:***@[masked]"


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

async def create_app(db_manager: DatabaseManager, server_manager: ServerManager, secure_mode: bool = False, token: str = None, allowed_origins: list = None, host: str = "0.0.0.0", port: int = 8099, auth0_mode: bool = False) -> FastAPI:
    """
    Create FastAPI application without starting any MCP servers.

    Args:
        db_manager: Database manager instance
        server_manager: ServerManager instance
        secure_mode: Enable bearer token authentication
        token: Bearer token for secure mode
        allowed_origins: List of allowed CORS origins (default: localhost only)
        auth0_mode: Enable OAuth0 (Auth0) authentication
        host: Host address for URL logging (default: 0.0.0.0)
        port: Port number for URL logging (default: 8099)

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
    
    # Auto-expand CORS for OAuth environments
    if auth0_mode:
        from .auth.url_utils import get_cors_origins
        auto_origins = get_cors_origins(8099)
        allowed_origins = list(set((allowed_origins or []) + auto_origins))
        logger.info(f"OAuth mode: Auto-detected CORS origins: {auto_origins}")

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

    # Add security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        """Add security headers to all responses"""
        response = await call_next(request)

        # Content Security Policy (CSP) - prevent XSS
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "  # Allow inline scripts for docs
            "style-src 'self' 'unsafe-inline'; "   # Allow inline styles
            "img-src 'self' data: https:; "
            "font-src 'self' data:;"
        )

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response

    logger.info("Security headers middleware enabled")

    # Store managers in app state for dependency injection
    app.state.db_manager = db_manager
    app.state.server_manager = server_manager

    # Set up secure mode if enabled
    if secure_mode and token:
        os.environ["FMCP_BEARER_TOKEN"] = token
        os.environ["FMCP_SECURE_MODE"] = "true"
        logger.info("Secure mode enabled with bearer token")

    # Serve frontend from backend (single-port deployment)
    setup_frontend_routes(app, host=host, port=port)

    # Include Management API
    app.include_router(mgmt_router, prefix="/api", tags=["management"])
    logger.info("Management API mounted at /api")

    # Include Dynamic MCP Router
    mcp_router = create_dynamic_router(server_manager)
    app.include_router(mcp_router, tags=["mcp"])
    logger.info("Dynamic MCP router mounted")

    # Mount OAuth routes if enabled
    if auth0_mode:
        from .auth import auth_router, init_auth_routes, Auth0Config
        auth_config = Auth0Config.from_env(port=8099)
        init_auth_routes(auth_config)
        app.include_router(auth_router, tags=["Authentication"])
        logger.info("✓ OAuth routes mounted at /auth")

    # Add a health check endpoint with actual connection verification
    # NOTE: /health (and /metrics below) are intentionally NOT instrumented with
    # RequestTimer to avoid high-cardinality metric pollution from frequent load
    # balancer health checks and Prometheus scrapes. Only business logic endpoints
    # (MCP requests) are instrumented and counted in fluidmcp_requests_total.
    @app.get("/health")
    async def health_check():
        """Health check endpoint with database connection status."""
        db_status = "disconnected"
        db_error = None

        if hasattr(db_manager, 'client') and db_manager.client:
            try:
                # Actually ping the database to verify connection
                await db_manager.client.admin.command('ping')
                db_status = "connected"
            except Exception as e:
                db_status = "error"
                db_error = str(e)
        elif hasattr(db_manager, '__class__') and db_manager.__class__.__name__ == 'InMemoryBackend':
            db_status = "in-memory"

        return {
            "status": "healthy",
            "database": db_status,
            "database_error": db_error,
            "persistence_enabled": db_status == "connected"
        }

    @app.get("/metrics", dependencies=[Depends(verify_token)])
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
        from fastapi.responses import PlainTextResponse
        from .services.metrics import MetricsCollector

        # Update uptime for all running servers before rendering metrics
        # Note: MetricsCollector is lightweight (just holds server_id + registry ref).
        # Creating N instances per scrape is acceptable given low overhead.
        # Alternative optimization: Add batch method like registry.set_uptimes(Dict[str, float])

        # Get snapshot of server IDs under lock to avoid race condition
        with server_manager._registry_lock:
            server_ids = list(server_manager.processes.keys())

        # Update metrics outside lock (safe iteration)
        for server_id in server_ids:
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
    else:
        # Check environment variable even if no CLI args
        origins_str = os.getenv("FMCP_ALLOWED_ORIGINS", "")
        if origins_str:
            allowed_origins = [origin.strip() for origin in origins_str.split(",")]

    # Auto-detect GitHub Codespaces environment and add Codespaces URLs to CORS
    codespace_name = os.getenv("CODESPACE_NAME")
    if codespace_name:
        codespaces_domain = f"https://*.{codespace_name}.preview.app.github.dev"
        logger.info(f"GitHub Codespaces detected: {codespace_name}")
        logger.info(f"Adding Codespaces domain to CORS: {codespaces_domain}")

        if allowed_origins is None:
            allowed_origins = [
                "http://localhost:*",
                "http://127.0.0.1:*",
                f"https://*.{codespace_name}.preview.app.github.dev",
                f"https://*-*.app.github.dev"
            ]
        elif "*" not in allowed_origins:
            allowed_origins.extend([
                f"https://*.{codespace_name}.preview.app.github.dev",
                f"https://*-*.app.github.dev"
            ])

    # 1. Choose persistence backend
    persistence_mode = getattr(args, 'persistence_mode', 'mongodb')
    in_memory = getattr(args, 'in_memory', False)

    if in_memory or persistence_mode == 'memory':
        logger.info("Using in-memory persistence backend")
        persistence: PersistenceBackend = InMemoryBackend()
        db_connected = await persistence.connect()
    else:  # mongodb (default)
        logger.info(f"Using MongoDB persistence backend at {mask_mongodb_uri(args.mongodb_uri)}")
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
    auth0_mode = getattr(args, 'auth0', False)
    app = await create_app(
        db_manager=persistence,
        server_manager=server_manager,
        secure_mode=args.secure,
        token=args.token,
        allowed_origins=allowed_origins,
        auth0_mode=auth0_mode
        host=args.host,
        port=args.port
    )

    # 3. Setup graceful shutdown with comprehensive signal handlers
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

    # 4. Run server
    config = Config(
        app,
        host=args.host,
        port=args.port,
        loop="asyncio",
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
        server_header=False,
        date_header=False
    )
    server = Server(config)

    logger.info(f"Backend server starting on http://{args.host}:{args.port}")
    logger.info(f"Frontend UI available at: http://{args.host}:{args.port}/ui")
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
        "--auth0",
        action="store_true",
        help="Enable OAuth0 (Auth0) authentication (mutually exclusive with --secure)"
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

    # Validate authentication modes (mutually exclusive)
    if args.secure and args.auth0:
        logger.error("❌ Cannot use --secure and --auth0 together. Choose one authentication method.")
        logger.info("   --secure: Bearer token authentication (simple, for CI/CD)")
        logger.info("   --auth0:  OAuth0 authentication (multi-user, SSO)")
        return

    # Validate Auth0 configuration if enabled
    if args.auth0:
        required_vars = ["FMCP_AUTH0_DOMAIN", "FMCP_AUTH0_CLIENT_ID", "FMCP_AUTH0_CLIENT_SECRET"]
        missing = [v for v in required_vars if not os.getenv(v)]
        if missing:
            logger.error(f"❌ Auth0 mode requires environment variables: {', '.join(missing)}")
            logger.info("   Set these environment variables or create auth0-config.json")
            logger.info("   See .env.example for configuration template")
            return
        os.environ["FMCP_AUTH0_MODE"] = "true"
        logger.info(f"✓ OAuth0 enabled with domain: {os.getenv('FMCP_AUTH0_DOMAIN')}")

    # Generate and save token if secure mode enabled but no token provided
    if args.secure and not args.token:
        args.token = secrets.token_urlsafe(32)
        logger.info(f"Generated bearer token: {args.token}")

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

        # Only log masked version
        logger.info(f"Bearer token generated (starts with: {args.token[:4]}****)")

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    run()
