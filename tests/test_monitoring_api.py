"""Integration tests for the monitoring HTTP API.

Exercises the real FastAPI app with a real ServerManager over the in-memory
backend, so the endpoint contracts documented in
docs/MONITORING_INTEGRATION_GUIDE.md are verified against actual responses
rather than against the doc.
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from fluidmcp.cli.models.events import EventType
from fluidmcp.cli.repositories.memory import InMemoryBackend
from fluidmcp.cli.server import create_app
from fluidmcp.cli.services.event_bus import get_event_bus
from fluidmcp.cli.services.server_manager import MCPHealthMonitor, ServerManager
from fluidmcp.cli.services.tool_error_tracker import get_tool_error_tracker


@pytest.fixture
async def app_client(monkeypatch):
    """A running app with two registered servers, neither actually spawned."""
    monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
    monkeypatch.delenv("FMCP_BEARER_TOKEN", raising=False)

    backend = InMemoryBackend()
    await backend.connect()

    manager = ServerManager(backend)
    monitor = MCPHealthMonitor(manager, check_interval=3600)
    manager._health_monitor = monitor

    for server_id, name in (("sql", "SQL MCP"), ("files", "Filesystem MCP")):
        config = {
            "id": server_id,
            "name": name,
            "command": "python3",
            "args": ["-c", "pass"],
            "env": {},
            "enabled": True,
        }
        await backend.save_server_config(config)
        manager.configs[server_id] = config

    app = await create_app(
        db_manager=backend, server_manager=manager, secure_mode=False, token=None
    )

    bus = get_event_bus()
    bus.set_db(backend)
    get_tool_error_tracker().reset("sql")
    get_tool_error_tracker().reset("files")
    manager.config_issues.clear()

    with TestClient(app) as client:
        yield client, manager, backend, bus


class TestFleetHealth:
    @pytest.mark.asyncio
    async def test_returns_boot_identity_and_summary(self, app_client):
        client, _, _, _ = app_client
        response = client.get("/api/monitoring/health")
        assert response.status_code == 200
        body = response.json()

        # Boot identity — the fields a consumer keys its cursor on.
        for field in ("gateway_id", "boot_id", "boot_count", "generated_at"):
            assert field in body, f"missing {field}"

        assert body["summary"]["total"] == 2
        assert len(body["servers"]) == 2
        assert {s["id"] for s in body["servers"]} == {"sql", "files"}

    @pytest.mark.asyncio
    async def test_every_server_carries_the_documented_fields(self, app_client):
        client, _, _, _ = app_client
        body = client.get("/api/monitoring/health").json()
        for server in body["servers"]:
            for field in (
                "id", "name", "state", "process_state", "restart_count",
                "stability", "error_rate_5m", "failing_tools", "config_issues",
            ):
                assert field in server, f"{server['id']} missing {field}"

    @pytest.mark.asyncio
    async def test_failing_tool_surfaces_in_rollup(self, app_client):
        """Scenario: one endpoint starts erroring inside a healthy server."""
        client, _, _, _ = app_client
        tracker = get_tool_error_tracker()
        for _ in range(30):
            tracker.record("sql", "list_tables", "success")
        for _ in range(12):
            tracker.record("sql", "execute_query", "error", "ECONNREFUSED 10.0.0.5:1433")

        body = client.get("/api/monitoring/health").json()
        sql = next(s for s in body["servers"] if s["id"] == "sql")

        assert sql["failing_tools"], "a broken tool must be listed"
        assert sql["failing_tools"][0]["tool"] == "execute_query"
        assert sql["failure_category"] == "db_connection_refused"
        assert sql["failure_owner"] == "customer"
        # Server-wide rate stays low — proving the per-tool arm is what caught it.
        assert sql["error_rate_5m"] < 0.5

    @pytest.mark.asyncio
    async def test_misconfigured_server_that_never_started_reads_config_error(
        self, app_client
    ):
        """A registered server that failed to start due to config is not "not_found".

        Found against a real MCP: IFS could not start because its connection
        string was unset, and the rollup reported `not_found` — which reads as
        "unknown server" and tells an operator nothing actionable.
        """
        client, manager, _, _ = app_client
        manager.config_issues["sql"] = {
            "missing_env": ["IFS_MSSQL_CONNECTION_STRING"],
            "placeholder_env": [],
            "unresolved_env": [],
            "errors": [{"key": "IFS_MSSQL_CONNECTION_STRING",
                        "problem": "required but not set"}],
            "remediation": "Set IFS_MSSQL_CONNECTION_STRING",
        }
        body = client.get("/api/monitoring/health").json()
        sql = next(s for s in body["servers"] if s["id"] == "sql")

        assert sql["state"] == "config_error"
        assert sql["process_state"] != "config_error", (
            "process_state must stay raw so a consumer can still see the "
            "underlying process state"
        )
        assert body["summary"]["config_error"] >= 1

    @pytest.mark.asyncio
    async def test_registered_but_never_started_reads_stopped_not_not_found(
        self, app_client
    ):
        """A configured server with no instance record has not "vanished"."""
        client, _, _, _ = app_client
        body = client.get("/api/monitoring/health").json()
        for server in body["servers"]:
            assert server["state"] != "not_found", (
                f"{server['id']} reports not_found despite being registered"
            )

    @pytest.mark.asyncio
    async def test_config_issues_surface_in_rollup(self, app_client):
        """Scenario: an MCP is missing credentials."""
        client, manager, _, _ = app_client
        manager.config_issues["sql"] = {
            "missing_env": ["DB_PASSWORD"],
            "placeholder_env": [],
            "unresolved_env": [],
            "errors": [{"key": "DB_PASSWORD", "problem": "required but not set"}],
            "remediation": "Set DB_PASSWORD",
        }
        body = client.get("/api/monitoring/health").json()
        sql = next(s for s in body["servers"] if s["id"] == "sql")
        assert sql["config_issues"]["missing_env"] == ["DB_PASSWORD"]
        assert sql["failure_owner"] == "customer"


class TestGatewayEndpoint:
    @pytest.mark.asyncio
    async def test_reports_boot_identity_and_resources(self, app_client):
        client, _, _, _ = app_client
        body = client.get("/api/monitoring/gateway").json()
        assert body["boot_id"].startswith("boot_")
        assert "event_loop_lag_ms" in body["resources"]
        assert "config" in body
        assert "event_bus" in body
        assert body["servers_managed"] == 0

    @pytest.mark.asyncio
    async def test_health_exposes_config_errors_without_auth(self, monkeypatch):
        """The redeploy case: secure mode on, token missing.

        Must be readable unauthenticated — if the token is what is broken, a
        monitoring system cannot authenticate to discover that.
        """
        monkeypatch.setenv("FMCP_SECURE_MODE", "true")
        monkeypatch.delenv("FMCP_BEARER_TOKEN", raising=False)

        backend = InMemoryBackend()
        await backend.connect()
        manager = ServerManager(backend)
        app = await create_app(
            db_manager=backend, server_manager=manager, secure_mode=False, token=None
        )
        with TestClient(app) as client:
            response = client.get("/health")  # no Authorization header
            assert response.status_code == 200
            body = response.json()
            assert body["config"]["valid"] is False
            assert any(e["key"] == "FMCP_BEARER_TOKEN" for e in body["config"]["errors"])
            assert body["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_readiness_returns_503_when_misconfigured(self, monkeypatch):
        monkeypatch.setenv("FMCP_SECURE_MODE", "true")
        monkeypatch.delenv("FMCP_BEARER_TOKEN", raising=False)

        backend = InMemoryBackend()
        await backend.connect()
        manager = ServerManager(backend)
        app = await create_app(
            db_manager=backend, server_manager=manager, secure_mode=False, token=None
        )
        with TestClient(app) as client:
            response = client.get("/health/ready")
            assert response.status_code == 503
            assert response.json()["ready"] is False
            # Liveness still answers 200 — a broken container must be
            # distinguishable from a dead one.
            assert client.get("/health").status_code == 200


class TestEventFeed:
    @pytest.mark.asyncio
    async def test_cursor_semantics(self, app_client):
        client, _, _, bus = app_client
        for i in range(5):
            bus.emit(EventType.SERVER_CRASHED, server_id="sql", exit_code=137, n=i)

        body = client.get("/api/monitoring/events").json()
        assert body["returned"] >= 5
        seqs = [e["seq"] for e in body["events"]]
        assert seqs == sorted(seqs), "events must be ordered by seq ascending"

        cursor = seqs[-1]
        assert client.get(f"/api/monitoring/events?since={cursor}").json()["returned"] == 0

        bus.emit(EventType.SERVER_STARTED, server_id="sql")
        after = client.get(f"/api/monitoring/events?since={cursor}").json()
        assert after["returned"] == 1
        assert after["events"][0]["seq"] == cursor + 1

    @pytest.mark.asyncio
    async def test_severity_filter(self, app_client):
        client, _, _, bus = app_client
        bus.emit(EventType.SERVER_STARTED, server_id="a")
        bus.emit(EventType.SERVER_CRASHED, server_id="a")
        critical = client.get("/api/monitoring/events?severity=critical").json()
        assert all(e["severity"] == "critical" for e in critical["events"])

    @pytest.mark.asyncio
    async def test_server_filter(self, app_client):
        client, _, _, bus = app_client
        bus.emit(EventType.SERVER_CRASHED, server_id="sql")
        bus.emit(EventType.SERVER_CRASHED, server_id="files")
        body = client.get("/api/monitoring/events?server_id=sql").json()
        assert all(e["server_id"] == "sql" for e in body["events"])

    @pytest.mark.asyncio
    async def test_events_carry_boot_id_for_cursor_scoping(self, app_client):
        client, _, _, bus = app_client
        bus.emit(EventType.SERVER_CRASHED, server_id="sql")
        body = client.get("/api/monitoring/events").json()
        assert all(e["boot_id"] == body["boot_id"] for e in body["events"])

    @pytest.mark.asyncio
    async def test_limit_is_enforced(self, app_client):
        client, _, _, bus = app_client
        for i in range(30):
            bus.emit(EventType.SERVER_STARTED, server_id=f"s{i}")
        assert client.get("/api/monitoring/events?limit=10").json()["returned"] == 10
        assert client.get("/api/monitoring/events?limit=9999").status_code == 422


class TestDiagnosis:
    @pytest.mark.asyncio
    async def test_diagnoses_dependency_failure(self, app_client):
        """The headline scenario: SQL connection broken on a healthy process."""
        client, _, _, _ = app_client
        tracker = get_tool_error_tracker()
        for _ in range(12):
            tracker.record(
                "sql", "execute_query", "error",
                "Error: connect ECONNREFUSED 10.20.1.44:1433",
            )

        body = client.get("/api/monitoring/servers/sql/diagnosis").json()
        diagnosis = body["diagnosis"]

        assert diagnosis["failure_category"] == "db_connection_refused"
        assert diagnosis["owner"] == "customer"
        assert diagnosis["confidence"] == "high"
        assert diagnosis["is_dependency_failure"] is True
        assert diagnosis["summary"]
        assert diagnosis["remediation"]
        assert diagnosis["evidence"]
        # Says plainly that restarting will not fix it.
        assert body["auto_restart"]["would_help"] is True or \
               body["auto_restart"]["reason"]

    @pytest.mark.asyncio
    async def test_credentials_diagnosis_says_restart_wont_help(self, app_client):
        client, _, _, _ = app_client
        tracker = get_tool_error_tracker()
        for _ in range(12):
            tracker.record("sql", "execute_query", "error",
                           "Login failed for user 'sa'.")
        body = client.get("/api/monitoring/servers/sql/diagnosis").json()
        assert body["diagnosis"]["failure_category"] == "db_auth_failed"
        assert body["auto_restart"]["would_help"] is False

    @pytest.mark.asyncio
    async def test_404_for_unknown_server(self, app_client):
        client, _, _, _ = app_client
        assert client.get("/api/monitoring/servers/nope/diagnosis").status_code == 404


class TestWebhookAPI:
    @pytest.mark.asyncio
    async def test_register_rejects_unsafe_url(self, app_client):
        client, _, _, _ = app_client
        response = client.post(
            "/api/monitoring/webhooks",
            json={"url": "http://169.254.169.254/", "events": ["server.crashed"]},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_rejects_unknown_event_type(self, app_client):
        client, _, _, _ = app_client
        response = client.post(
            "/api/monitoring/webhooks",
            json={"url": "https://example.com/h", "events": ["server.exploded"]},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_list_delete_lifecycle(self, app_client):
        client, _, _, _ = app_client
        created = client.post(
            "/api/monitoring/webhooks",
            json={"url": "https://example.com/h", "events": ["server.crashed"]},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["secret"].startswith("whsec_")
        webhook_id = body["id"]

        listed = client.get("/api/monitoring/webhooks").json()
        assert listed["count"] == 1
        # Secret must never be readable back.
        assert listed["webhooks"][0]["secret"] == "***redacted***"

        assert client.delete(f"/api/monitoring/webhooks/{webhook_id}").status_code == 200
        assert client.get("/api/monitoring/webhooks").json()["count"] == 0

    @pytest.mark.asyncio
    async def test_delete_unknown_returns_404(self, app_client):
        client, _, _, _ = app_client
        assert client.delete("/api/monitoring/webhooks/nope").status_code == 404


class TestUptimeAPI:
    @pytest.mark.asyncio
    async def test_reports_per_server_and_fleet(self, app_client):
        client, manager, _, _ = app_client
        await manager.record_transition("sql", "running", reason="started")
        body = client.get("/api/monitoring/uptime?window=24h").json()
        assert body["window"] == "24h"
        assert "fleet" in body
        assert any(s["server_id"] == "sql" for s in body["servers"])

    @pytest.mark.asyncio
    async def test_rejects_invalid_window(self, app_client):
        client, _, _, _ = app_client
        assert client.get("/api/monitoring/uptime?window=13m").status_code == 422


class TestEventTypesReference:
    @pytest.mark.asyncio
    async def test_lists_every_type_with_severity(self, app_client):
        client, _, _, _ = app_client
        body = client.get("/api/monitoring/event-types").json()
        types = {e["type"] for e in body["event_types"]}
        # The types the integration guide tells consumers to subscribe to.
        for expected in (
            "server.crashed", "server.degraded", "server.dependency_failed",
            "server.unstable", "server.config_invalid", "gateway.config_invalid",
        ):
            assert expected in types, f"{expected} missing from reference"
        assert all(e["default_severity"] in ("info", "warning", "critical")
                   for e in body["event_types"])


class TestAuthEnforcement:
    @pytest.mark.asyncio
    async def test_monitoring_requires_token_in_secure_mode(self, monkeypatch):
        monkeypatch.setenv("FMCP_SECURE_MODE", "true")
        monkeypatch.setenv("FMCP_BEARER_TOKEN", "t" * 64)

        backend = InMemoryBackend()
        await backend.connect()
        manager = ServerManager(backend)
        app = await create_app(
            db_manager=backend, server_manager=manager,
            secure_mode=True, token="t" * 64,
        )
        with TestClient(app) as client:
            assert client.get("/api/monitoring/health").status_code == 401
            ok = client.get(
                "/api/monitoring/health",
                headers={"Authorization": f"Bearer {'t' * 64}"},
            )
            assert ok.status_code == 200

