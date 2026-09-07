"""Regression test for env_file support in ServerManager._spawn_mcp_process.

Covers a real production bug: servers configured with an "env_file" key
(pointing to a .env-style file, as used by on-prem/ONGC deployments) need
that file's vars loaded and merged, and TRANSPORT_TYPE from that file must
promote config["transport"] so HTTP-transport servers get MCP_PORT injected.
This support existed on a divergent branch but was missing from `development`
until this fix — servers relying on env_file crashed with MCP_PORT=None.

The actual subprocess spawn + MCP handshake (stdio/http) is mocked out so
these tests exercise only the env_file-loading and transport-promotion logic
that changed, without needing a real MCP-protocol-speaking server process.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager


@pytest.fixture
def backend():
    return InMemoryBackend()


@pytest.fixture
def server_manager(backend):
    return ServerManager(backend)


class _FakeProcess:
    """Stand-in for subprocess.Popen — alive, does nothing."""
    pid = 12345
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = None

    def poll(self):
        return None

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def _capturing_popen(captured_env):
    def fake_popen(cmd_list, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return _FakeProcess()
    return fake_popen


@pytest.mark.asyncio
async def test_env_file_promotes_transport_and_injects_mcp_port(tmp_path, server_manager):
    env_file = tmp_path / ".env"
    env_file.write_text("TRANSPORT_TYPE=http\nCUSTOM_VAR=hello\n")
    (tmp_path / "server.py").write_text("pass")  # never actually executed, Popen is mocked

    config = {
        "command": "python3",
        "args": [str(tmp_path / "server.py")],
        "env": {},
        "working_dir": str(tmp_path),
        "install_path": str(tmp_path),
        "env_file": ".env",
    }

    captured_env = {}
    fake_handle = object()

    with patch("fluidmcp.cli.services.server_manager.subprocess.Popen", side_effect=_capturing_popen(captured_env)), \
         patch.object(ServerManager, "_handshake_http_subprocess", new=AsyncMock(return_value=fake_handle)):
        result = await server_manager._spawn_mcp_process("probe-server", config)

    assert result is fake_handle, "HTTP handshake path should have been taken and its handle returned"
    assert captured_env.get("MCP_PORT"), "MCP_PORT was not injected — transport was not promoted from env_file"
    assert int(captured_env["MCP_PORT"]) > 0
    assert captured_env.get("CUSTOM_VAR") == "hello", "env_file vars beyond TRANSPORT_TYPE were not merged into the subprocess env"

    # transport promotion should also be reflected back onto the config dict
    assert config["transport"] == "http"
    # env_file key should be consumed (matches original deploy_onprod behavior)
    assert "env_file" not in config


@pytest.mark.asyncio
async def test_no_env_file_key_is_unaffected(tmp_path, server_manager):
    """Servers without env_file must behave exactly as before (no transport promotion, no MCP_PORT)."""
    (tmp_path / "server.py").write_text("pass")

    config = {
        "command": "python3",
        "args": [str(tmp_path / "server.py")],
        "env": {},
        "working_dir": str(tmp_path),
        "install_path": str(tmp_path),
    }

    captured_env = {}

    with patch("fluidmcp.cli.services.server_manager.subprocess.Popen", side_effect=_capturing_popen(captured_env)), \
         patch("fluidmcp.cli.services.server_manager.initialize_mcp_server", return_value=True), \
         patch.object(ServerManager, "_discover_and_cache_tools", new=AsyncMock(return_value=None)):
        result = await server_manager._spawn_mcp_process("probe-server-stdio", config)

    assert result is not None
    assert "MCP_PORT" not in captured_env
    assert config.get("transport") is None


@pytest.mark.asyncio
async def test_env_file_outside_working_dir_is_rejected(tmp_path, server_manager):
    """Security: env_file must stay under install_path/working_dir — a path-traversal attempt is skipped, not followed."""
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "evil.env").write_text("TRANSPORT_TYPE=http\n")

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "server.py").write_text("pass")

    config = {
        "command": "python3",
        "args": [str(work_dir / "server.py")],
        "env": {},
        "working_dir": str(work_dir),
        "install_path": str(work_dir),
        "env_file": "../outside/evil.env",
    }

    captured_env = {}

    with patch("fluidmcp.cli.services.server_manager.subprocess.Popen", side_effect=_capturing_popen(captured_env)), \
         patch("fluidmcp.cli.services.server_manager.initialize_mcp_server", return_value=True), \
         patch.object(ServerManager, "_discover_and_cache_tools", new=AsyncMock(return_value=None)):
        result = await server_manager._spawn_mcp_process("probe-server-escape", config)

    assert result is not None
    assert "MCP_PORT" not in captured_env, "env_file outside install_path/working_dir must be skipped, not loaded"
    assert config.get("transport") is None
