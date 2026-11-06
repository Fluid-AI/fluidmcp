"""
Tests for POST /api/llm/models/{id}/stop and /start.

Both endpoints previously called an undefined get_db_manager() and returned 500
on every call (stop did so after the process had already been stopped).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fluidmcp.cli.api.management import router
from fluidmcp.cli.services import llm_provider_registry


@pytest.fixture(autouse=True)
def _insecure_mode(monkeypatch):
    monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)


def _client(db_manager=None):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    if db_manager is not None:
        app.state.db_manager = db_manager
    return TestClient(app)


def _db(model_doc=None):
    db = MagicMock()
    db.update_llm_model = AsyncMock(return_value=True)
    db.get_llm_model = AsyncMock(return_value=model_doc)
    return db


def _running_process():
    process = MagicMock()
    process.is_running.return_value = True
    return process


class TestStopLLMModel:

    def test_graceful_stop_persists_state(self):
        process = _running_process()
        db = _db()

        with patch("fluidmcp.cli.api.management.get_llm_processes", return_value={"m1": process}):
            resp = _client(db).post("/api/llm/models/m1/stop")

        assert resp.status_code == 200
        assert resp.json()["persisted"] is True
        process.stop.assert_called_once()
        process.force_kill.assert_not_called()
        model_id, updates = db.update_llm_model.await_args.args
        assert model_id == "m1"
        assert updates["state"] == "stopped"
        assert updates["stop_method"] == "graceful"

    def test_force_stop(self):
        process = _running_process()
        db = _db()

        with patch("fluidmcp.cli.api.management.get_llm_processes", return_value={"m1": process}):
            resp = _client(db).post("/api/llm/models/m1/stop?force=true")

        assert resp.status_code == 200
        process.force_kill.assert_called_once()
        assert db.update_llm_model.await_args.args[1]["stop_method"] == "force_killed"

    def test_stop_without_persistence_still_succeeds(self):
        process = _running_process()

        with patch("fluidmcp.cli.api.management.get_llm_processes", return_value={"m1": process}):
            resp = _client().post("/api/llm/models/m1/stop")

        assert resp.status_code == 200
        assert resp.json()["persisted"] is False
        process.stop.assert_called_once()

    def test_unknown_model_404(self):
        with patch("fluidmcp.cli.api.management.get_llm_processes", return_value={}):
            resp = _client(_db()).post("/api/llm/models/ghost/stop")

        assert resp.status_code == 404


class TestStartLLMModel:

    VLLM_DOC = {
        "model_id": "m1",
        "type": "vllm",
        "state": "stopped",
        "command": "vllm",
        "args": ["serve", "facebook/opt-125m"],
        "endpoints": {"base_url": "http://localhost:8001/v1"},
    }

    def test_start_launches_registers_and_persists(self):
        db = _db(dict(self.VLLM_DOC))
        processes = {}
        launched = MagicMock()

        with patch("fluidmcp.cli.services.run_servers.get_llm_processes", return_value=processes), \
                patch("fluidmcp.cli.services.llm_launcher.launch_single_llm_model",
                      return_value=launched) as launch, \
                patch.dict(llm_provider_registry._llm_models_config, clear=False):
            resp = _client(db).post("/api/llm/models/m1/start")
            registered_config = llm_provider_registry._llm_models_config.get("m1")

        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert resp.json()["persisted"] is True
        model_id, model_config = launch.call_args.args
        assert model_id == "m1"
        # DB bookkeeping fields are stripped before launch
        assert "type" not in model_config and "state" not in model_config
        assert model_config["command"] == "vllm"
        assert processes["m1"] is launched
        assert registered_config == model_config
        assert db.update_llm_model.await_args.args[1]["state"] == "running"

    def test_start_without_persistence_500(self):
        with patch("fluidmcp.cli.services.run_servers.get_llm_processes", return_value={}):
            resp = _client().post("/api/llm/models/m1/start")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Database not available"

    def test_start_unsupported_type_400(self):
        db = _db({"model_id": "m1", "type": "replicate"})

        with patch("fluidmcp.cli.services.run_servers.get_llm_processes", return_value={}):
            resp = _client(db).post("/api/llm/models/m1/start")

        assert resp.status_code == 400

    def test_start_unknown_model_404(self):
        with patch("fluidmcp.cli.services.run_servers.get_llm_processes", return_value={}):
            resp = _client(_db(None)).post("/api/llm/models/ghost/start")

        assert resp.status_code == 404
