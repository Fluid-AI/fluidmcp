"""Env values (API keys etc.) must never be returned by the management API.

GET responses mask every value as "****". Clients that edit a config send the
masked values back, so PUT /api/servers/{id} restores the stored value for any
key still set to "****".
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.api.management import router
from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.server_manager import ServerManager
from fluidmcp.cli.utils.env_utils import (
    ENV_VALUE_MASK,
    mask_env_values,
    restore_masked_env_values,
)

SECRET = "sk_live_TESTSECRET_1234567890"


class TestMaskEnvValues:
    def test_masks_values_keeps_keys(self):
        assert mask_env_values({"API_KEY": SECRET, "DEBUG": "true"}) == {"API_KEY": "****", "DEBUG": "****"}

    def test_empty_values_stay_empty(self):
        assert mask_env_values({"API_KEY": ""}) == {"API_KEY": ""}

    def test_structured_format(self):
        env = {"API_KEY": {"value": SECRET, "description": "Key", "required": True}}
        assert mask_env_values(env) == {"API_KEY": {"value": "****", "description": "Key", "required": True}}

    def test_does_not_modify_input(self):
        env = {"API_KEY": SECRET}
        mask_env_values(env)
        assert env == {"API_KEY": SECRET}

    def test_non_dict_passes_through(self):
        assert mask_env_values(None) is None


class TestRestoreMaskedEnvValues:
    def test_masked_value_restored_from_stored(self):
        assert restore_masked_env_values({"API_KEY": ENV_VALUE_MASK}, {"API_KEY": SECRET}) == {"API_KEY": SECRET}

    def test_changed_value_kept(self):
        assert restore_masked_env_values({"API_KEY": "new-key"}, {"API_KEY": SECRET}) == {"API_KEY": "new-key"}

    def test_removed_key_stays_removed(self):
        assert restore_masked_env_values({}, {"API_KEY": SECRET}) == {}

    def test_masked_value_without_stored_value_kept(self):
        assert restore_masked_env_values({"NEW": ENV_VALUE_MASK}, {}) == {"NEW": ENV_VALUE_MASK}

    def test_structured_format(self):
        stored = {"API_KEY": {"value": SECRET}}
        assert restore_masked_env_values({"API_KEY": {"value": ENV_VALUE_MASK}}, stored) == stored


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
    backend = InMemoryBackend()
    manager = ServerManager(backend)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.server_manager = manager
    app.state.db_manager = backend
    client = TestClient(app)

    resp = client.post("/api/servers", json={
        "id": "weather",
        "name": "Weather",
        "command": "npx",
        "args": ["-y", "weather-mcp"],
        "env": {"WEATHER_API_KEY": SECRET, "REGION": "eu"},
    })
    assert resp.status_code == 200
    return client, manager


class TestManagementApiMasking:
    def test_list_servers_masks_env(self, setup):
        client, _ = setup
        resp = client.get("/api/servers")
        assert SECRET not in resp.text
        assert resp.json()["servers"][0]["config"]["env"] == {"WEATHER_API_KEY": "****", "REGION": "****"}

    def test_get_server_masks_env(self, setup):
        client, _ = setup
        resp = client.get("/api/servers/weather")
        assert SECRET not in resp.text
        assert resp.json()["config"]["env"]["WEATHER_API_KEY"] == "****"

    def test_update_with_masked_values_keeps_secret(self, setup):
        """The edit form and the Disable button send back what GET returned."""
        client, manager = setup
        resp = client.put("/api/servers/weather", json={
            "name": "Weather",
            "command": "npx",
            "args": ["-y", "weather-mcp"],
            "env": {"WEATHER_API_KEY": "****", "REGION": "us"},
            "enabled": False,
        })
        assert resp.status_code == 200
        assert SECRET not in resp.text
        assert manager.configs["weather"]["env"] == {"WEATHER_API_KEY": SECRET, "REGION": "us"}

    def test_update_with_new_value_replaces_secret(self, setup):
        client, manager = setup
        client.put("/api/servers/weather", json={
            "name": "Weather",
            "command": "npx",
            "env": {"WEATHER_API_KEY": "sk_live_ROTATED_0987654321"},
        })
        assert manager.configs["weather"]["env"] == {"WEATHER_API_KEY": "sk_live_ROTATED_0987654321"}
