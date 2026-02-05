"""
Integration tests for fmcp serve API endpoints (fast tests).

These tests verify API behavior WITHOUT starting actual MCP servers:
- Health, metrics, and Swagger endpoints
- Server configuration validation
- MongoDB connection handling

For slow end-to-end tests that start actual MCP servers, see test_serve_e2e.py

Prerequisites:
    MongoDB instance is required for these tests.

    Option 1 - Local MongoDB (Docker):
        docker run -d -p 27017:27017 --name mongodb-test mongo:latest

    Option 2 - Local MongoDB (Native):
        # macOS: brew install mongodb-community && brew services start mongodb-community
        # Ubuntu: sudo apt-get install mongodb && sudo systemctl start mongodb

    Option 3 - MongoDB Atlas (Cloud):
        export FMCP_TEST_MONGODB_URI="mongodb+srv://username:password@cluster.mongodb.net/"

Running tests:
    # Run fast API tests (completes in ~5 seconds)
    pytest tests/test_serve_api.py -v

    # With custom MongoDB URI
    FMCP_TEST_MONGODB_URI=mongodb://localhost:27017 pytest tests/test_serve_api.py -v
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
# Test Fixtures
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
    await manager.connect()

    yield manager

    # Cleanup: drop test database
    try:
        await manager.client.drop_database(test_db_name)
    except Exception:
        pass  # Best effort cleanup
    await manager.close()


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
# Server Lifecycle Tests
# ============================================================================

class TestServerLifecycle:
    """Tests for FastAPI server startup and core endpoints."""

    @pytest.mark.asyncio
    async def test_serve_app_startup_and_endpoints(self, api_client):
        """
        Verify FastAPI app starts and all core endpoints are accessible.
        """
        client = api_client

        # Test health endpoint
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "unhealthy"]
        assert "database" in data

        # Test metrics endpoint
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "fluidmcp" in response.text

        # Test API list servers endpoint
        response = await client.get("/api/servers")
        assert response.status_code == 200
        data = response.json()
        # Response can be either a list (old format) or dict with 'servers' key (new format)
        assert isinstance(data, (list, dict))
        if isinstance(data, dict):
            assert "servers" in data or "count" in data

        # Test Swagger UI endpoint
        response = await client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower()


# ============================================================================
# Configuration Management Tests
# ============================================================================

class TestConfigurationManagement:
    """Tests for server configuration validation (without starting servers)."""

    @pytest.mark.asyncio
    async def test_server_config_validation_errors(self, api_client):
        """
        Test that invalid server configurations are rejected with clear errors.
        """
        client = api_client

        # Test 1: Invalid command (not in whitelist)
        invalid_config = {
            "id": "invalid-server",
            "name": "Invalid",
            "command": "/bin/bash",  # Absolute path not allowed
            "args": ["-c", "echo hello"]
        }
        response = await client.post("/api/servers", json=invalid_config)
        assert response.status_code == 400
        assert "absolute path" in response.json()["detail"].lower()

        # Test 2: Shell metacharacter in args
        invalid_config = {
            "id": "invalid-server-2",
            "name": "Invalid",
            "command": "npx",
            "args": ["-y", "package; rm -rf /"]
        }
        response = await client.post("/api/servers", json=invalid_config)
        assert response.status_code == 400
        assert "dangerous pattern" in response.json()["detail"].lower()

        # Test 3: Invalid environment variable names
        invalid_config = {
            "id": "invalid-server-3",
            "name": "Invalid",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "env": {"$INJECTION": "value"}  # MongoDB injection attempt
        }
        response = await client.post("/api/servers", json=invalid_config)
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "injection" in detail or "invalid" in detail


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Tests for error handling and recovery."""

    @pytest.mark.asyncio
    async def test_mongodb_connection_retry_logic(self):
        """
        Test that MongoDB connection handles failure gracefully.
        Uses invalid URI to trigger connection failure.
        """
        # Use invalid URI (non-existent host)
        invalid_uri = "mongodb://nonexistent-host:27017"
        db_manager = DatabaseManager(invalid_uri, "test_db")

        start_time = time.time()

        # Attempt connection (should return False on failure)
        result = await db_manager.connect()

        elapsed_time = time.time() - start_time

        # Should return False for failed connection
        assert result is False, "Connection should fail and return False"

        # Should fail within configured timeout (default 30 seconds)
        assert elapsed_time < 35, f"Connection timeout took {elapsed_time}s, expected < 35s"
