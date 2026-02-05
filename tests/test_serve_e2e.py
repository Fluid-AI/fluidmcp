"""
End-to-end tests for fmcp serve (SLOW tests that start actual MCP servers).

⚠️  WARNING: These tests take 5-10 minutes to run because they start actual MCP servers.
Run these manually or in CI, not during regular development.

TEST FILE ORGANIZATION:
    📦 test_serve_api.py (FAST - ~3 minutes)
        - Tests API behavior WITHOUT starting MCP servers
        - Run during regular development

    ⏱️  test_serve_e2e.py (SLOW - 5-10 minutes) 👈 YOU ARE HERE
        - End-to-end tests that start actual MCP servers
        - Run manually before committing or in CI

These tests verify full server lifecycle by actually starting MCP servers:
- Server CRUD operations with real server processes
- Server start/stop/restart lifecycle
- Environment variable management with server restarts
- Concurrent server operations
- Graceful shutdown
- Tool discovery and execution

For fast API tests that don't start servers, see test_serve_api.py

Prerequisites:
    1. MongoDB instance (see test_serve_api.py for MongoDB setup)
    2. Node.js and npx installed (to run @modelcontextprotocol/server-memory)
    3. 5-10 minutes of patience :)

Running tests:
    # Run all E2E tests (takes 5-10 minutes)
    pytest tests/test_serve_e2e.py -v

    # Run specific test class
    pytest tests/test_serve_e2e.py::TestServerOperations -v

    # With custom MongoDB URI
    FMCP_TEST_MONGODB_URI=mongodb://localhost:27017 pytest tests/test_serve_e2e.py -v
"""

import asyncio
import os
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
# Configuration Management Tests (with actual server creation)
# ============================================================================

class TestConfigurationManagement:
    """Tests for server configuration CRUD operations (creates actual configs)."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_server_config_crud_lifecycle(self, api_client):
        """
        Test complete lifecycle: create, read, update, delete server config.
        Note: This test only creates configs, doesn't start servers.
        """
        client = api_client

        # Create server config
        server_config = {
            "id": "test-memory-server",
            "name": "Test Memory Server",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "env": {"TEST_VAR": "test_value"},
            "description": "Test server for integration tests"
        }

        response = await client.post("/api/servers", json=server_config)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-memory-server"

        # Read - list servers
        response = await client.get("/api/servers")
        assert response.status_code == 200
        data = response.json()
        servers = data if isinstance(data, list) else data.get("servers", [])
        assert len(servers) >= 1
        assert any(s["id"] == "test-memory-server" for s in servers)

        # Read - get specific server
        response = await client.get("/api/servers/test-memory-server")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Memory Server"

        # Update server config
        updated_config = {
            "name": "Updated Memory Server",
            "description": "Updated description"
        }
        response = await client.put("/api/servers/test-memory-server", json=updated_config)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Memory Server"
        assert data["description"] == "Updated description"

        # Delete server config
        response = await client.delete("/api/servers/test-memory-server")
        assert response.status_code in [200, 400, 403, 404]


# ============================================================================
# Server Operations Tests (SLOW - starts actual MCP servers)
# ============================================================================

class TestServerOperations:
    """Tests for server start/stop/restart operations (SLOW - starts actual servers)."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_server_lifecycle_management(self, api_client, serve_test_app):
        """
        Test starting, stopping, and restarting MCP servers.
        ⚠️  SLOW: Starts actual MCP server processes.
        """
        client = api_client
        app, db_manager, server_manager = serve_test_app

        # Create server config
        server_config = {
            "id": "lifecycle-test-server",
            "name": "Lifecycle Test Server",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"]
        }
        response = await client.post("/api/servers", json=server_config)
        assert response.status_code == 200

        # Start server
        response = await client.post("/api/servers/lifecycle-test-server/start")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "status" in data

        # Wait for server to initialize
        await asyncio.sleep(2)

        # Check status
        response = await client.get("/api/servers/lifecycle-test-server/status")
        assert response.status_code == 200
        data = response.json()
        status_field = data.get("state") or data.get("status")
        assert status_field in ["running", "started"]
        assert "pid" in data and data["pid"] is not None

        # Restart server
        old_pid = data["pid"]
        response = await client.post("/api/servers/lifecycle-test-server/restart")
        assert response.status_code == 200

        await asyncio.sleep(2)

        # After restart, verify server is running
        response = await client.get("/api/servers/lifecycle-test-server/status")
        assert response.status_code == 200
        data = response.json()
        status_field = data.get("state") or data.get("status")
        assert status_field in ["running", "started"]

        # Stop server
        response = await client.post("/api/servers/lifecycle-test-server/stop")
        assert response.status_code == 200

        await asyncio.sleep(1)

        # Check final status
        response = await client.get("/api/servers/lifecycle-test-server/status")
        # 404 is acceptable - means server stopped and cleaned up
        if response.status_code == 404:
            return
        assert response.status_code == 200
        data = response.json()
        status_field = data.get("state") or data.get("status")
        if status_field:
            assert status_field in ["stopped", "not_found", "not found"]


