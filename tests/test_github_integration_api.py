"""
Integration tests for POST /api/servers/from-github endpoint.

Tests cover:
- Missing X-GitHub-Token header → 400
- Missing required body fields → 400
- Duplicate server ID → 409
- Dangerous command in metadata → 400
- Single-server repo added successfully (test_before_save=False)
- Multi-server repo adds all servers
- server_name filter adds one server
- test_before_save=True runs manager lifecycle validation
"""

import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from fastapi.testclient import TestClient
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Minimal FastAPI app fixture
# ---------------------------------------------------------------------------

def _make_app(db_manager=None, server_manager=None):
    """Create a minimal FastAPI app with the management router mounted."""
    from fluidmcp.cli.api.management import router

    app = FastAPI()
    app.include_router(router, prefix="/api")

    # Attach fake app state
    if db_manager is None:
        db_manager = _make_db_manager()
    if server_manager is None:
        server_manager = _make_server_manager(db_manager)

    app.state.db_manager = db_manager
    app.state.server_manager = server_manager

    return app


def _make_db_manager():
    db = MagicMock()
    db.get_server_config = AsyncMock(return_value=None)
    db.save_server_config = AsyncMock(return_value=True)
    db.get_instance_state = AsyncMock(return_value=None)
    db.save_instance_state = AsyncMock(return_value=True)
    db.get_instance_env = AsyncMock(return_value={})
    db.db = None  # No real MongoDB
    return db


def _make_server_manager(db=None):
    from fluidmcp.cli.services.server_manager import ServerManager
    if db is None:
        db = _make_db_manager()
    manager = MagicMock(spec=ServerManager)
    manager.db = db
    manager.configs = {}
    manager.start_server = AsyncMock(return_value=True)
    manager.stop_server = AsyncMock(return_value=True)
    manager.get_server_status = AsyncMock(return_value={"state": "running"})
    return manager


# ---------------------------------------------------------------------------
# Shared metadata fixtures
# ---------------------------------------------------------------------------

SINGLE_SERVER_METADATA = {
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "env": {},
        }
    }
}

MULTI_SERVER_METADATA = {
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        },
        "memory": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
        },
    }
}

DANGEROUS_METADATA = {
    "mcpServers": {
        "evil": {
            "command": "rm",
            "args": ["-rf", "/"],
        }
    }
}


def _github_service_patch(metadata, clone_path=Path("/tmp/clone")):
    """Return a context-manager that patches GitHubService.build_server_configs."""
    from fluidmcp.cli.services.github_utils import GitHubService

    def _build(repo_path, token, base_server_id, branch="main", server_name=None,
               subdirectory=None, env=None, restart_policy="never", max_restarts=3,
               enabled=True, created_by=None):
        from fluidmcp.cli.services.server_builder import ServerBuilder
        from fluidmcp.cli.services.validators import validate_command_allowlist

        mcp_servers = metadata.get("mcpServers", {})
        if server_name:
            if server_name not in mcp_servers:
                raise ValueError(f"Server '{server_name}' not found")
            mcp_servers = {server_name: mcp_servers[server_name]}

        is_multi = len(mcp_servers) > 1
        configs = []
        for name, srv in mcp_servers.items():
            ok, err = validate_command_allowlist(srv.get("command", ""))
            if not ok:
                raise ValueError(f"Server '{name}': {err}")
            cfg = ServerBuilder.build_config(
                base_id=base_server_id, server_name=name, server_config=srv,
                clone_path=clone_path, repo_path=repo_path, branch=branch,
                env=env, restart_policy=restart_policy, max_restarts=max_restarts,
                enabled=enabled, is_multi_server=is_multi, created_by=created_by,
            )
            configs.append(cfg)
        return configs, clone_path

    # GitHubService is imported inside the endpoint function, so we patch
    # at the source module level.
    return patch(
        "fluidmcp.cli.services.github_utils.GitHubService.build_server_configs",
        side_effect=_build,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAddServerFromGitHubMissingHeader:
    def test_missing_github_token_header_returns_400(self):
        app = _make_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/servers/from-github",
                json={"github_repo": "owner/repo", "server_id": "test"},
            )
        assert resp.status_code == 400
        assert "X-GitHub-Token" in resp.json()["detail"]


class TestAddServerFromGitHubMissingFields:
    def _call(self, body):
        app = _make_app()
        with TestClient(app) as client:
            return client.post(
                "/api/servers/from-github",
                json=body,
                headers={"X-GitHub-Token": "ghp_testtoken"},
            )

    def test_missing_github_repo_returns_400(self):
        resp = self._call({"server_id": "test"})
        assert resp.status_code == 400
        assert "github_repo" in resp.json()["detail"]

    def test_missing_server_id_returns_400(self):
        resp = self._call({"github_repo": "owner/repo"})
        assert resp.status_code == 400
        assert "server_id" in resp.json()["detail"]


