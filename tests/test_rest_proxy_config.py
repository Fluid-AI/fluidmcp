"""Tests for restServers in config files, `fmcp validate` and `fmcp run` wiring."""
import importlib
import json
from unittest.mock import patch

import httpx
import pytest

from fluidmcp.cli.services import rest_proxy
from fluidmcp.cli.services.config_resolver import (
    RestServersConfigError,
    ServerConfig,
    resolve_from_file,
)
from fluidmcp.cli.services.s3_utils import validate_metadata_config

# services/__init__.py re-exports the run_servers function under the module's name.
run_servers_module = importlib.import_module("fluidmcp.cli.services.run_servers")

GUPSHUP = {"type": "rest-proxy", "target-rest-endpoint": "media.gupshup.com"}


def write_config(tmp_path, config):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path


def test_metadata_config_accepts_rest_only_section():
    assert validate_metadata_config({"restServers": {"chat": GUPSHUP}}, "test") is True
    assert validate_metadata_config({"restServers": []}, "test") is False
    assert validate_metadata_config({"other": {}}, "test") is False


def test_resolve_from_file_rest_only(tmp_path):
    config = resolve_from_file(str(write_config(tmp_path, {"restServers": {"gupshup-chat": GUPSHUP}})))
    assert config.rest_servers == {"gupshup-chat": GUPSHUP}
    assert config.servers == {}


def test_resolve_from_file_alongside_mcp_servers(tmp_path):
    path = write_config(tmp_path, {
        "mcpServers": {"weather": {"command": "python3", "args": ["-c", "pass"]}},
        "restServers": {"gupshup-chat": GUPSHUP},
    })
    config = resolve_from_file(str(path))
    assert list(config.servers) == ["weather"]
    assert list(config.rest_servers) == ["gupshup-chat"]


def test_resolve_from_file_without_rest_servers_is_unchanged(tmp_path):
    path = write_config(tmp_path, {"mcpServers": {"weather": {"command": "python3"}}})
    assert resolve_from_file(str(path)).rest_servers == {}


def test_resolve_from_file_reports_every_rest_error(tmp_path):
    path = write_config(tmp_path, {
        "mcpServers": {"weather": {"command": "python3"}},
        "restServers": {
            "weather": GUPSHUP,
            "api": GUPSHUP,
            "bad": {"type": "rest-proxy", "target-rest-endpoint": "ftp://x"},
        },
    })
    with pytest.raises(RestServersConfigError) as exc:
        resolve_from_file(str(path))
    errors = exc.value.errors
    assert len(errors) == 3
    assert any("'weather'" in e and "MCP server" in e for e in errors)
    assert any("'api'" in e and "reserved" in e for e in errors)
    assert any("'bad'" in e for e in errors)
    assert isinstance(exc.value, ValueError)


def test_validate_command_lists_rest_errors(tmp_path, capsys):
    from fluidmcp.cli.cli import validate_command

    path = write_config(tmp_path, {"restServers": {"api": GUPSHUP, "ok": GUPSHUP}})
    args = type("Args", (), {"package": str(path), "file": True, "s3": False, "master": False})()
    with pytest.raises(SystemExit) as exc:
        validate_command(args)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "REST server 'api': name is reserved" in out


def test_validate_command_lists_rest_proxies(tmp_path, capsys):
    from fluidmcp.cli.cli import validate_command

    path = write_config(tmp_path, {"restServers": {"gupshup-chat": GUPSHUP}})
    args = type("Args", (), {"package": str(path), "file": True, "s3": False, "master": False})()
    with pytest.raises(SystemExit) as exc:
        validate_command(args)
    assert exc.value.code == 0
    assert "gupshup-chat → https://media.gupshup.com" in capsys.readouterr().out


# ── fmcp run wiring ─────────────────────────────────────────────────────────

def build_run_app(config: ServerConfig):
    """Run run_servers up to the point it would start uvicorn, and return the app."""
    captured = {}
    with patch.object(run_servers_module, "_start_server", lambda app, port, force_reload: captured.setdefault("app", app)):
        run_servers_module.run_servers(config, start_server=True)
    return captured.get("app")


@pytest.fixture
def upstream(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={"X-Upstream": "1"}, stream=httpx.ByteStream(b"from-upstream"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.headers.clear()

    async def get_client():
        return client

    monkeypatch.setattr(rest_proxy, "get_client", get_client)
    monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
    monkeypatch.delenv("MCP_ROOT_PATH", raising=False)
    return requests


async def test_run_with_only_rest_servers_serves_proxy_and_health(upstream):
    app = build_run_app(ServerConfig(rest_servers={"gupshup-chat": GUPSHUP}, source_type="file"))
    assert app is not None, "run_servers returned early for a REST-only config"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
        proxied = await c.post("/gupshup-chat/wa/api/v1/msg?x=1", content=b"payload")
        health = await c.get("/health")

    assert proxied.status_code == 200 and proxied.content == b"from-upstream"
    assert str(upstream[0].url) == "https://media.gupshup.com/wa/api/v1/msg?x=1"
    assert health.status_code == 200
    assert health.json()["status"] == "healthy" and health.json()["rest_servers"] == 1
    assert app.state.rest_proxy_registry.names() == ["gupshup-chat"]


def test_run_with_nothing_configured_still_returns_early():
    assert build_run_app(ServerConfig(source_type="file")) is None


async def test_health_still_degraded_when_mcp_servers_are_down(upstream):
    app = build_run_app(ServerConfig(rest_servers={"gupshup-chat": GUPSHUP}, source_type="file"))

    class Dead:
        def poll(self):
            return 1

    with patch.object(run_servers_module, "_get_server_processes", return_value={"weather": Dead()}):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
            health = await c.get("/health")
    assert health.status_code == 503 and health.json()["rest_servers"] == 1


async def test_health_degraded_when_configured_mcp_servers_never_started(upstream):
    # MCP servers that fail to launch are never registered as processes.
    config = ServerConfig(
        servers={"weather": {"command": "python3", "install_path": "/nonexistent"}},
        rest_servers={"gupshup-chat": GUPSHUP}, source_type="file",
    )
    app = build_run_app(config)
    with patch.object(run_servers_module, "_get_server_processes", return_value={}):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
            health = await c.get("/health")
    assert health.status_code == 503 and health.json()["status"] == "degraded"


def test_rest_errors_reported_before_github_clone(tmp_path):
    path = write_config(tmp_path, {
        "mcpServers": {"repo": {"github_repo": "owner/repo"}},
        "restServers": {"api": GUPSHUP},
    })
    with patch("fluidmcp.cli.services.config_resolver._handle_github_server") as clone:
        with pytest.raises(RestServersConfigError):
            resolve_from_file(str(path))
    clone.assert_not_called()
