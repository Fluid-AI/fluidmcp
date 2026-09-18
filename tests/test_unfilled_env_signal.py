"""
Tests for the "unfilled_env" warning signal added to POST /api/servers,
POST /api/servers/{id}/start, and POST /api/servers/from-github.

This is PR 2 of the env-var startup UX spec (docs/specs/env_var_startup_ux.md):
surface the same placeholder-detection signal from PR 1 at add/start time,
before a crash ever happens, without blocking the request either way.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager


def _make_app(manager: ServerManager) -> FastAPI:
    from fluidmcp.cli.api.management import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.server_manager = manager
    app.state.db_manager = manager.db
    return app


@pytest.fixture
def manager():
    return ServerManager(InMemoryBackend())


class TestAddServerUnfilledEnv:
    def test_reports_unfilled_placeholder_and_empty_values(self, manager):
        app = _make_app(manager)
        with TestClient(app) as client:
            resp = client.post(
                "/api/servers",
                json={
                    "id": "image-enhancement-mcp",
                    "name": "Image Enhancement",
                    "command": "uv",
                    "args": ["run", "server.py"],
                    "env": {
                        "REPLICATE_API_TOKEN": "your_replicate_api_token_here",
                        "GEMINI_API_KEY": "your_gemini_api_key_here",
                        "DEBUG": "false",
                    },
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert set(data["unfilled_env"]) == {"REPLICATE_API_TOKEN", "GEMINI_API_KEY"}

    def test_no_warning_when_all_env_filled(self, manager):
        app = _make_app(manager)
        with TestClient(app) as client:
            resp = client.post(
                "/api/servers",
                json={
                    "id": "weather",
                    "name": "Weather",
                    "command": "npx",
                    "args": ["-y", "weather-mcp"],
                    "env": {"OPENWEATHER_API_KEY": "sk-real-looking-value-123"},
                },
            )

        assert resp.status_code == 200
        assert resp.json()["unfilled_env"] == []

    def test_no_env_at_all_reports_empty_list(self, manager):
        app = _make_app(manager)
        with TestClient(app) as client:
            resp = client.post(
                "/api/servers",
                json={"id": "filesystem", "name": "Filesystem", "command": "npx", "args": []},
            )

        assert resp.status_code == 200
        assert resp.json()["unfilled_env"] == []

    def test_server_is_still_added_despite_unfilled_env(self, manager):
        """Non-blocking: the point of this signal is to warn, not refuse."""
        app = _make_app(manager)
        with TestClient(app) as client:
            resp = client.post(
                "/api/servers",
                json={
                    "id": "incomplete",
                    "name": "Incomplete",
                    "command": "npx",
                    "args": [],
                    "env": {"API_KEY": ""},
                },
            )

        assert resp.status_code == 200
        assert "incomplete" in manager.configs


class TestStartServerUnfilledEnv:
    def test_reports_unfilled_env_on_start_without_blocking(self, manager):
        app = _make_app(manager)
        with TestClient(app) as client:
            client.post(
                "/api/servers",
                json={
                    "id": "image-enhancement-mcp",
                    "name": "Image Enhancement",
                    "command": "uv",
                    "args": ["run", "server.py"],
                    "env": {"REPLICATE_API_TOKEN": "your_replicate_api_token_here"},
                },
            )

            # Avoid actually spawning a subprocess — only the reported signal
            # is under test here, not the spawn/start lifecycle itself.
            with patch.object(ServerManager, "start_server", new=AsyncMock(return_value=True)):
                resp = client.post("/api/servers/image-enhancement-mcp/start")

        assert resp.status_code == 200
        assert resp.json()["unfilled_env"] == ["REPLICATE_API_TOKEN"]


class TestAddServerFromGithubUnfilledEnv:
    def _github_service_patch(self, metadata, clone_path=Path("/tmp/clone")):
        from fluidmcp.cli.services.github_utils import GitHubService

        def _build(repo_path, token, base_server_id, branch="main", server_name=None,
                   subdirectory=None, env=None, restart_policy="never", max_restarts=3,
                   enabled=True, created_by=None):
            from fluidmcp.cli.services.server_builder import ServerBuilder

            mcp_servers = metadata.get("mcpServers", {})
            is_multi = len(mcp_servers) > 1
            configs = [
                ServerBuilder.build_config(
                    base_id=base_server_id, server_name=name, server_config=srv,
                    clone_path=clone_path, repo_path=repo_path, branch=branch,
                    env=env, restart_policy=restart_policy, max_restarts=max_restarts,
                    enabled=enabled, is_multi_server=is_multi, created_by=created_by,
                )
                for name, srv in mcp_servers.items()
            ]
            return configs, clone_path

        return patch(
            "fluidmcp.cli.services.github_utils.GitHubService.build_server_configs",
            side_effect=_build,
        )

    def test_reports_unfilled_env_from_cloned_metadata(self, manager):
        metadata = {
            "mcpServers": {
                "image-enhancement": {
                    "command": "uv",
                    "args": ["run", "server.py"],
                    "env": {
                        "REPLICATE_API_TOKEN": "your_replicate_api_token_here",
                        "GEMINI_API_KEY": "your_gemini_api_key_here",
                    },
                }
            }
        }
        app = _make_app(manager)
        with self._github_service_patch(metadata):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/servers/from-github",
                    json={
                        "github_repo": "owner/private-repo",
                        "server_id": "image-enhancement-mcp",
                        "test_before_save": False,
                    },
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["servers"]) == 1
        assert set(data["servers"][0]["unfilled_env"]) == {"REPLICATE_API_TOKEN", "GEMINI_API_KEY"}
