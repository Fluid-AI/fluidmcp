"""
Tests for P6 - concurrency limiting.

Covers:
- GET /api/servers/{id}/concurrency: 404, unlimited, limited with no active, correct slot math
- rejected_total increments in Prometheus counter
- Semaphore: no limit when config absent / zero
- Semaphore: created once and reused (singleton per server)
- Semaphore: acquire/release under the limit
- Semaphore slots: correct _value before and after acquire
"""
import asyncio
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.api.management import router
from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager
from fluidmcp.cli.services.metrics import get_registry, MetricsCollector


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
