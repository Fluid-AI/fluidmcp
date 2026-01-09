"""
Standalone FluidMCP backend server.

This module provides a persistent API server that can run independently
and manage MCP servers dynamically via HTTP API.
"""
import argparse
import asyncio
import os
import signal
from loguru import logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import Config, Server

from .services.database import DatabaseManager
from .services.server_manager import ServerManager
from .api.management import router as mgmt_router
from .services.package_launcher import create_dynamic_router


async def create_app(
    db_manager: DatabaseManager,
    server_manager: ServerManager,
    secure_mode: bool = False,
    token: str = None
) -> FastAPI:
    """
    Create FastAPI application without starting any MCP servers.

    Args:
        db_manager: Database manager instance
        server_manager: ServerManager instance
        secure_mode: Enable bearer token authentication
        token: Bearer token for secure mode

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="FluidMCP Gateway",
        description="Unified gateway for MCP servers with dynamic management",
        version="2.0.0"
    )

    # CORS setup to allow React dev server access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for development
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

    # Add a health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        running_servers = len([
            name for name, proc in server_manager.processes.items()
            if proc.poll() is None
        ])

        return {
            "status": "healthy",
            "database": "connected" if db_manager.client else "disconnected",
            "servers_running": running_servers
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


async def main(args):
    """
    Main async entry point for standalone server.

    Args:
        args: Parsed command line arguments
    """
    logger.info("Starting FluidMCP backend server (standalone mode)")

    # 1. Initialize MongoDB connection
    logger.info(f"Connecting to MongoDB at {args.mongodb_uri}")
    db_manager = DatabaseManager(
        mongodb_uri=args.mongodb_uri,
        database_name=args.database
    )

    db_connected = await db_manager.init_db()
    if not db_connected:
        logger.warning("⚠️  Failed to connect to MongoDB.")
        logger.warning("⚠️  Backend will start WITHOUT persistence.")
        logger.warning("⚠️  Server state will not be saved across restarts.")
        logger.warning("⚠️  To enable persistence, check your MongoDB connection.")
        # Continue anyway - backend can still start

    # 2. Create ServerManager
    logger.info("Creating ServerManager...")
    server_manager = ServerManager(db_manager)

    # 3. Create FastAPI app (without MCP servers)
    app = await create_app(
        db_manager=db_manager,
        server_manager=server_manager,
        secure_mode=args.secure,
        token=args.token
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

    args = parser.parse_args()

    # Generate token if secure mode enabled but no token provided
    if args.secure and not args.token:
        import secrets
        args.token = secrets.token_urlsafe(32)
        logger.info(f"Generated bearer token: {args.token}")

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    run()