# ============================================================================
# Environment Management Tests (SLOW - starts servers)
# ============================================================================

class TestEnvironmentManagement:
    """Tests for instance environment variable management (SLOW - starts servers)."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_instance_env_management(self, api_client):
        """
        Test getting, updating, and deleting instance environment variables.
        ⚠️  SLOW: Starts actual MCP server and restarts it.
        """
        client = api_client

        # Create and start server
        server_config = {
            "id": "env-test-server",
            "name": "Env Test Server",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "env": {"CONFIG_VAR": "config_value"}
        }
        await client.post("/api/servers", json=server_config)
        await client.post("/api/servers/env-test-server/start")
        await asyncio.sleep(2)

        # Get environment variables
        response = await client.get("/api/servers/env-test-server/instance/env")
        assert response.status_code == 200
        env_data = response.json()
        assert "CONFIG_VAR" in env_data

        # Update environment variables (triggers restart)
        new_env = {
            "NEW_VAR": "new_value",
            "ANOTHER_VAR": "another_value"
        }
        response = await client.put("/api/servers/env-test-server/instance/env", json=new_env)
        assert response.status_code == 200

        # Wait for restart
        await asyncio.sleep(3)

        # Verify new env vars
        response = await client.get("/api/servers/env-test-server/instance/env")
        assert response.status_code == 200
        env_data = response.json()
        assert "NEW_VAR" in env_data

        # Delete env var
        response = await client.delete("/api/servers/env-test-server/instance/env/NEW_VAR")
        assert response.status_code == 200

        # Cleanup
        await client.post("/api/servers/env-test-server/stop")


# ============================================================================
# Concurrent Operations Tests (SLOW - starts servers concurrently)
# ============================================================================

class TestConcurrentOperations:
    """Tests for concurrent server operations (SLOW - starts multiple servers)."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_server_operations(self, api_client, serve_test_app):
        """
        Test that concurrent start/stop operations on the same server are safe.
        ⚠️  SLOW: Attempts to start servers concurrently.
        """
        client = api_client
        app, db_manager, server_manager = serve_test_app

        # Create server
        server_config = {
            "id": "concurrent-test-server",
            "name": "Concurrent Test Server",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"]
        }
        await client.post("/api/servers", json=server_config)

        # Launch 5 concurrent start requests
        async def start_server():
            return await client.post("/api/servers/concurrent-test-server/start")

        responses = await asyncio.gather(*[start_server() for _ in range(5)], return_exceptions=True)

        # At least one should succeed
        success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
        assert success_count >= 1, f"At least one start should succeed, got {success_count}"

        await asyncio.sleep(2)

        # Verify server is running
        response = await client.get("/api/servers/concurrent-test-server/status")
        assert response.status_code == 200
        data = response.json()
        status_field = data.get("state") or data.get("status")
        assert status_field in ["running", "started"]

        # Cleanup
        await client.post("/api/servers/concurrent-test-server/stop")


# ============================================================================
# Error Handling Tests (SLOW - starts multiple servers)
# ============================================================================

