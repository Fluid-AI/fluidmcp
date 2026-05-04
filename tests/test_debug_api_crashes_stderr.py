"""
Tests for P2 debugging endpoints:
- GET /api/servers/{id}/crashes
- GET /api/servers/{id}/stderr
"""
import os
import pytest
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.api.management import router
from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

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
    app = make_app(server_manager, backend)
    return TestClient(app)


# ---------------------------------------------------------------------------
# /crashes endpoint
# ---------------------------------------------------------------------------

class TestGetServerCrashes:

    def _register_server(self, server_manager, server_id, name="Test Server"):
        server_manager.configs[server_id] = {"id": server_id, "name": name}

    def test_404_for_unknown_server(self, client):
        resp = client.get("/api/servers/ghost/crashes")
        assert resp.status_code == 404

    def test_empty_crashes_for_known_server(self, client, server_manager):
        self._register_server(server_manager, "srv1")
        resp = client.get("/api/servers/srv1/crashes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["server"] == "srv1"
        assert data["crashes"] == []
        assert data["restart_count"] == 0
        assert data["crashes_per_hour"] == 0

    def test_crashes_returned_with_exit_classification(self, client, server_manager, backend):
        self._register_server(server_manager, "srv1")

        # Save a crash event directly into the backend
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            backend.save_crash_event({
                "server_id": "srv1",
                "server_name": "Test Server",
                "exit_code": 137,
                "stderr_tail": "OOM error",
                "uptime_seconds": 60.0,
                "timestamp": datetime.utcnow(),
            })
        )

        resp = client.get("/api/servers/srv1/crashes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["crashes"]) == 1
        crash = data["crashes"][0]
        assert crash["exit_code"] == 137
        assert crash["exit_category"] == "resource"
        assert crash["exit_label"] == "oom_killed"

    def test_crashes_per_hour_counts_recent(self, client, server_manager, backend):
        self._register_server(server_manager, "srv1")

        import asyncio
        loop = asyncio.get_event_loop()

        # Two recent crashes (within last hour)
        for _ in range(2):
            loop.run_until_complete(backend.save_crash_event({
                "server_id": "srv1",
                "server_name": "Test Server",
                "exit_code": 1,
                "stderr_tail": "",
                "uptime_seconds": 10.0,
                "timestamp": datetime.utcnow(),
            }))

        resp = client.get("/api/servers/srv1/crashes")
        assert resp.status_code == 200
        assert resp.json()["crashes_per_hour"] == 2

    def test_limit_query_param_respected(self, client, server_manager, backend):
        self._register_server(server_manager, "srv1")

        import asyncio
        loop = asyncio.get_event_loop()
        for _ in range(5):
            loop.run_until_complete(backend.save_crash_event({
                "server_id": "srv1",
                "server_name": "Test Server",
                "exit_code": 1,
                "stderr_tail": "",
                "uptime_seconds": 5.0,
                "timestamp": datetime.utcnow(),
            }))

        resp = client.get("/api/servers/srv1/crashes?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()["crashes"]) <= 2

    def test_already_classified_crash_not_overwritten(self, client, server_manager, backend):
        """If crash event already has exit_category, don't re-classify."""
        self._register_server(server_manager, "srv1")

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            backend.save_crash_event({
                "server_id": "srv1",
                "server_name": "Test Server",
                "exit_code": 137,
                "exit_category": "resource",
                "exit_label": "oom_killed",
                "exit_description": "custom description",
                "stderr_tail": "",
                "uptime_seconds": 10.0,
                "timestamp": datetime.utcnow(),
            })
        )

        resp = client.get("/api/servers/srv1/crashes")
        crash = resp.json()["crashes"][0]
        assert crash["exit_description"] == "custom description"


# ---------------------------------------------------------------------------
# /stderr endpoint
# ---------------------------------------------------------------------------

class TestGetServerStderr:

    def _register_server(self, server_manager, server_id):
        server_manager.configs[server_id] = {"id": server_id, "name": "Test"}

    def test_404_for_unknown_server(self, client):
        resp = client.get("/api/servers/ghost/stderr")
        assert resp.status_code == 404

    def test_empty_response_when_no_log_file(self, client, server_manager):
        self._register_server(server_manager, "srv1")

        with patch.object(server_manager, "_get_stderr_log_path", return_value="/nonexistent/path.log"):
            resp = client.get("/api/servers/srv1/stderr")

        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == []
        assert data["line_count"] == 0
        assert data["truncated"] is False

    def test_returns_last_n_lines(self, client, server_manager):
        self._register_server(server_manager, "srv1")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            for i in range(20):
                f.write(f"line {i}\n")
            tmp_path = f.name

        try:
            with patch.object(server_manager, "_get_stderr_log_path", return_value=tmp_path):
                resp = client.get("/api/servers/srv1/stderr?lines=5")

            assert resp.status_code == 200
            data = resp.json()
            assert data["line_count"] == 5
            assert data["lines"][-1] == "line 19"
        finally:
            os.unlink(tmp_path)

    def test_contains_filter_applied(self, client, server_manager):
        self._register_server(server_manager, "srv1")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("INFO: server started\n")
            f.write("ERROR: connection refused\n")
            f.write("INFO: retrying\n")
            f.write("ERROR: timeout exceeded\n")
            tmp_path = f.name

        try:
            with patch.object(server_manager, "_get_stderr_log_path", return_value=tmp_path):
                resp = client.get("/api/servers/srv1/stderr?lines=50&contains=ERROR")

            data = resp.json()
            assert data["line_count"] == 2
            assert all("ERROR" in line for line in data["lines"])
        finally:
            os.unlink(tmp_path)

    def test_contains_filter_case_insensitive(self, client, server_manager):
        self._register_server(server_manager, "srv1")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("error: something bad\n")
            f.write("ERROR: something worse\n")
            f.write("info: all good\n")
            tmp_path = f.name

        try:
            with patch.object(server_manager, "_get_stderr_log_path", return_value=tmp_path):
                resp = client.get("/api/servers/srv1/stderr?lines=50&contains=error")

            data = resp.json()
            assert data["line_count"] == 2
        finally:
            os.unlink(tmp_path)

    def test_contains_filter_no_match_returns_empty(self, client, server_manager):
        self._register_server(server_manager, "srv1")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("INFO: all fine\n")
            tmp_path = f.name

        try:
            with patch.object(server_manager, "_get_stderr_log_path", return_value=tmp_path):
                resp = client.get("/api/servers/srv1/stderr?lines=50&contains=FATAL")

            data = resp.json()
            assert data["lines"] == []
            assert data["line_count"] == 0
        finally:
            os.unlink(tmp_path)

    def test_response_includes_file_path(self, client, server_manager):
        self._register_server(server_manager, "srv1")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("hello\n")
            tmp_path = f.name

        try:
            with patch.object(server_manager, "_get_stderr_log_path", return_value=tmp_path):
                resp = client.get("/api/servers/srv1/stderr")

            assert resp.json()["file"] == tmp_path
        finally:
            os.unlink(tmp_path)