class TestAddServerFromGitHubSingleServer:
    def test_adds_single_server_successfully(self):
        app = _make_app()
        with _github_service_patch(SINGLE_SERVER_METADATA):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/servers/from-github",
                    json={
                        "github_repo": "owner/repo",
                        "server_id": "fs",
                        "test_before_save": False,
                    },
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"].startswith("Successfully added 1")
        assert len(data["servers"]) == 1
        assert data["servers"][0]["id"] == "fs"
        assert data["servers"][0]["status"] == "added"

    def test_server_stored_in_manager_configs(self):
        db = _make_db_manager()
        manager = _make_server_manager(db)
        app = _make_app(db_manager=db, server_manager=manager)

        with _github_service_patch(SINGLE_SERVER_METADATA):
            with TestClient(app) as client:
                client.post(
                    "/api/servers/from-github",
                    json={"github_repo": "owner/repo", "server_id": "fs", "test_before_save": False},
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert "fs" in manager.configs

    def test_server_saved_to_database(self):
        db = _make_db_manager()
        manager = _make_server_manager(db)
        app = _make_app(db_manager=db, server_manager=manager)

        with _github_service_patch(SINGLE_SERVER_METADATA):
            with TestClient(app) as client:
                client.post(
                    "/api/servers/from-github",
                    json={"github_repo": "owner/repo", "server_id": "fs", "test_before_save": False},
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        db.save_server_config.assert_called_once()


class TestAddServerFromGitHubMultiServer:
    def test_adds_all_servers(self):
        app = _make_app()
        with _github_service_patch(MULTI_SERVER_METADATA):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/servers/from-github",
                    json={"github_repo": "owner/repo", "server_id": "tools", "test_before_save": False},
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"].startswith("Successfully added 2")
        ids = {s["id"] for s in data["servers"]}
        assert "tools-filesystem" in ids
        assert "tools-memory" in ids

    def test_server_name_filter_adds_one(self):
        app = _make_app()
        with _github_service_patch(MULTI_SERVER_METADATA):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/servers/from-github",
                    json={
                        "github_repo": "owner/repo",
                        "server_id": "my-memory",
                        "server_name": "memory",
                        "test_before_save": False,
                    },
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["servers"]) == 1
        assert data["servers"][0]["id"] == "my-memory"


class TestAddServerFromGitHubDuplicateId:
    def test_duplicate_in_memory_returns_409(self):
        db = _make_db_manager()
        manager = _make_server_manager(db)
        manager.configs["fs"] = {"id": "fs"}  # Pre-existing entry
        app = _make_app(db_manager=db, server_manager=manager)

        with _github_service_patch(SINGLE_SERVER_METADATA):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/servers/from-github",
                    json={"github_repo": "owner/repo", "server_id": "fs", "test_before_save": False},
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert resp.status_code == 409

    def test_duplicate_in_database_returns_409(self):
        db = _make_db_manager()
        db.get_server_config = AsyncMock(return_value={"id": "fs"})  # Already in DB
        manager = _make_server_manager(db)
        app = _make_app(db_manager=db, server_manager=manager)

        with _github_service_patch(SINGLE_SERVER_METADATA):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/servers/from-github",
                    json={"github_repo": "owner/repo", "server_id": "fs", "test_before_save": False},
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert resp.status_code == 409


class TestAddServerFromGitHubDangerousCommand:
    def test_blocked_command_returns_400(self):
        app = _make_app()
        with _github_service_patch(DANGEROUS_METADATA):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/servers/from-github",
                    json={"github_repo": "owner/repo", "server_id": "evil", "test_before_save": False},
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert resp.status_code == 400
        assert "allowed" in resp.json()["detail"].lower()


class TestAddServerFromGitHubTestBeforeSave:
    def test_with_test_before_save_status_is_validated(self):
        db = _make_db_manager()
        manager = _make_server_manager(db)
        # Simulate the manager lifecycle: start succeeds, server is running
        manager.start_server = AsyncMock(return_value=True)
        manager.get_server_status = AsyncMock(return_value={"state": "running"})
        manager.stop_server = AsyncMock(return_value=True)
        app = _make_app(db_manager=db, server_manager=manager)

        with _github_service_patch(SINGLE_SERVER_METADATA), \
             patch("fluidmcp.cli.api.management.asyncio.sleep", new=AsyncMock()):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/servers/from-github",
                    json={"github_repo": "owner/repo", "server_id": "fs", "test_before_save": True},
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert resp.status_code == 200
        assert resp.json()["servers"][0]["status"] == "validated"

    def test_validation_failure_returns_400(self):
        db = _make_db_manager()
        manager = _make_server_manager(db)
        # Simulate server crashing during validation
        manager.start_server = AsyncMock(return_value=True)
        manager.get_server_status = AsyncMock(return_value={"state": "failed"})
        manager.stop_server = AsyncMock(return_value=True)
        app = _make_app(db_manager=db, server_manager=manager)

        with _github_service_patch(SINGLE_SERVER_METADATA), \
             patch("fluidmcp.cli.api.management.asyncio.sleep", new=AsyncMock()):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/servers/from-github",
                    json={"github_repo": "owner/repo", "server_id": "fs", "test_before_save": True},
                    headers={"X-GitHub-Token": "ghp_testtoken"},
                )

        assert resp.status_code == 400
        assert "crashed" in resp.json()["detail"].lower()
