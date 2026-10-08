"""Regression tests for the on-prem `fmcp run --file` workflow (python servers,
per-server env_file, TRANSPORT_TYPE=http).

Each test pins one bug found while auditing that workflow:
  - SSE-framed responses: a notification sent before the result was returned
    to the client instead of the result.
  - env_file was popped from the cached config, so a manual restart respawned
    the server without its env_file vars (no TRANSPORT_TYPE / DB credentials).
  - A missing/unreadable env_file only logged a warning and the server started
    with the wrong environment.
  - A startup cancelled by the 30s start timeout orphaned the child process
    and leaked its allocated port.
  - Stateless HTTP servers: FASTMCP_STATELESS_HTTP in env_file was ignored, and
    tool discovery was sent to the SSE endpoint (/messages/) instead of /mcp.
  - /health read a module registry that is never updated on restart.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services import server_manager as sm_module
from fluidmcp.cli.services.network_handle import parse_sse_jsonrpc_response
from fluidmcp.cli.services.package_launcher import _proxy_to_http_server
from fluidmcp.cli.services.server_manager import ServerManager


def _sse(*messages) -> str:
    return "".join(f"event: message\ndata: {json.dumps(m)}\n\n" for m in messages)


LOG_NOTIFICATION = {"jsonrpc": "2.0", "method": "notifications/message",
                    "params": {"level": "info", "data": "working"}}
PROGRESS_NOTIFICATION = {"jsonrpc": "2.0", "method": "notifications/progress",
                         "params": {"progressToken": 1, "progress": 50}}


@pytest.fixture
def server_manager():
    return ServerManager(InMemoryBackend())


class _FakeProcess:
    """Stand-in for subprocess.Popen — alive until killed."""

    def __init__(self):
        self.pid = 4242
        self.stdin = MagicMock()
        self.stdout = MagicMock()
        self.stderr = None
        self.returncode = None
        self.killed = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def terminate(self):
        self.kill()

    def wait(self, timeout=None):
        return self.returncode


def _write_server(root, env_text):
    server_dir = root / "servers" / "x"
    server_dir.mkdir(parents=True)
    (server_dir / "server.py").write_text("pass")
    (server_dir / ".env").write_text(env_text)
    return {
        "command": "python3",
        "args": ["servers/x/server.py"],
        "env": {},
        "working_dir": str(root),
        "install_path": str(root),
        "env_file": "servers/x/.env",
    }


# ── SSE response selection ──────────────────────────────────────────────────

class TestSseResponseSelection:
    def test_skips_notifications_before_result(self):
        body = _sse(LOG_NOTIFICATION, PROGRESS_NOTIFICATION,
                    {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}})
        assert parse_sse_jsonrpc_response(body, 7) == {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}

    def test_matches_request_id(self):
        body = _sse({"jsonrpc": "2.0", "id": "other", "result": {}},
                    {"jsonrpc": "2.0", "id": "mine", "error": {"code": -1, "message": "x"}})
        assert parse_sse_jsonrpc_response(body, "mine")["id"] == "mine"

    def test_only_notifications_raises(self):
        with pytest.raises(ValueError):
            parse_sse_jsonrpc_response(_sse(LOG_NOTIFICATION), 1)

    @pytest.mark.asyncio
    async def test_proxy_returns_tool_result_not_log_notification(self):
        """ctx.info()/report_progress() inside a tool must not replace the tool result."""
        result = {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "done"}]}}

        def handler(request):
            return httpx.Response(200, text=_sse(LOG_NOTIFICATION, result),
                                  headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response, _ = await _proxy_to_http_server(
                "http://upstream", {"jsonrpc": "2.0", "id": 3, "method": "tools/call"}, client=client
            )
        assert response == result


# ── env_file handling ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_env_file_survives_respawn_from_cached_config(tmp_path, server_manager):
    """restart_server() respawns from self.configs[id]; env_file must still be loaded."""
    config = _write_server(tmp_path, "ONGC_HR_CONN=postgresql://fake:fake@db.invalid/x\n")
    server_manager.configs["srv"] = config
    envs = []

    def fake_popen(cmd, **kwargs):
        envs.append(kwargs["env"])
        return _FakeProcess()

    with patch.object(sm_module.subprocess, "Popen", side_effect=fake_popen), \
         patch.object(sm_module, "initialize_mcp_server", return_value=True), \
         patch.object(ServerManager, "_discover_and_cache_tools", new=AsyncMock()):
        assert await server_manager._spawn_mcp_process("srv", server_manager.configs["srv"])
        assert await server_manager._spawn_mcp_process("srv", server_manager.configs["srv"])

    assert config.get("env_file") == "servers/x/.env"
    assert [e.get("ONGC_HR_CONN") for e in envs] == ["postgresql://fake:fake@db.invalid/x"] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize("env_file", ["servers/x/.env.prod", "servers/x"])
async def test_unloadable_env_file_refuses_to_start(tmp_path, server_manager, env_file):
    """A typo'd env_file (or a directory) must not start the server without its env."""
    config = _write_server(tmp_path, "TRANSPORT_TYPE=http\n")
    config["env_file"] = env_file

    with patch.object(sm_module.subprocess, "Popen") as popen:
        result = await server_manager._spawn_mcp_process("srv", config)

    assert result is None
    popen.assert_not_called()


