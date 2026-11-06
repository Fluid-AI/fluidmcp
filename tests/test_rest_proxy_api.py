"""Tests for /api/rest-servers and REST proxy persistence (fmcp serve side)."""
import httpx
import pytest
from fastapi import FastAPI

from fluidmcp.cli.api.management import router
from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.repositories.base import PersistenceBackend
from fluidmcp.cli.services.rest_proxy import RestProxyRegistry, install_rest_proxy, load_rest_servers
from fluidmcp.cli.services.server_manager import ServerManager

TOKEN = "admin-token"
GUPSHUP = {"id": "gupshup-chat", "type": "rest-proxy", "target-rest-endpoint": "media.gupshup.com"}


@pytest.fixture
def upstream():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(b"upstream:" + request.url.host.encode()))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.headers.clear()
    return client, requests


@pytest.fixture
def backend():
    return InMemoryBackend()


@pytest.fixture
def app(backend, upstream, monkeypatch):
    monkeypatch.setenv("FMCP_SECURE_MODE", "true")
    monkeypatch.setenv("FMCP_BEARER_TOKEN", TOKEN)
    monkeypatch.delenv("MCP_ROOT_PATH", raising=False)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.server_manager = ServerManager(backend)
    app.state.db_manager = backend
    app.state.rest_proxy_registry = RestProxyRegistry()
    install_rest_proxy(app, app.state.rest_proxy_registry, client=upstream[0])
    return app


