"""
Tests for the optional explicit per-key ``required`` flag on env values.

PR 4 of the env-var startup UX spec (docs/specs/env_var_startup_ux.md):
POST/PUT /api/servers accept env values as ``str | {value, required?, description?}``
and GET /api/servers/{id}/instance/env reports the stored flag instead of a
hardcoded ``True``. Keys without a flag behave exactly as before.
"""

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


def _body(env):
    return {"id": "srv", "name": "Srv", "command": "uv", "args": ["run", "s.py"], "env": env}


class TestRequiredFlag:
    def test_rich_env_is_flattened_and_flag_stored(self, manager):
        with TestClient(_make_app(manager)) as client:
            resp = client.post("/api/servers", json=_body({
                "API_KEY": {"value": "your_key_here", "required": True, "description": "Provider key"},
                "DEBUG": {"value": "false", "required": False},
                "PLAIN": "x",
            }))
            assert resp.status_code == 200, resp.text
            assert resp.json()["unfilled_env"] == ["API_KEY"]

            cfg = manager.configs["srv"]
            assert cfg["env"] == {"API_KEY": "your_key_here", "DEBUG": "false", "PLAIN": "x"}
            assert cfg["env_metadata"] == {
                "API_KEY": {"required": True, "description": "Provider key"},
                "DEBUG": {"required": False},
            }

    def test_instance_env_reflects_stored_flag(self, manager):
        with TestClient(_make_app(manager)) as client:
            client.post("/api/servers", json=_body({
                "API_KEY": {"value": "", "required": True, "description": "Provider key"},
                "DEBUG": {"value": "false", "required": False},
                "PLAIN": "x",
            }))
            meta = client.get("/api/servers/srv/instance/env").json()
            assert meta["API_KEY"]["required"] is True
            assert meta["API_KEY"]["description"] == "Provider key"
            assert meta["DEBUG"]["required"] is False
            # No flag declared -> unchanged legacy behavior
            assert meta["PLAIN"]["required"] is True

    def test_plain_env_creates_no_metadata(self, manager):
        with TestClient(_make_app(manager)) as client:
            client.post("/api/servers", json=_body({"A": "1"}))
            assert "env_metadata" not in manager.configs["srv"]

    @pytest.mark.parametrize("bad", [
        {"K": {"value": 1}},
        {"K": {"value": "v", "required": "yes"}},
        {"K": {"value": "v", "description": 5}},
    ])
    def test_invalid_rich_entries_rejected(self, manager, bad):
        with TestClient(_make_app(manager)) as client:
            resp = client.post("/api/servers", json=_body(bad))
            assert resp.status_code == 400

    def test_update_replaces_metadata(self, manager):
        with TestClient(_make_app(manager)) as client:
            client.post("/api/servers", json=_body({"K": {"value": "v", "required": True}}))
            resp = client.put("/api/servers/srv", json=_body({"K": "v"}))
            assert resp.status_code == 200, resp.text
            assert "env_metadata" not in manager.configs["srv"]
