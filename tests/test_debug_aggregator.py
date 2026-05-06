"""
Tests for GET /api/servers/{id}/debug aggregator endpoint.

Covers:
- 404 for unknown server
- All top-level keys present
- status section present and correct
- resources null when not running
- resources populated when running
- concurrency section present
- crashes section present with events list
- stderr section present (empty when no log file)
- stderr_lines query param respected
- crashes annotated with exit classification
"""
import os
import pytest
import tempfile
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.api.management import router
from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager


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


def _register(server_manager, server_id, name="Test"):
    server_manager.configs[server_id] = {"id": server_id, "name": name}


# ---------------------------------------------------------------------------
# Basic shape
# ---------------------------------------------------------------------------

class TestDebugAggregatorShape:

    def test_404_for_unknown_server(self, client):
        resp = client.get("/api/servers/ghost/debug")
        assert resp.status_code == 404

    def test_all_top_level_keys_present(self, client, server_manager):
        _register(server_manager, "srv")
        resp = client.get("/api/servers/srv/debug")
        assert resp.status_code == 200
        keys = resp.json().keys()
        for expected in ["server", "status", "resources", "concurrency", "crashes", "stderr"]:
            assert expected in keys, f"missing top-level key: {expected}"

    def test_server_field_matches_id(self, client, server_manager):
        _register(server_manager, "srv")
        assert client.get("/api/servers/srv/debug").json()["server"] == "srv"

    def test_status_section_has_state(self, client, server_manager):
        _register(server_manager, "srv")
        data = client.get("/api/servers/srv/debug").json()
        assert "state" in data["status"]

    def test_resources_null_when_not_running(self, client, server_manager):
        _register(server_manager, "srv")
        data = client.get("/api/servers/srv/debug").json()
        assert data["resources"]["memory_rss_bytes"] is None
        assert data["resources"]["cpu_percent"] is None

    def test_concurrency_section_present(self, client, server_manager):
        _register(server_manager, "srv")
        data = client.get("/api/servers/srv/debug").json()
        conc = data["concurrency"]
        for key in ["max_concurrent_requests", "active_requests", "available_slots", "rejected_total"]:
            assert key in conc, f"missing concurrency key: {key}"

    def test_crashes_section_present(self, client, server_manager):
        _register(server_manager, "srv")
        data = client.get("/api/servers/srv/debug").json()
        crashes = data["crashes"]
        for key in ["recent_crash_count", "crashes_per_hour", "events"]:
            assert key in crashes, f"missing crashes key: {key}"
        assert isinstance(crashes["events"], list)

    def test_stderr_section_present(self, client, server_manager):
        _register(server_manager, "srv")
        data = client.get("/api/servers/srv/debug").json()
        stderr = data["stderr"]
        for key in ["lines", "line_count", "truncated", "file"]:
            assert key in stderr, f"missing stderr key: {key}"

    def test_stderr_empty_when_no_log_file(self, client, server_manager):
        _register(server_manager, "srv")
        data = client.get("/api/servers/srv/debug").json()
        assert data["stderr"]["lines"] == []
        assert data["stderr"]["line_count"] == 0


# ---------------------------------------------------------------------------
# Running server resources
# ---------------------------------------------------------------------------

class TestDebugAggregatorRunning:

    def test_resources_populated_when_running(self, client, server_manager):
        _register(server_manager, "srv")
        mock_process = Mock()
        mock_process.pid = 1234
        mock_process.poll = Mock(return_value=None)
        server_manager.processes["srv"] = mock_process

        import asyncio
        from fluidmcp.cli.repositories import InMemoryBackend
        asyncio.get_event_loop().run_until_complete(
            server_manager.db.save_instance_state({
                "server_id": "srv", "state": "running", "pid": 1234
            })
        )

        mock_proc = Mock()
        mock_proc.memory_info = Mock(return_value=Mock(rss=52428800))
        mock_proc.num_fds = Mock(return_value=15)
        mock_proc.num_threads = Mock(return_value=4)

        with patch("psutil.Process", return_value=mock_proc):
            data = client.get("/api/servers/srv/debug").json()

        assert data["resources"]["memory_rss_bytes"] == 52428800
        assert data["resources"]["pid"] == 1234
        assert data["resources"]["open_fds"] == 15
        assert data["resources"]["threads"] == 4


# ---------------------------------------------------------------------------
# Stderr
# ---------------------------------------------------------------------------

class TestDebugAggregatorStderr:

    def test_stderr_lines_returned_from_log_file(self, client, server_manager):
        _register(server_manager, "srv")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            for i in range(30):
                f.write(f"log line {i}\n")
            log_path = f.name

        try:
            server_manager._get_stderr_log_path = Mock(return_value=log_path)
            data = client.get("/api/servers/srv/debug").json()
            # Default is 20 lines
            assert data["stderr"]["line_count"] == 20
            assert "log line 29" in data["stderr"]["lines"][-1]
        finally:
            os.unlink(log_path)

    def test_stderr_lines_param_respected(self, client, server_manager):
        _register(server_manager, "srv")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            for i in range(30):
                f.write(f"log line {i}\n")
            log_path = f.name

        try:
            server_manager._get_stderr_log_path = Mock(return_value=log_path)
            data = client.get("/api/servers/srv/debug?stderr_lines=5").json()
            assert data["stderr"]["line_count"] == 5
        finally:
            os.unlink(log_path)


# ---------------------------------------------------------------------------
# Crash annotation
# ---------------------------------------------------------------------------

class TestDebugAggregatorCrashes:

    def test_crashes_annotated_with_exit_classification(self, client, server_manager, backend):
        import asyncio
        _register(server_manager, "srv")
        asyncio.get_event_loop().run_until_complete(
            backend.save_crash_event({
                "server_id": "srv",
                "exit_code": 137,
                "timestamp": __import__("datetime").datetime.utcnow(),
            })
        )

        data = client.get("/api/servers/srv/debug").json()
        events = data["crashes"]["events"]
        assert len(events) == 1
        assert events[0]["exit_label"] == "oom_killed"
        assert events[0]["exit_category"] == "resource"

    def test_crashes_per_hour_computed(self, client, server_manager, backend):
        import asyncio
        _register(server_manager, "srv")
        asyncio.get_event_loop().run_until_complete(
            backend.save_crash_event({
                "server_id": "srv",
                "exit_code": 1,
                "timestamp": __import__("datetime").datetime.utcnow(),
            })
        )

        data = client.get("/api/servers/srv/debug").json()
        assert data["crashes"]["crashes_per_hour"] == 1.0
        assert data["crashes"]["recent_crash_count"] == 1
