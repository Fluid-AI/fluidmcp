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


async def create_app(db_manager: DatabaseManager, server_manager: ServerManager, secure_mode: bool = False, token: str = None, allowed_origins: list = None) -> FastAPI:
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

    # Store managers in app state for dependency injection
    app.state.db_manager = db_manager
    app.state.server_manager = server_manager

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

    # Add a health check endpoint with actual connection verification
    @app.get("/health")
    async def health_check():
        """Health check endpoint with database connection status."""
        db_status = "disconnected"
        db_error = None

        if db_manager.client:
            try:
                # Actually ping the database to verify connection
                await db_manager.client.admin.command('ping')
                db_status = "connected"
            except Exception as e:
                db_status = "error"
                db_error = str(e)

        return {
            "status": "healthy",
            "database": db_status,
            "database_error": db_error,
            "persistence_enabled": db_status == "connected"
        }

    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "FluidMCP Gateway",
            "version": "2.0.0",
            "docs": "/docs",
            "health": "/health",
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
        allowed_origins=allowed_origins
    )

    # 3. Setup graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info("Shutdown signal received. Stopping server...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 4. Run server
    config = Config(
        app,
        host=args.host,
        port=args.port,
        loop="asyncio",
        log_level="info"
    )
    server = Server(config)

    logger.info(f"Backend server starting on http://{args.host}:{args.port}")
    logger.info(f"Swagger UI available at: http://{args.host}:{args.port}/docs")
    logger.info(f"Health check at: http://{args.host}:{args.port}/health")

    # Start server in background task
    server_task = asyncio.create_task(server.serve())

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Cleanup
    logger.info("Stopping all MCP servers...")
    await server_manager.stop_all_servers()

    logger.info("Closing database connection...")
    await db_manager.close()

    logger.info("Backend server stopped")


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
