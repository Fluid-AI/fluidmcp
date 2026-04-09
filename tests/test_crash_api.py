"""
Tests for crash history API endpoints.

Tests GET /api/servers/{id}/crashes and GET /api/crashes using
the in-memory backend — no MongoDB required.
"""
import pytest
from datetime import datetime

from httpx import AsyncClient, ASGITransport

from fluidmcp.cli.server import create_app
from fluidmcp.cli.repositories.memory import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager


@pytest.fixture
async def app_with_crashes():
    """Create app with in-memory backend pre-populated with crash events."""
    backend = InMemoryBackend()
    await backend.connect()

    server_manager = ServerManager(backend)

    # Save a server config
    await backend.save_server_config({
        "id": "srv1",
        "name": "Test Server",
        "command": "echo",
        "args": [],
        "env": {},
        "restart_policy": "on-failure"
    })
    server_manager.configs["srv1"] = {"id": "srv1", "name": "Test Server"}

    # Save crash events
    await backend.save_crash_event({
        "server_id": "srv1",
        "exit_code": 1,
        "stderr_tail": "OOM error",
        "uptime_seconds": 120.0,
        "timestamp": datetime(2026, 3, 31, 10, 0, 0)
    })
    await backend.save_crash_event({
        "server_id": "srv1",
        "exit_code": 137,
        "stderr_tail": "Killed",
        "uptime_seconds": 300.0,
        "timestamp": datetime(2026, 3, 31, 11, 0, 0)
    })

    app = await create_app(
        db_manager=backend,
        server_manager=server_manager,
        secure_mode=False,
        token=None,
        allowed_origins=["http://localhost"]
    )

    yield app, backend, server_manager

    await backend.disconnect()


@pytest.fixture
async def client(app_with_crashes):
    app, backend, server_manager = app_with_crashes
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, backend, server_manager


class TestGetServerCrashes:
    """Tests for GET /api/servers/{id}/crashes"""

    @pytest.mark.asyncio
    async def test_returns_crash_events(self, client):
        c, _, _ = client
        response = await c.get("/api/servers/srv1/crashes")
        assert response.status_code == 200
        data = response.json()
        assert data["server_id"] == "srv1"
        assert data["count"] == 2
        assert len(data["crashes"]) == 2

    @pytest.mark.asyncio
    async def test_404_for_unknown_server(self, client):
        c, _, _ = client
        response = await c.get("/api/servers/unknown-server/crashes")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_limit_respected(self, client):
        c, _, _ = client
        response = await c.get("/api/servers/srv1/crashes?limit=1")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["crashes"]) == 1

    @pytest.mark.asyncio
    async def test_limit_bounds_enforced(self, client):
        c, _, _ = client
        # limit=0 should be rejected (ge=1)
        response = await c.get("/api/servers/srv1/crashes?limit=0")
        assert response.status_code == 422

        # limit=101 should be rejected (le=100)
        response = await c.get("/api/servers/srv1/crashes?limit=101")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_most_recent_first(self, client):
        c, _, _ = client
        response = await c.get("/api/servers/srv1/crashes")
        assert response.status_code == 200
        crashes = response.json()["crashes"]
        # Most recent event (11:00) should be first
        assert crashes[0]["exit_code"] == 137


class TestListAllCrashes:
    """Tests for GET /api/crashes"""

    @pytest.mark.asyncio
    async def test_returns_all_crashes(self, client):
        c, _, _ = client
        response = await c.get("/api/crashes")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["crashes"]) == 2

    @pytest.mark.asyncio
    async def test_limit_respected(self, client):
        c, _, _ = client
        response = await c.get("/api/crashes?limit=1")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_limit_bounds_enforced(self, client):
        c, _, _ = client
        response = await c.get("/api/crashes?limit=0")
        assert response.status_code == 422

        response = await c.get("/api/crashes?limit=201")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_sorted_most_recent_first(self, client):
        c, _, _ = client
        response = await c.get("/api/crashes")
        assert response.status_code == 200
        crashes = response.json()["crashes"]
        assert crashes[0]["exit_code"] == 137  # 11:00 event

    @pytest.mark.asyncio
    async def test_empty_when_no_crashes(self, app_with_crashes):
        """Returns empty list when no crash events exist."""
        _, backend, server_manager = app_with_crashes
        # Fresh backend with no crashes
        fresh_backend = InMemoryBackend()
        await fresh_backend.connect()
        fresh_sm = ServerManager(fresh_backend)
        await fresh_backend.save_server_config({"id": "clean", "name": "clean", "command": "echo", "args": [], "env": {}})
        fresh_sm.configs["clean"] = {"id": "clean"}

        app = await create_app(
            db_manager=fresh_backend,
            server_manager=fresh_sm,
            secure_mode=False,
            token=None,
            allowed_origins=["http://localhost"]
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/api/crashes")
        assert response.status_code == 200
        assert response.json()["count"] == 0
        await fresh_backend.disconnect()