@pytest.fixture
async def api(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gw",
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as client:
        yield client


PROXY_AUTH = {"FluidMCP-Authorization": f"Bearer {TOKEN}"}


async def test_add_then_call_then_list(api, app, backend, upstream):
    r = await api.post("/api/rest-servers", json=GUPSHUP)
    assert r.status_code == 200, r.text
    # In-memory backend: stored, but not persisted across restarts.
    assert r.json() == {"message": "REST server 'gupshup-chat' added", "id": "gupshup-chat",
                        "target_url": "https://media.gupshup.com", "persisted": False}

    called = await api.post("/gupshup-chat/wa/msg", content=b"x", headers=PROXY_AUTH)
    assert called.status_code == 200 and called.content == b"upstream:media.gupshup.com"
    assert str(upstream[1][0].url) == "https://media.gupshup.com/wa/msg"

    listed = (await api.get("/api/rest-servers")).json()
    assert listed["count"] == 1
    server = listed["servers"][0]
    assert server["id"] == "gupshup-chat" and server["target-rest-endpoint"] == "media.gupshup.com"
    assert server["target_url"] == "https://media.gupshup.com" and server["path"] == "/gupshup-chat/"
    assert server["persisted"] is False and "created_at" in server

    assert (await backend.get_rest_server("gupshup-chat"))["target-rest-endpoint"] == "media.gupshup.com"


async def test_get_one_and_404(api):
    await api.post("/api/rest-servers", json=GUPSHUP)
    assert (await api.get("/api/rest-servers/gupshup-chat")).json()["target_url"] == "https://media.gupshup.com"
    assert (await api.get("/api/rest-servers/nope")).status_code == 404


async def test_update_changes_target_live(api, upstream):
    await api.post("/api/rest-servers", json=GUPSHUP)
    r = await api.put("/api/rest-servers/gupshup-chat", json={"type": "rest-proxy", "target-rest-endpoint": "https://api.gupshup.io/v1"})
    assert r.status_code == 200 and r.json()["target_url"] == "https://api.gupshup.io/v1"
    await api.get("/gupshup-chat/msg", headers=PROXY_AUTH)
    assert str(upstream[1][-1].url) == "https://api.gupshup.io/v1/msg"
    assert (await api.put("/api/rest-servers/nope", json={"type": "rest-proxy", "target-rest-endpoint": "a.com"})).status_code == 404
    assert (await api.put("/api/rest-servers/gupshup-chat", json={"id": "other", "type": "rest-proxy", "target-rest-endpoint": "a.com"})).status_code == 400


async def test_delete_stops_forwarding(api, backend, upstream):
    await api.post("/api/rest-servers", json=GUPSHUP)
    r = await api.delete("/api/rest-servers/gupshup-chat")
    assert r.status_code == 200
    after = await api.get("/gupshup-chat/msg", headers=PROXY_AUTH)
    assert after.status_code == 404 and upstream[1] == []
    assert await backend.get_rest_server("gupshup-chat") is None
    assert (await api.delete("/api/rest-servers/gupshup-chat")).status_code == 404


@pytest.mark.parametrize("body,fragment", [
    ({"type": "rest-proxy", "target-rest-endpoint": "a.com"}, "id is required"),
    ({"id": "api", "type": "rest-proxy", "target-rest-endpoint": "a.com"}, "reserved"),
    ({"id": "x", "type": "proxy", "target-rest-endpoint": "a.com"}, "field 'type'"),
    ({"id": "x", "type": "rest-proxy", "target-rest-endpoint": "ftp://a.com"}, "target-rest-endpoint"),
    ({"id": "x", "type": "rest-proxy", "target-rest-endpoint": "a.com", "headers": {}}, "unknown field"),
    ({"id": "x", "type": "rest-proxy", "target-rest-endpoint": "a.com", "$where": "1"}, ""),
])
async def test_add_rejects_invalid(api, app, body, fragment):
    r = await api.post("/api/rest-servers", json=body)
    assert r.status_code == 400
    assert fragment in r.json()["detail"]
    assert len(app.state.rest_proxy_registry) == 0


async def test_add_duplicate_is_409(api):
    await api.post("/api/rest-servers", json=GUPSHUP)
    assert (await api.post("/api/rest-servers", json=GUPSHUP)).status_code == 409


async def test_rest_and_mcp_ids_cannot_clash(api):
    mcp = {"id": "weather", "name": "Weather", "command": "npx", "args": ["-y", "x"], "env": {}}
    assert (await api.post("/api/servers", json=mcp)).status_code == 200
    clash = await api.post("/api/rest-servers", json={**GUPSHUP, "id": "weather"})
    assert clash.status_code == 409 and "MCP server" in clash.json()["detail"]

    await api.post("/api/rest-servers", json=GUPSHUP)
    clash = await api.post("/api/servers", json={**mcp, "id": "gupshup-chat"})
    assert clash.status_code == 409 and "REST proxy" in clash.json()["detail"]


async def test_management_endpoints_require_admin_token(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as anon:
        assert (await anon.get("/api/rest-servers")).status_code == 401
        assert (await anon.get("/api/rest-servers/x")).status_code == 401
        assert (await anon.post("/api/rest-servers", json=GUPSHUP)).status_code == 401
        assert (await anon.put("/api/rest-servers/x", json=GUPSHUP)).status_code == 401
        assert (await anon.delete("/api/rest-servers/x")).status_code == 401


async def test_proxy_call_requires_fluidmcp_header_in_secure_mode(api, upstream):
    await api.post("/api/rest-servers", json=GUPSHUP)
    # The api client sends the admin token in Authorization, which belongs to the upstream.
    r = await api.get("/gupshup-chat/msg")
    assert r.status_code == 401 and r.headers["X-FluidMCP-Error"] == "unauthorized"
    assert upstream[1] == []


async def test_backend_without_rest_storage_keeps_proxy_live(app, upstream):
    class NoRestStorage(InMemoryBackend):
        save_rest_server = PersistenceBackend.save_rest_server
        get_rest_server = PersistenceBackend.get_rest_server
        list_rest_servers = PersistenceBackend.list_rest_servers
        delete_rest_server = PersistenceBackend.delete_rest_server

    app.state.server_manager = ServerManager(NoRestStorage())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw",
                                 headers={"Authorization": f"Bearer {TOKEN}"}) as api:
        r = await api.post("/api/rest-servers", json=GUPSHUP)
        assert r.status_code == 200 and r.json()["persisted"] is False
        listed = (await api.get("/api/rest-servers")).json()["servers"]
        assert listed[0]["persisted"] is False
        assert (await api.get("/gupshup-chat/x", headers=PROXY_AUTH)).status_code == 200


# ── Persistence ─────────────────────────────────────────────────────────────

async def test_in_memory_backend_crud():
    backend = InMemoryBackend()
    assert await backend.save_rest_server(GUPSHUP) is True
    first = await backend.get_rest_server("gupshup-chat")
    await backend.save_rest_server({**GUPSHUP, "target-rest-endpoint": "b.com"})
    second = await backend.get_rest_server("gupshup-chat")
    assert second["target-rest-endpoint"] == "b.com"
    assert second["created_at"] == first["created_at"] and second["updated_at"] >= first["updated_at"]
    await backend.save_rest_server({**GUPSHUP, "id": "a-first"})
    assert [d["id"] for d in await backend.list_rest_servers()] == ["a-first", "gupshup-chat"]
    assert await backend.delete_rest_server("gupshup-chat") is True
    assert await backend.delete_rest_server("gupshup-chat") is False
    await backend.disconnect()
    assert await backend.list_rest_servers() == []


async def test_load_rest_servers_skips_invalid_entries():
    backend = InMemoryBackend()
    await backend.save_rest_server(GUPSHUP)
    await backend.save_rest_server({"id": "api", "type": "rest-proxy", "target-rest-endpoint": "a.com"})
    registry = RestProxyRegistry()
    assert await load_rest_servers(backend, registry) == 1
    assert registry.names() == ["gupshup-chat"]
    assert registry.get("gupshup-chat") == "https://media.gupshup.com"


# ── MongoDB (skipped when MongoDB is not reachable; see conftest.py) ─────────

async def test_database_manager_rest_server_crud(mongodb_test_connection):
    db = mongodb_test_connection
    assert await db.init_db() is True
    indexes = await db.db.fluidmcp_rest_servers.index_information()
    assert any(spec.get("unique") and spec["key"] == [("id", 1)] for spec in indexes.values())

    assert await db.save_rest_server(GUPSHUP) is True
    first = await db.get_rest_server("gupshup-chat")
    assert first["target-rest-endpoint"] == "media.gupshup.com" and "_id" not in first
    await db.save_rest_server({**GUPSHUP, "target-rest-endpoint": "b.com", "created_at": "ignored"})
    second = await db.get_rest_server("gupshup-chat")
    assert second["target-rest-endpoint"] == "b.com" and second["created_at"] == first["created_at"]
    await db.save_rest_server({**GUPSHUP, "id": "a-first"})
    assert [d["id"] for d in await db.list_rest_servers()] == ["a-first", "gupshup-chat"]
    assert await db.delete_rest_server("gupshup-chat") is True
    assert await db.delete_rest_server("gupshup-chat") is False


async def test_serve_app_end_to_end_with_mongodb(serve_test_app, upstream, monkeypatch):
    """create_app() mounts the route; proxies added via the API survive a restart (reload from MongoDB)."""
    monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
    app, db, _ = serve_test_app
    await db.init_db()
    from fluidmcp.cli.services import rest_proxy

    async def get_client():
        return upstream[0]

    monkeypatch.setattr(rest_proxy, "get_client", get_client)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
        assert (await c.post("/api/rest-servers", json=GUPSHUP)).status_code == 200
        r = await c.get("/gupshup-chat/wa/msg?x=1")
        assert r.status_code == 200 and str(upstream[1][0].url) == "https://media.gupshup.com/wa/msg?x=1"
        assert (await c.get("/health")).status_code == 200

    # Simulated restart: a fresh registry loads what the API stored.
    fresh = RestProxyRegistry()
    assert await load_rest_servers(db, fresh) == 1
    assert fresh.get("gupshup-chat") == "https://media.gupshup.com"


# ── Review fixes: durable backends, repair, concurrency, route clashes ──────

class DurableBackend(InMemoryBackend):
    """In-memory backend that claims durability, with switchable save/delete failures."""

    def __init__(self):
        super().__init__()
        self.fail_save = False
        self.fail_delete = False

    def persists_rest_servers(self):
        return True

    async def save_rest_server(self, config):
        return False if self.fail_save else await super().save_rest_server(config)

    async def delete_rest_server(self, id):
        return False if self.fail_delete else await super().delete_rest_server(id)


@pytest.fixture
def durable(app):
    backend = DurableBackend()
    app.state.server_manager = ServerManager(backend)
    return backend


async def test_durable_backend_reports_persisted(api, durable):
    r = await api.post("/api/rest-servers", json=GUPSHUP)
    assert r.json()["persisted"] is True
    assert (await api.get("/api/rest-servers/gupshup-chat")).json()["persisted"] is True


async def test_failed_save_on_durable_backend_changes_nothing(api, app, durable):
    durable.fail_save = True
    r = await api.post("/api/rest-servers", json=GUPSHUP)
    assert r.status_code == 500
    assert "gupshup-chat" not in app.state.rest_proxy_registry

    durable.fail_save = False
    await api.post("/api/rest-servers", json=GUPSHUP)
    durable.fail_save = True
    r = await api.put("/api/rest-servers/gupshup-chat", json={"type": "rest-proxy", "target-rest-endpoint": "evil.example"})
    assert r.status_code == 500
    assert app.state.rest_proxy_registry.get("gupshup-chat") == "https://media.gupshup.com"


async def test_failed_db_delete_keeps_proxy_active(api, app, durable):
    await api.post("/api/rest-servers", json=GUPSHUP)
    durable.fail_delete = True
    r = await api.delete("/api/rest-servers/gupshup-chat")
    assert r.status_code == 500 and "still active" in r.json()["detail"]
    assert "gupshup-chat" in app.state.rest_proxy_registry
    assert await durable.get_rest_server("gupshup-chat") is not None


async def test_stored_but_unloaded_entry_can_be_repaired(api, app, backend):
    # Stored, but not live (as when it failed validation at startup).
    await backend.save_rest_server(GUPSHUP)
    assert (await api.get("/api/rest-servers/gupshup-chat")).status_code == 404
    r = await api.put("/api/rest-servers/gupshup-chat", json={"type": "rest-proxy", "target-rest-endpoint": "fixed.example"})
    assert r.status_code == 200 and app.state.rest_proxy_registry.get("gupshup-chat") == "https://fixed.example"

    app.state.rest_proxy_registry.unregister("gupshup-chat")
    assert (await api.post("/api/rest-servers", json=GUPSHUP)).status_code == 200


async def test_delete_stored_but_unloaded_entry(api, backend):
    await backend.save_rest_server(GUPSHUP)
    assert (await api.delete("/api/rest-servers/gupshup-chat")).status_code == 200
    assert await backend.get_rest_server("gupshup-chat") is None


async def test_concurrent_adds_of_same_id(api):
    import asyncio
    results = await asyncio.gather(
        api.post("/api/rest-servers", json={**GUPSHUP, "target-rest-endpoint": "a.example"}),
        api.post("/api/rest-servers", json={**GUPSHUP, "target-rest-endpoint": "b.example"}),
    )
    assert sorted(r.status_code for r in results) == [200, 409]


async def test_name_clashing_with_live_route_is_refused(api, app):
    @app.get("/settings")
    async def settings():
        return {"settings": True}

    r = await api.post("/api/rest-servers", json={**GUPSHUP, "id": "settings"})
    assert r.status_code == 409 and "existing FluidMCP route" in r.json()["detail"]
    assert (await api.get("/settings")).json() == {"settings": True}


def test_drop_shadowing_proxies_at_startup(app):
    from fluidmcp.cli.services.rest_proxy import drop_shadowing_proxies

    @app.get("/settings/{x}")
    async def settings(x: str):
        return {}

    registry = app.state.rest_proxy_registry
    registry.register("settings", {"type": "rest-proxy", "target-rest-endpoint": "a.example"})
    registry.register("gupshup-chat", {"type": "rest-proxy", "target-rest-endpoint": "a.example"})
    assert drop_shadowing_proxies(app, registry) == ["settings"]
    assert registry.names() == ["gupshup-chat"]
