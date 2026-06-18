"""
Tests for P6 - concurrency limiting.

Covers:
- GET /api/servers/{id}/concurrency: 404, unlimited, limited with no active, correct slot math
- rejected_total increments in Prometheus counter
- Semaphore: no limit when config absent / zero
- Semaphore: created once and reused (singleton per server)
- Semaphore: acquire/release under the limit
- Semaphore slots: correct _value before and after acquire
- 429 response when semaphore is full (most important behavior)
- null/invalid max_concurrent_requests values
- Enriched GET /api/servers/{id} response shape
"""
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.api.management import router
from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager
from fluidmcp.cli.services.metrics import get_registry
from fluidmcp.cli.services.package_launcher import create_dynamic_router
from fluidmcp.cli.services.network_handle import NetworkSubprocessHandle


def make_app(server_manager, db_manager):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.server_manager = server_manager
    app.state.db_manager = db_manager
    return app


@pytest.fixture
def backend():
    return InMemoryBackend()


@pytest.fixture
def server_manager(backend):
    return ServerManager(backend)


@pytest.fixture
def client(server_manager, backend):
    return TestClient(make_app(server_manager, backend))


def _register(server_manager, server_id, max_concurrent_requests=0):
    server_manager.configs[server_id] = {
        "id": server_id,
        "name": "Test",
        "max_concurrent_requests": max_concurrent_requests,
    }


# ---------------------------------------------------------------------------
# GET /api/servers/{id}/concurrency endpoint
# ---------------------------------------------------------------------------

class TestGetConcurrencyEndpoint:

    def test_404_for_unknown_server(self, client):
        resp = client.get("/api/servers/ghost/concurrency")
        assert resp.status_code == 404

    def test_unlimited_when_not_configured(self, client, server_manager):
        _register(server_manager, "srv")
        resp = client.get("/api/servers/srv/concurrency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_concurrent_requests"] is None
        assert data["active_requests"] is None
        assert data["available_slots"] is None

    def test_limited_shows_correct_info(self, client, server_manager):
        _register(server_manager, "srv", max_concurrent_requests=5)
        resp = client.get("/api/servers/srv/concurrency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_concurrent_requests"] == 5
        assert data["active_requests"] == 0
        assert data["available_slots"] == 5

    def test_response_has_all_expected_keys(self, client, server_manager):
        _register(server_manager, "srv")
        resp = client.get("/api/servers/srv/concurrency")
        assert resp.status_code == 200
        keys = resp.json().keys()
        for expected in ["server", "max_concurrent_requests", "active_requests",
                         "available_slots", "rejected_total"]:
            assert expected in keys, f"missing key: {expected}"

    def test_rejected_total_reflects_counter(self, client, server_manager):
        _register(server_manager, "srv")
        # Manually increment the rejection counter
        registry = get_registry()
        counter = registry.get_metric("fluidmcp_requests_rejected_total")
        counter.inc({"server_id": "srv", "reason": "concurrency_limit"}, amount=3)

        resp = client.get("/api/servers/srv/concurrency")
        assert resp.json()["rejected_total"] == 3


# ---------------------------------------------------------------------------
# ServerManager.get_concurrency_semaphore()
# ---------------------------------------------------------------------------