@pytest.mark.asyncio
async def test_undecodable_env_file_refuses_to_start(tmp_path, server_manager):
    config = _write_server(tmp_path, "")
    (tmp_path / "servers" / "x" / ".env").write_bytes(b"KEY=\xff\xfe\xfa\n")

    with patch.object(sm_module.subprocess, "Popen") as popen:
        result = await server_manager._spawn_mcp_process("srv", config)

    assert result is None
    popen.assert_not_called()


# ── startup cancellation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancelled_http_startup_kills_child_and_releases_port(tmp_path, server_manager):
    """_start_server_unlocked's wait_for(30s) cancels the HTTP readiness wait; the
    half-started child must be killed and its port returned to the pool."""
    config = _write_server(tmp_path, "TRANSPORT_TYPE=http\n")
    proc = _FakeProcess()

    async def never_ready(*args, **kwargs):
        await asyncio.sleep(3600)

    with patch.object(sm_module.subprocess, "Popen", return_value=proc), \
         patch.object(ServerManager, "_handshake_http_subprocess", new=never_ready):
        task = asyncio.create_task(server_manager._spawn_mcp_process("srv", config))
        await asyncio.sleep(0.8)  # past the 0.5s post-spawn sleep, now waiting for HTTP
        assert server_manager._allocated_ports, "port should be allocated during startup"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert proc.killed
    assert server_manager._allocated_ports == set()


# ── stateless HTTP ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stateless_flag_read_from_env_file(tmp_path, server_manager):
    config = _write_server(tmp_path, "TRANSPORT_TYPE=http\nFASTMCP_STATELESS_HTTP=true\n")
    server_manager.configs["srv"] = config
    captured = {}

    async def fake_handshake(self, id, port, process, server_env=None):
        captured["server_env"] = server_env
        return None

    with patch.object(sm_module.subprocess, "Popen", return_value=_FakeProcess()), \
         patch.object(ServerManager, "_handshake_http_subprocess", new=fake_handshake):
        await server_manager._spawn_mcp_process("srv", config)

    assert captured["server_env"]["FASTMCP_STATELESS_HTTP"] == "true"


@pytest.mark.asyncio
async def test_stateless_http_tool_discovery_uses_mcp_endpoint(server_manager):
    """No session id (stateless) must still be treated as streamable-http, not SSE."""
    await server_manager.db.save_server_config({"id": "srv", "name": "srv"})
    seen = []

    def handler(request):
        seen.append(request.url.path)
        body = _sse({"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "echo"}]}})
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    real_client = httpx.AsyncClient
    with patch.object(sm_module.httpx, "AsyncClient",
                      side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler))):
        await server_manager._discover_and_cache_tools_network(
            "srv", "http://127.0.0.1:8500", session_id=None, transport="http"
        )

    assert seen == ["/mcp"]
    assert (await server_manager.db.get_server_config("srv"))["tools"] == [{"name": "echo"}]


# ── /health ─────────────────────────────────────────────────────────────────

def test_health_uses_live_server_manager_registry():
    """After a restart the ServerManager holds the new handle; the module registry
    still holds the dead original. /health must report the live state."""
    from fluidmcp.cli.services.run_servers import _add_health_endpoint

    dead, alive = MagicMock(), MagicMock()
    dead.poll.return_value = 3
    alive.poll.return_value = None

    app = FastAPI()
    app.state.server_manager = MagicMock(processes={"a": alive})
    _add_health_endpoint(app)

    with patch("fluidmcp.cli.services.run_servers._get_server_processes", return_value={"a": dead}):
        resp = TestClient(app).get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy", "servers": 1, "running_servers": 1}
