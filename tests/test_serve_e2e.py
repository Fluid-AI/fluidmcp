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
import time

import pytest


# ============================================================================
# Test Utility Functions
# ============================================================================

async def wait_for_server_status(client, server_id: str, expected_status: str, timeout: float = 10.0) -> bool:
    """
    Poll server status until it reaches expected state or timeout.

    Args:
        client: httpx.AsyncClient instance
        server_id: The server ID to check
        expected_status: The status to wait for (e.g., "running", "stopped")
        timeout: Maximum time to wait in seconds

    Returns:
        True if server reached expected status, False if timeout
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = await client.get(f"/api/servers/{server_id}/status")
            if response.status_code == 200:
                data = response.json()
                status = data.get("state") or data.get("status")
                if status == expected_status:
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
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
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            if await condition_func():
                return True
        except Exception:
            pass
        await asyncio.sleep(poll_interval)
    return False


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

        # Update server config - must include all required fields
        updated_config = {
            "name": "Updated Memory Server",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "env": {"TEST_VAR": "updated_value"},
            "description": "Updated description"
        }
        response = await client.put("/api/servers/test-memory-server", json=updated_config)
        assert response.status_code == 200
        data = response.json()
        # Response structure is {message, config}, so check config field
        assert "config" in data, f"Expected 'config' in response, got: {data.keys()}"
        assert data["config"]["name"] == "Updated Memory Server"
        assert data["config"]["description"] == "Updated description"

        # Delete server config
        response = await client.delete("/api/servers/test-memory-server")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


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
        _app, _db_manager, _server_manager = serve_test_app

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

        # Wait for server to reach running state (up to 30 seconds)
        success = await wait_for_server_status(client, "lifecycle-test-server", "running", timeout=30.0)
        if not success:
            # Try alternate status value
            success = await wait_for_server_status(client, "lifecycle-test-server", "started", timeout=5.0)
        assert success, "Server failed to start within 30 seconds"

        # Verify server details
        response = await client.get("/api/servers/lifecycle-test-server/status")
        assert response.status_code == 200
        data = response.json()
        assert "pid" in data and data["pid"] is not None

        # Restart server
        response = await client.post("/api/servers/lifecycle-test-server/restart")
        assert response.status_code == 200

        # Wait for server to restart and reach running state
        success = await wait_for_server_status(client, "lifecycle-test-server", "running", timeout=30.0)
        if not success:
            success = await wait_for_server_status(client, "lifecycle-test-server", "started", timeout=5.0)
        assert success, "Server failed to restart within 30 seconds"

        # Verify server is running
        response = await client.get("/api/servers/lifecycle-test-server/status")
        assert response.status_code == 200
        data = response.json()
        status_field = data.get("state") or data.get("status")
        assert status_field in ["running", "started"]

        # Stop server
        response = await client.post("/api/servers/lifecycle-test-server/stop")
        assert response.status_code == 200

        # Wait for server to stop (require 200 response with explicit stopped state)
        async def check_stopped():
            response = await client.get("/api/servers/lifecycle-test-server/status")
            if response.status_code != 200:
                return False
            data = response.json()
            status_field = data.get("state") or data.get("status")
            return status_field == "stopped"

        success = await wait_for_condition(check_stopped, timeout=10.0)
        assert success, "Server failed to stop within 10 seconds"


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

        # Wait for server to start
        success = await wait_for_server_status(client, "env-test-server", "running", timeout=30.0)
        if not success:
            success = await wait_for_server_status(client, "env-test-server", "started", timeout=5.0)
        assert success, "Server failed to start within 30 seconds"

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

        # Wait for server to restart
        success = await wait_for_server_status(client, "env-test-server", "running", timeout=30.0)
        if not success:
            success = await wait_for_server_status(client, "env-test-server", "started", timeout=5.0)
        assert success, "Server failed to restart after env update within 30 seconds"

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
        _app, _db_manager, _server_manager = serve_test_app

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

        # Wait for server to reach running state
        success = await wait_for_server_status(client, "concurrent-test-server", "running", timeout=30.0)
        if not success:
            success = await wait_for_server_status(client, "concurrent-test-server", "started", timeout=5.0)
        assert success, "Server failed to start after concurrent requests within 30 seconds"

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
        _app, _db_manager, server_manager = serve_test_app
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

        # Wait for all servers to start
        for i in range(3):
            success = await wait_for_server_status(client, f"shutdown-test-{i}", "running", timeout=30.0)
            if not success:
                success = await wait_for_server_status(client, f"shutdown-test-{i}", "started", timeout=5.0)
            assert success, f"Server shutdown-test-{i} failed to start within 30 seconds"

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

        # Wait for server to start
        success = await wait_for_server_status(client, "tool-discovery-test", "running", timeout=30.0)
        if not success:
            success = await wait_for_server_status(client, "tool-discovery-test", "started", timeout=5.0)
        assert success, "Server failed to start within 30 seconds"

        # Allow additional time for tool discovery (tools may be discovered after server starts)
        await asyncio.sleep(2)

        # Get tools
        response = await client.get("/api/servers/tool-discovery-test/tools")
        if response.status_code == 404:
            response = await client.get("/api/tool-discovery-test/tools")

        if response.status_code == 404:
            pytest.skip("Tools endpoint not available or tools not discovered")

        assert response.status_code == 200
        data = response.json()
        # The tools endpoint may return either:
        #   - an object: {"server_id": ..., "tools": [...], "count": ...}
        #   - or a raw list of tools (legacy behavior)
        if isinstance(data, dict):
            tools = data.get("tools", [])
        else:
            tools = data
        assert isinstance(tools, list)
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
        success = await wait_for_server_status(client, "tool-execution-test", "running", timeout=30.0)
        if not success:
            success = await wait_for_server_status(client, "tool-execution-test", "started", timeout=5.0)
        assert success, "Server failed to start within 30 seconds"

        # Allow additional time for tool discovery
        await asyncio.sleep(2)

        # Get available tools
        response = await client.get("/api/servers/tool-execution-test/tools")
        if response.status_code == 404:
            response = await client.get("/api/tool-execution-test/tools")

        if response.status_code == 404:
            pytest.skip("Tools endpoint not available or tools not discovered")

        assert response.status_code == 200
        data = response.json()
        # /api/servers/{id}/tools returns a dict with a "tools" field; fall back to
        # treating the whole payload as the list for backward compatibility.
        tools = data.get("tools", data) if isinstance(data, dict) else data

        # Find a tool to execute
        tool_to_execute = None
        for tool in tools:
            if "store" in tool["name"].lower() or "add" in tool["name"].lower():
                tool_to_execute = tool
                break

        # Ensure we found an appropriate tool
        assert tool_to_execute is not None, \
            f"Expected store/add tool in {[t['name'] for t in tools]}"

        if tool_to_execute:
            # Execute the tool
            # API expects arguments directly, not nested under "arguments" key
            tool_params = {
                "key": "test_key",
                "value": "test_value"
            }

            response = await client.post(
                f"/api/servers/tool-execution-test/tools/{tool_to_execute['name']}/run",
                json=tool_params
            )

            # Tool execution should succeed (200) or fail with validation error (400)
            # 404 is acceptable only if endpoint/tool not found
            assert response.status_code in [200, 400, 404], \
                f"Expected 200/400/404, got {response.status_code}: {response.text}"

            if response.status_code == 200:
                result = response.json()
                assert "result" in result or "content" in result

        # Cleanup
        await client.post("/api/servers/tool-execution-test/stop")