class TestGetConcurrencySemaphore:

    def test_returns_none_when_not_configured(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv"}
        assert server_manager.get_concurrency_semaphore("srv") is None

    def test_returns_none_when_limit_is_zero(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": 0}
        assert server_manager.get_concurrency_semaphore("srv") is None

    def test_returns_semaphore_when_limit_set(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": 3}
        sem = server_manager.get_concurrency_semaphore("srv")
        assert sem is not None
        assert sem._value == 3

    def test_semaphore_is_singleton(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": 3}
        sem1 = server_manager.get_concurrency_semaphore("srv")
        sem2 = server_manager.get_concurrency_semaphore("srv")
        assert sem1 is sem2

    @pytest.mark.asyncio
    async def test_semaphore_slots_decrement_on_acquire(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": 2}
        sem = server_manager.get_concurrency_semaphore("srv")
        assert sem._value == 2
        await sem.acquire()
        assert sem._value == 1
        sem.release()
        assert sem._value == 2

    @pytest.mark.asyncio
    async def test_semaphore_full_when_all_slots_taken(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": 1}
        sem = server_manager.get_concurrency_semaphore("srv")
        await sem.acquire()
        assert sem._value == 0  # exhausted — next acquire would block
        sem.release()


# ---------------------------------------------------------------------------
# ServerManager.get_concurrency_info()
# ---------------------------------------------------------------------------

class TestGetConcurrencyInfo:

    def test_unlimited_server(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv"}
        info = server_manager.get_concurrency_info("srv")
        assert info["max_concurrent_requests"] is None
        assert info["active_requests"] is None
        assert info["available_slots"] is None

    @pytest.mark.asyncio
    async def test_limited_server_shows_slot_math(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": 4}
        sem = server_manager.get_concurrency_semaphore("srv")
        await sem.acquire()
        await sem.acquire()

        info = server_manager.get_concurrency_info("srv")
        assert info["max_concurrent_requests"] == 4
        assert info["active_requests"] == 2
        assert info["available_slots"] == 2

        sem.release()
        sem.release()


# ---------------------------------------------------------------------------
# 429 when semaphore is full
# ---------------------------------------------------------------------------

class TestConcurrencyLimiting429:
    """The most important behavior: 429 + Retry-After when all slots are occupied."""

    def _make_mcp_app(self, server_manager):
        app = FastAPI()
        mcp_router = create_dynamic_router(server_manager)
        app.include_router(mcp_router)
        return app

    @pytest.mark.asyncio
    async def test_429_when_semaphore_full(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": 1}
        # Exhaust the one available slot manually
        sem = server_manager.get_concurrency_semaphore("srv")
        await sem.acquire()

        # Use a mock so the 503 "process is None" guard doesn't fire before the semaphore check.
        fake_process = MagicMock()
        fake_process.poll.return_value = None  # pretend process is alive
        server_manager.processes["srv"] = fake_process

        app = self._make_mcp_app(server_manager)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/srv/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "1"
        assert "too many concurrent requests" in resp.text

        sem.release()

    @pytest.mark.asyncio
    async def test_429_network_transport_when_semaphore_full(self, server_manager):
        """Network/SSE-backed servers must also be blocked when the semaphore is full."""
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": 1}
        sem = server_manager.get_concurrency_semaphore("srv")
        await sem.acquire()

        # Build a real NetworkSubprocessHandle with a mock subprocess so isinstance() passes
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None  # looks alive for the fast-path check
        handle = NetworkSubprocessHandle(fake_proc, base_url="http://127.0.0.1:9999", transport="sse")
        server_manager.processes["srv"] = handle

        app = self._make_mcp_app(server_manager)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/srv/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "1"

        sem.release()
        await handle.aclose()


# ---------------------------------------------------------------------------
# null / invalid max_concurrent_requests config values
# ---------------------------------------------------------------------------

class TestNullMaxConcurrentRequests:

    def test_null_value_returns_none_semaphore(self, server_manager):
        """'max_concurrent_requests': null must not crash with TypeError."""
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": None}
        sem = server_manager.get_concurrency_semaphore("srv")
        assert sem is None

    def test_null_value_concurrency_info_unlimited(self, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": None}
        info = server_manager.get_concurrency_info("srv")
        assert info["max_concurrent_requests"] is None
        assert info["active_requests"] is None
        assert info["available_slots"] is None

    def test_null_via_endpoint(self, client, server_manager):
        server_manager.configs["srv"] = {"id": "srv", "max_concurrent_requests": None}
        resp = client.get("/api/servers/srv/concurrency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_concurrent_requests"] is None


# ---------------------------------------------------------------------------
# Enriched GET /api/servers/{id} response shape
# ---------------------------------------------------------------------------

class TestEnrichedServerGetShape:

    def test_response_includes_debug_sections(self, client, server_manager):
        """GET /api/servers/{id} must include resources, concurrency, and crashes sections."""
        _register(server_manager, "srv", max_concurrent_requests=3)

        resp = client.get("/api/servers/srv")
        assert resp.status_code == 200
        data = resp.json()

        assert "resources" in data, "missing 'resources' section"
        assert "concurrency" in data, "missing 'concurrency' section"
        assert "crashes" in data, "missing 'crashes' section"

    def test_concurrency_section_shape(self, client, server_manager):
        _register(server_manager, "srv", max_concurrent_requests=5)
        data = client.get("/api/servers/srv").json()
        conc = data["concurrency"]
        assert conc["max_concurrent_requests"] == 5
        assert conc["active_requests"] == 0
        assert conc["available_slots"] == 5
        assert "rejected_total" in conc

    def test_crashes_section_uses_correct_field_name(self, client, server_manager):
        """Field must be crashes_last_hour, not the old crashes_per_hour."""
        _register(server_manager, "srv")
        data = client.get("/api/servers/srv").json()
        crashes = data["crashes"]
        assert "crashes_last_hour" in crashes, "field renamed from crashes_per_hour"
        assert "crashes_per_hour" not in crashes, "old field name must not be present"

    def test_unauthenticated_request_is_rejected(self, server_manager, backend, monkeypatch):
        """GET /api/servers/{id} must require auth in secure mode — it returns protected debug telemetry."""
        monkeypatch.setenv("FMCP_SECURE_MODE", "true")
        monkeypatch.setenv("FMCP_BEARER_TOKEN", "test-secret")
        _register(server_manager, "srv")
        # Build a client with no Authorization header
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.state.server_manager = server_manager
        app.state.db_manager = backend
        unauthed_client = TestClient(app, raise_server_exceptions=False)
        resp = unauthed_client.get("/api/servers/srv")
        assert resp.status_code in (401, 403), (
            f"Expected 401/403 for unauthenticated request, got {resp.status_code}"
        )
