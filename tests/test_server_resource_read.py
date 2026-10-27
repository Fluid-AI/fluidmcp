"""
Tests for POST /api/servers/{id}/resources/read — used by the Tool Runner to
fetch MCP Apps widget HTML (ui:// resources) from a managed server.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.api.management import router
from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager
from fluidmcp.cli.services.stdio_jsonrpc import StdioRequestTimeout


@pytest.fixture
def server_manager():
    manager = ServerManager(InMemoryBackend())
    yield manager
    # Fake processes must not reach the manager's atexit cleanup
    manager.processes.clear()


@pytest.fixture
def client(server_manager):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.server_manager = server_manager
    return TestClient(app)


def _running_process():
    process = MagicMock()
    process.poll.return_value = None
    return process


def _patch_router(response=None, side_effect=None):
    stdio_router = MagicMock()
    stdio_router.request = AsyncMock(return_value=response, side_effect=side_effect)
    return patch("fluidmcp.cli.api.management.get_stdio_router", return_value=stdio_router), stdio_router


class TestReadServerResource:

    def test_returns_resource_contents(self, client, server_manager):
        server_manager.processes["srv"] = _running_process()
        contents = [{"uri": "ui://widget/app.html", "mimeType": "text/html", "text": "<html></html>"}]
        patcher, stdio_router = _patch_router({"jsonrpc": "2.0", "id": 3, "result": {"contents": contents}})

        with patcher:
            resp = client.post("/api/servers/srv/resources/read", json={"uri": "ui://widget/app.html"})

        assert resp.status_code == 200
        assert resp.json() == {"contents": contents}
        sent = stdio_router.request.call_args.args[0]
        assert sent["method"] == "resources/read"
        assert sent["params"] == {"uri": "ui://widget/app.html"}

    def test_400_when_server_not_running(self, client, server_manager):
        resp = client.post("/api/servers/ghost/resources/read", json={"uri": "ui://x"})
        assert resp.status_code == 400

        exited = MagicMock()
        exited.poll.return_value = 1
        server_manager.processes["dead"] = exited
        resp = client.post("/api/servers/dead/resources/read", json={"uri": "ui://x"})
        assert resp.status_code == 400

    def test_500_on_jsonrpc_error(self, client, server_manager):
        server_manager.processes["srv"] = _running_process()
        patcher, _ = _patch_router({"jsonrpc": "2.0", "id": 3, "error": {"code": -32002, "message": "Resource not found"}})

        with patcher:
            resp = client.post("/api/servers/srv/resources/read", json={"uri": "ui://missing"})

        assert resp.status_code == 500
        assert "Resource not found" in resp.json()["detail"]

    def test_504_on_timeout(self, client, server_manager):
        server_manager.processes["srv"] = _running_process()
        patcher, _ = _patch_router(side_effect=StdioRequestTimeout("timeout"))

        with patcher:
            resp = client.post("/api/servers/srv/resources/read", json={"uri": "ui://slow"})

        assert resp.status_code == 504

    def test_rejects_empty_uri(self, client, server_manager):
        server_manager.processes["srv"] = _running_process()
        resp = client.post("/api/servers/srv/resources/read", json={"uri": ""})
        assert resp.status_code == 422