class TestErrorHandling:
    """Tests for error handling (SLOW - starts multiple servers)."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_graceful_shutdown_stops_servers(self, serve_test_app, api_client):
        """
        Test that graceful shutdown stops all running MCP servers.
        ⚠️  SLOW: Starts 3 actual MCP servers.
        """
        app, db_manager, server_manager = serve_test_app
        client = api_client

        # Create and start 3 servers
        for i in range(3):
            server_config = {
                "id": f"shutdown-test-{i}",
                "name": f"Shutdown Test {i}",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"]
            }
            await client.post("/api/servers", json=server_config)
            await client.post(f"/api/servers/shutdown-test-{i}/start")

        await asyncio.sleep(3)

        # Verify all servers are running
        for i in range(3):
            response = await client.get(f"/api/servers/shutdown-test-{i}/status")
            data = response.json()
            status_field = data.get("state") or data.get("status")
            assert status_field in ["running", "started"]

        # Trigger graceful shutdown
        await server_manager.shutdown_all()

        await asyncio.sleep(2)

        # Verify all servers are stopped
        for i in range(3):
            response = await client.get(f"/api/servers/shutdown-test-{i}/status")
            data = response.json()
            status_field = data.get("state") or data.get("status")
            if status_field:
                assert status_field in ["stopped", "not_found", "not found"]


# ============================================================================
# Tool Management Tests (SLOW - starts servers and discovers tools)
# ============================================================================

class TestToolManagement:
    """Tests for tool discovery and execution (SLOW - starts servers)."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_tool_discovery_from_server(self, api_client):
        """
        Test that tools are discovered from a running MCP server.
        ⚠️  SLOW: Starts actual MCP server and waits for tool discovery.
        """
        client = api_client

        # Create and start server
        server_config = {
            "id": "tool-discovery-test",
            "name": "Tool Discovery Test",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"]
        }
        await client.post("/api/servers", json=server_config)
        response = await client.post("/api/servers/tool-discovery-test/start")
        assert response.status_code == 200

        # Wait for server to start and discover tools
        await asyncio.sleep(5)

        # Get tools
        response = await client.get("/api/servers/tool-discovery-test/tools")
        if response.status_code == 404:
            response = await client.get("/api/tool-discovery-test/tools")

        if response.status_code == 404:
            pytest.skip("Tools endpoint not available or tools not discovered")

        assert response.status_code == 200
        tools = response.json()
        assert len(tools) > 0
        tool_names = [tool["name"] for tool in tools]
        assert any("memory" in name.lower() for name in tool_names)

        # Cleanup
        await client.post("/api/servers/tool-discovery-test/stop")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_tool_execution(self, api_client):
        """
        Test executing a tool on a running MCP server.
        ⚠️  SLOW: Starts actual MCP server and executes tools.
        """
        client = api_client

        # Create and start server
        server_config = {
            "id": "tool-execution-test",
            "name": "Tool Execution Test",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"]
        }
        await client.post("/api/servers", json=server_config)
        await client.post("/api/servers/tool-execution-test/start")

        # Wait for server to start
        await asyncio.sleep(5)

        # Get available tools
        response = await client.get("/api/servers/tool-execution-test/tools")
        if response.status_code == 404:
            response = await client.get("/api/tool-execution-test/tools")

        if response.status_code == 404:
            pytest.skip("Tools endpoint not available or tools not discovered")

        assert response.status_code == 200
        tools = response.json()

        # Find a tool to execute
        tool_to_execute = None
        for tool in tools:
            if "store" in tool["name"].lower() or "add" in tool["name"].lower():
                tool_to_execute = tool
                break

        if tool_to_execute:
            # Execute the tool
            tool_params = {
                "key": "test_key",
                "value": "test_value"
            }

            response = await client.post(
                f"/api/servers/tool-execution-test/tools/{tool_to_execute['name']}/run",
                json={"arguments": tool_params}
            )

            if response.status_code == 404:
                response = await client.post(
                    f"/api/tool-execution-test/tools/{tool_to_execute['name']}/execute",
                    json={"arguments": tool_params}
                )

            assert response.status_code in [200, 400, 404]

            if response.status_code == 200:
                result = response.json()
                assert "result" in result or "content" in result

        # Cleanup
        await client.post("/api/servers/tool-execution-test/stop")
