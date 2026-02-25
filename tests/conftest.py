"""
Shared test fixtures for FluidMCP integration tests.

This module contains common fixtures used across multiple test files to reduce
code duplication and ensure consistency.
"""

import asyncio
import os
import time
import uuid

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
