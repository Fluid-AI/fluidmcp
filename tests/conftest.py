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


# ============================================================================
# Test Utility Functions
# ============================================================================

async def wait_for_server_status(client, server_id: str, expected_status: str, timeout: float = 10.0) -> bool:
    """
    Poll server status until it reaches expected state or timeout.

    This utility replaces hardcoded asyncio.sleep() calls with intelligent polling,
    making tests more reliable and faster.

    Args:
        client: httpx.AsyncClient instance
        server_id: The server ID to check
        expected_status: The status to wait for (e.g., "running", "stopped")
        timeout: Maximum time to wait in seconds

    Returns:
        True if server reached expected status, False if timeout

    Example:
        success = await wait_for_server_status(client, "test-server", "running", timeout=30)
        assert success, "Server failed to start within 30 seconds"
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = await client.get(f"/api/servers/{server_id}/status")
            if response.status_code == 200:
                data = response.json()
                # Handle both 'state' and 'status' field names (API inconsistency)
                status = data.get("state") or data.get("status")
                if status == expected_status:
                    return True
        except Exception:
            pass  # Continue polling on transient errors
        await asyncio.sleep(0.5)  # Poll every 500ms
    return False


async def wait_for_condition(condition_func, timeout: float = 10.0, poll_interval: float = 0.5) -> bool:
    """
    Generic polling utility for waiting on async conditions.

    Args:
        condition_func: Async function that returns True when condition is met
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds

    Returns:
        True if condition met, False if timeout

    Example:
        async def check_health():
            response = await client.get("/health")
            return response.status_code == 200

        success = await wait_for_condition(check_health, timeout=30)
        assert success, "Health check never succeeded"
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            if await condition_func():
                return True
        except Exception:
            pass  # Continue polling on errors
        await asyncio.sleep(poll_interval)
    return False
