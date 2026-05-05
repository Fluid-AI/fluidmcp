"""
Tests for P3 debugging endpoint:
- GET /api/servers/{id}/resources
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.api.management import router
from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager, MCPHealthMonitor


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


def _register(server_manager, server_id, name="Test", memory_limit_mb=0):
    server_manager.configs[server_id] = {
        "id": server_id,
        "name": name,
        "memory_limit_mb": memory_limit_mb,
    }


class TestGetServerResources:

    def test_404_for_unknown_server(self, client):
        resp = client.get("/api/servers/ghost/resources")
        assert resp.status_code == 404

    def test_not_running_when_no_process(self, client, server_manager):
        _register(server_manager, "srv1")
        resp = client.get("/api/servers/srv1/resources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_running"
        assert data["pid"] is None

    def test_running_server_returns_psutil_data(self, client, server_manager):
        _register(server_manager, "srv1")

        mock_process = Mock()
        mock_process.pid = 1234
        mock_process.poll = Mock(return_value=None)  # alive
        server_manager.processes["srv1"] = mock_process

        mock_proc = Mock()
        mock_proc.memory_info = Mock(return_value=Mock(rss=52428800))
        mock_proc.cpu_percent = Mock(return_value=12.5)
        mock_proc.num_fds = Mock(return_value=24)
        mock_proc.num_threads = Mock(return_value=4)

        with patch("psutil.Process", return_value=mock_proc):
            resp = client.get("/api/servers/srv1/resources")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["pid"] == 1234
        assert data["memory_rss_bytes"] == 52428800
        assert data["memory_rss_human"] == "50.0 MB"
        assert data["cpu_percent"] == 12.5
        assert data["open_fds"] == 24
        assert data["threads"] == 4

    def test_memory_usage_pct_computed_when_limit_set(self, client, server_manager):
        _register(server_manager, "srv1", memory_limit_mb=100)

        mock_process = Mock()
        mock_process.pid = 1234
        mock_process.poll = Mock(return_value=None)
        server_manager.processes["srv1"] = mock_process

        mock_proc = Mock()
        mock_proc.memory_info = Mock(return_value=Mock(rss=52428800))  # 50MB
        mock_proc.cpu_percent = Mock(return_value=0.0)
        mock_proc.num_fds = Mock(return_value=10)
        mock_proc.num_threads = Mock(return_value=2)

        with patch("psutil.Process", return_value=mock_proc):
            resp = client.get("/api/servers/srv1/resources")

        data = resp.json()
        assert data["memory_limit_bytes"] == 100 * 1024 * 1024
        assert data["memory_limit_human"] == "100.0 MB"
        assert data["memory_usage_pct"] == 50.0
        assert data["memory_limit_note"] is None

    def test_memory_limit_note_when_no_limit_configured(self, client, server_manager):
        _register(server_manager, "srv1", memory_limit_mb=0)

        mock_process = Mock()
        mock_process.pid = 1234
        mock_process.poll = Mock(return_value=None)
        server_manager.processes["srv1"] = mock_process

        mock_proc = Mock()
        mock_proc.memory_info = Mock(return_value=Mock(rss=1024))
        mock_proc.cpu_percent = Mock(return_value=0.0)
        mock_proc.num_fds = Mock(return_value=5)
        mock_proc.num_threads = Mock(return_value=1)

        with patch("psutil.Process", return_value=mock_proc):
            resp = client.get("/api/servers/srv1/resources")

        data = resp.json()
        assert data["memory_usage_pct"] is None
        assert data["memory_limit_note"] is not None
        assert "FMCP_DEFAULT_MEMORY_LIMIT_MB" in data["memory_limit_note"]

    def test_falls_back_to_cached_snapshot_when_process_dead(self, client, server_manager):
        _register(server_manager, "srv1")

        # Process exists but has exited
        mock_process = Mock()
        mock_process.pid = 1234
        mock_process.poll = Mock(return_value=1)  # dead
        server_manager.processes["srv1"] = mock_process

        # Health monitor has a cached snapshot
        mock_monitor = Mock()
        mock_monitor._last_resource_snapshot = {
            "srv1": {"memory_rss_bytes": 10485760, "cpu_percent": 5.0, "open_fds": 8}
        }
        mock_monitor.get_memory_trend = Mock(return_value="stable")
        server_manager._health_monitor = mock_monitor

        import psutil
        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(pid=1234)):
            resp = client.get("/api/servers/srv1/resources")

        data = resp.json()
        assert data["status"] == "not_running"
        assert data["memory_rss_bytes"] == 10485760
        assert data["cpu_percent"] == 5.0

    def test_memory_trend_from_monitor(self, client, server_manager):
        _register(server_manager, "srv1")

        mock_monitor = Mock()
        mock_monitor._last_resource_snapshot = {}
        mock_monitor.get_memory_trend = Mock(return_value="increasing")
        server_manager._health_monitor = mock_monitor

        resp = client.get("/api/servers/srv1/resources")
        assert resp.json()["memory_trend"] == "increasing"

    def test_memory_trend_unknown_when_no_monitor(self, client, server_manager):
        _register(server_manager, "srv1")
        # No _health_monitor set
        resp = client.get("/api/servers/srv1/resources")
        assert resp.json()["memory_trend"] == "unknown"

    def test_response_has_all_expected_keys(self, client, server_manager):
        _register(server_manager, "srv1")
        resp = client.get("/api/servers/srv1/resources")
        assert resp.status_code == 200
        keys = resp.json().keys()
        for expected in [
            "server", "pid", "status", "memory_rss_bytes", "memory_rss_human",
            "memory_trend", "memory_limit_bytes", "memory_limit_human",
            "memory_usage_pct", "memory_limit_note", "cpu_percent",
            "open_fds", "threads",
        ]:
            assert expected in keys, f"missing key: {expected}"
