"""
Shared test fixtures for FluidMCP integration tests.

This module contains common fixtures used across multiple test files to reduce
code duplication and ensure consistency.
"""

import asyncio
import os
import time
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from fluidmcp.cli.server import create_app
from fluidmcp.cli.repositories.database import DatabaseManager
from fluidmcp.cli.services.server_manager import ServerManager


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end integration test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring external services"
    )


# ============================================================================
# MongoDB Fixtures
# ============================================================================

@pytest.fixture
def mongodb_uri():
    """MongoDB URI for testing."""
    return os.getenv("FMCP_TEST_MONGODB_URI", "mongodb://localhost:27017")


@pytest.fixture
def test_db_name():
    """Generate unique test database name."""
    return f"fluidmcp_test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def mongodb_test_connection(mongodb_uri, test_db_name):
    """
    MongoDB connection for integration tests.
    Uses environment variable FMCP_TEST_MONGODB_URI or defaults to localhost.
    """
    # Create database manager
    manager = DatabaseManager(mongodb_uri, test_db_name)
    connected = await manager.connect()

    # Fail fast with clear error message if MongoDB is unavailable
    if not connected:
        pytest.skip(
            f"MongoDB connection failed at {mongodb_uri}. "
            "Please ensure MongoDB is running:\n"
            "  - Docker: docker run -d -p 27017:27017 mongo:latest\n"
            "  - Or set FMCP_TEST_MONGODB_URI environment variable"
        )

    yield manager

    # Cleanup: drop test database
    try:
        await manager.client.drop_database(test_db_name)
    except Exception:
        pass  # Best effort cleanup
    await manager.close()


# ============================================================================
# FastAPI App Fixtures
# ============================================================================

@pytest.fixture
async def serve_test_app(mongodb_test_connection):
    """
    Creates FastAPI app with MongoDB backend for integration testing.
    Uses insecure mode (no authentication) to simplify testing.
    Returns tuple: (app, database_manager, server_manager)
    """
    # Create managers
    db_manager = mongodb_test_connection
    server_manager = ServerManager(db_manager)

    # Create app using server.create_app() in insecure mode
    app = await create_app(
        db_manager=db_manager,
        server_manager=server_manager,
        secure_mode=False,  # Insecure mode - no authentication
        token=None,
        allowed_origins=["http://localhost:3000"]
    )

    yield app, db_manager, server_manager

    # Cleanup: stop all servers
    await server_manager.shutdown_all()


@pytest.fixture
async def api_client(serve_test_app):
    """
    httpx.AsyncClient for making API requests (insecure mode, no auth).
    """
    app, db_manager, server_manager = serve_test_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client



def _run_launch_startup(config, spawn_result=None):
    """Build the app via run_servers and run its MCP-launch startup hook.

    Servers are spawned in an app startup handler (not inline in run_servers), so
    capture the app instead of serving it and invoke that handler directly.
    """
    from fluidmcp.cli.services.run_servers import run_servers

    captured = {}
    spawn = AsyncMock(return_value=spawn_result)
    with patch('fluidmcp.cli.services.run_servers._start_server',
               side_effect=lambda app, *args, **kwargs: captured.update(app=app)), \
            patch.object(ServerManager, '_spawn_mcp_process', new=spawn):
        run_servers(config, start_server=True)
        app = captured['app']
        startup = next(h for h in app.router.on_startup if h.__name__ == '_launch_mcp_servers')
        # Private loop: asyncio.run() would clear the main thread's loop, breaking later
        # tests that call asyncio.get_event_loop()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(startup())
        finally:
            loop.close()
    return app, spawn


@pytest.fixture
def run_launch_startup():
    return _run_launch_startup
