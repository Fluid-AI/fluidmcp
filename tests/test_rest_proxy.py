"""Tests for REST proxy servers (fluidmcp/cli/services/rest_proxy.py)."""
import gzip

import httpx
import pytest
from fastapi import FastAPI

from fluidmcp.cli.services import rest_proxy
from fluidmcp.cli.services.rest_proxy import (
    ERROR_HEADER,
    RestProxyRegistry,
    build_upstream_url,
    install_rest_proxy,
    normalize_target,
    validate_rest_server,
    validate_rest_servers,
)

TOKEN = "gateway-token-123"


# ── Config validation ───────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("media.gupshup.com", "https://media.gupshup.com"),
    ("  media.gupshup.com  ", "https://media.gupshup.com"),
    ("https://api.example.com/", "https://api.example.com"),
    ("https://api.example.com/v1/", "https://api.example.com/v1"),
    ("HTTP://localhost:8080", "http://localhost:8080"),
    ("api.example.com:8443/base", "https://api.example.com:8443/base"),
])
def test_normalize_target(value, expected):
    assert normalize_target(value) == expected


@pytest.mark.parametrize("value", [
    None, "", "   ", 42,
    "ftp://example.com",
    "https://",
    "https://user:pass@example.com",
    "https://example.com?x=1",
    "https://example.com/#frag",
    "https://exa mple.com",
    "https://example.com:notaport",
])
def test_normalize_target_rejects(value):
    with pytest.raises(ValueError):
        normalize_target(value)


def test_validate_rest_server_valid():
    assert validate_rest_server("gupshup-chat", {"type": "rest-proxy", "target-rest-endpoint": "media.gupshup.com"}) == []


@pytest.mark.parametrize("name,config,fragment", [
    ("x", {"type": "proxy", "target-rest-endpoint": "a.com"}, "field 'type'"),
    ("x", {"target-rest-endpoint": "a.com"}, "field 'type'"),
    ("x", {"type": "rest-proxy"}, "target-rest-endpoint"),
    ("x", {"type": "rest-proxy", "target-rest-endpoint": "a.com", "headers": {}}, "unknown field(s) headers"),
    ("api", {"type": "rest-proxy", "target-rest-endpoint": "a.com"}, "reserved"),
    ("API", {"type": "rest-proxy", "target-rest-endpoint": "a.com"}, "reserved"),
    ("-x", {"type": "rest-proxy", "target-rest-endpoint": "a.com"}, "name must be"),
    ("a/b", {"type": "rest-proxy", "target-rest-endpoint": "a.com"}, "name must be"),
    ("x", "a.com", "must be an object"),
])
def test_validate_rest_server_errors(name, config, fragment):
    errors = validate_rest_server(name, config)
    assert any(fragment in e for e in errors), errors


def test_validate_rest_server_rejects_mcp_name_clash():
    errors = validate_rest_server("weather", {"type": "rest-proxy", "target-rest-endpoint": "a.com"}, ["weather"])
    assert any("already used by an MCP server" in e for e in errors)


def test_validate_rest_servers_section():
    assert validate_rest_servers([]) == ["Field 'restServers' must be an object"]
    errors = validate_rest_servers({
        "ok": {"type": "rest-proxy", "target-rest-endpoint": "a.com"},
        "bad": {"type": "rest-proxy"},
    })
    assert len(errors) == 1 and "'bad'" in errors[0]


def test_registry():
    registry = RestProxyRegistry()
    assert registry.register("chat", {"type": "rest-proxy", "target-rest-endpoint": "a.com/v1/"}) == "https://a.com/v1"
    assert "chat" in registry and registry.get("chat") == "https://a.com/v1" and len(registry) == 1
    with pytest.raises(ValueError):
        registry.register("api", {"type": "rest-proxy", "target-rest-endpoint": "a.com"})
    assert registry.unregister("chat") is True
    assert registry.unregister("chat") is False
    assert registry.names() == []


@pytest.mark.parametrize("target,tail,query,expected", [
    ("https://h.com", b"/a/b", b"", "https://h.com/a/b"),
    ("https://h.com", b"", b"", "https://h.com/"),
    ("https://h.com", b"/", b"", "https://h.com/"),
    ("https://h.com/v1", b"", b"", "https://h.com/v1"),
    ("https://h.com/v1", b"/", b"", "https://h.com/v1/"),
    ("https://h.com/v1", b"/msg", b"x=1&y=%20z", "https://h.com/v1/msg?x=1&y=%20z"),
    ("https://h.com", b"/a%2Fb", b"", "https://h.com/a%2Fb"),
    ("https://h.com", b"//evil.com/x", b"", "https://h.com//evil.com/x"),
])
def test_build_upstream_url(target, tail, query, expected):
    url = build_upstream_url(target, tail, query)
    assert str(url) == expected
    assert url.host == "h.com"


# ── Forwarding through an app ───────────────────────────────────────────────

def streamed(status, headers=None, content=b""):
    """An upstream response that is streamed like a real one (httpx pre-reads bytes content)."""
    return httpx.Response(status, headers=headers, stream=httpx.ByteStream(content))


class Upstream:
    """Fake upstream recording every request it receives."""

    def __init__(self, respond=None):
        self.requests = []
        self.bodies = []
        self.respond = respond or (lambda request: streamed(200, content=b"ok"))

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(await request.aread())
        self.requests.append(request)
        return self.respond(request)

    def client(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self), follow_redirects=False)
        client.headers.clear()
        return client


def make_app(upstream: Upstream, targets=None):
    app = FastAPI()

    @app.post("/{server_name}/mcp")
    async def mcp_route(server_name: str):
        return {"mcp": server_name}

    @app.get("/api/ping")
    async def api_ping():
        return {"api": "pong"}

    registry = RestProxyRegistry()
    for name, target in (targets or {"gupshup-chat": "media.gupshup.com"}).items():
        registry.register(name, {"type": "rest-proxy", "target-rest-endpoint": target})
    install_rest_proxy(app, registry, client=upstream.client())
    return app, registry


def caller(app) -> httpx.AsyncClient:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway")
    client.headers.clear()
    return client


@pytest.fixture(autouse=True)
def insecure(monkeypatch):
    monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
    monkeypatch.delenv("MCP_ROOT_PATH", raising=False)


async def test_get_forwards_path_and_raw_query():
    upstream = Upstream()
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.get("/gupshup-chat/wa/api/v1/a%2Fb?phone=%2B91999&x=1&x=2")
    assert r.status_code == 200 and r.content == b"ok"
    sent = upstream.requests[0]
    assert sent.method == "GET"
    assert str(sent.url) == "https://media.gupshup.com/wa/api/v1/a%2Fb?phone=%2B91999&x=1&x=2"
    assert sent.headers["host"] == "media.gupshup.com"
    assert "transfer-encoding" not in sent.headers and upstream.bodies[0] == b""


async def test_headers_forwarded_except_hop_by_hop_and_fluidmcp():
    upstream = Upstream()
    app, _ = make_app(upstream)
    async with caller(app) as c:
        await c.post("/gupshup-chat/msg", content=b"x", headers={
            "Authorization": "Bearer upstream-secret",
            "apikey": "gupshup-key",
            "X-Custom": "1",
            "FluidMCP-Authorization": "Bearer something",
            "FluidMCP-Other": "y",
            "Connection": "keep-alive, X-Hop",
            "X-Hop": "drop-me",
            "Keep-Alive": "timeout=5",
            "Proxy-Authorization": "Basic abc",
        })
    sent = upstream.requests[0].headers
    assert sent["authorization"] == "Bearer upstream-secret"
    assert sent["apikey"] == "gupshup-key"
    assert sent["x-custom"] == "1"
    for dropped in ("fluidmcp-authorization", "fluidmcp-other", "connection", "x-hop", "keep-alive", "proxy-authorization"):
        assert dropped not in sent, dropped
    # Nothing added on the way: no client defaults, no X-Forwarded-*.
    for added in ("user-agent", "accept-encoding", "x-forwarded-for"):
        assert added not in sent, added


async def test_binary_body_and_content_length_preserved():
    body = bytes(range(256)) * 40
    upstream = Upstream()
    app, _ = make_app(upstream)
    async with caller(app) as c:
        await c.post("/gupshup-chat/upload", content=body, headers={"Content-Type": "application/octet-stream"})
    sent = upstream.requests[0]
    assert upstream.bodies[0] == body
    assert sent.headers["content-length"] == str(len(body))
    assert "transfer-encoding" not in sent.headers
    assert sent.headers["content-type"] == "application/octet-stream"


async def test_multipart_body_forwarded_byte_for_byte():
    upstream = Upstream()
    app, _ = make_app(upstream)
    request = httpx.Request(
        "POST", "http://gateway/gupshup-chat/media",
        files={"file": ("a.jpg", b"\xff\xd8\xff" + b"\x00" * 100, "image/jpeg")},
        data={"channel": "whatsapp"},
    )
    expected = request.read()
    async with caller(app) as c:
        await c.send(request)
    sent = upstream.requests[0]
    assert sent.headers["content-type"] == request.headers["content-type"]
    assert sent.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert upstream.bodies[0] == expected


async def test_chunked_request_body_streamed():
    upstream = Upstream()
    app, _ = make_app(upstream)

    async def gen():
        yield b"part1-"
        yield b"part2"

    async with caller(app) as c:
        await c.post("/gupshup-chat/stream", content=gen())
    assert upstream.bodies[0] == b"part1-part2"


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def test_every_method_forwarded(method):
    upstream = Upstream()
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.request(method, "/gupshup-chat/x")
    assert r.status_code == 200
    assert upstream.requests[0].method == method


async def test_response_status_headers_and_raw_body_unchanged():
    compressed = gzip.compress(b'{"status":"submitted"}')

    def respond(request):
        return streamed(201, headers=[
            ("Content-Type", "application/json"),
            ("Content-Encoding", "gzip"),
            ("Set-Cookie", "a=1"),
            ("Set-Cookie", "b=2"),
            ("X-Upstream", "yes"),
            ("Connection", "close"),
        ], content=compressed)

    upstream = Upstream(respond)
    app, _ = make_app(upstream)
    async with caller(app) as c:
        async with c.stream("POST", "/gupshup-chat/msg", content=b"{}") as r:
            raw = b"".join([chunk async for chunk in r.aiter_raw()])
    assert r.status_code == 201
    assert raw == compressed
    assert r.headers["content-encoding"] == "gzip"
    assert r.headers.get_list("set-cookie") == ["a=1", "b=2"]
    assert r.headers["x-upstream"] == "yes"
    assert ERROR_HEADER.lower() not in r.headers
    assert "connection" not in r.headers or r.headers["connection"] != "close"


async def test_upstream_date_and_server_dropped():
    # Uvicorn adds its own Date and Server; forwarding the upstream's would send them twice.
    upstream = Upstream(lambda request: streamed(200, [
        ("Date", "Mon, 02 Nov 2026 00:00:00 GMT"), ("Server", "upstream/1.0"), ("X-Kept", "1"),
    ], b"ok"))
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.get("/gupshup-chat/x")
    assert "date" not in r.headers and "server" not in r.headers
    assert r.headers["x-kept"] == "1"


async def test_upstream_error_status_passes_through():
    upstream = Upstream(lambda request: streamed(401, {"Content-Type": "application/json"}, b'{"message": "invalid apikey"}'))
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.get("/gupshup-chat/x")
    assert r.status_code == 401 and r.json() == {"message": "invalid apikey"}
    assert ERROR_HEADER.lower() not in r.headers


async def test_redirect_returned_not_followed():
    upstream = Upstream(lambda request: streamed(302, {"Location": "https://elsewhere.example/x"}))
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.get("/gupshup-chat/x")
    assert r.status_code == 302 and r.headers["location"] == "https://elsewhere.example/x"
    assert len(upstream.requests) == 1


# ── Routing ─────────────────────────────────────────────────────────────────

async def test_proxy_name_shadows_mcp_suffix_but_other_routes_untouched():
    upstream = Upstream()
    app, _ = make_app(upstream)
    async with caller(app) as c:
        proxied = await c.post("/gupshup-chat/mcp", content=b"{}")
        mcp = await c.post("/weather/mcp")
        api = await c.get("/api/ping")
        unknown = await c.get("/not-registered/x")
    assert proxied.content == b"ok" and str(upstream.requests[0].url) == "https://media.gupshup.com/mcp"
    assert mcp.json() == {"mcp": "weather"}
    assert api.json() == {"api": "pong"}
    assert unknown.status_code == 404
    assert len(upstream.requests) == 1


@pytest.mark.parametrize("path,expected", [
    ("/chat", "https://h.com/v1"),
    ("/chat/", "https://h.com/v1/"),
    ("/chat/msg", "https://h.com/v1/msg"),
])
async def test_bare_name_maps_to_target_root(path, expected):
    upstream = Upstream()
    app, _ = make_app(upstream, {"chat": "https://h.com/v1"})
    async with caller(app) as c:
        await c.get(path)
    assert str(upstream.requests[0].url) == expected


async def test_registry_changes_apply_without_remount():
    upstream = Upstream()
    app, registry = make_app(upstream, {"chat": "a.com"})
    async with caller(app) as c:
        assert (await c.get("/chat/x")).status_code == 200
        registry.unregister("chat")
        assert (await c.get("/chat/x")).status_code == 404
        registry.register("chat", {"type": "rest-proxy", "target-rest-endpoint": "b.com"})
        await c.get("/chat/y")
    assert [str(r.url) for r in upstream.requests] == ["https://a.com/x", "https://b.com/y"]


async def test_mcp_root_path_prefix(monkeypatch):
    monkeypatch.setenv("MCP_ROOT_PATH", "/fluidmcp")
    upstream = Upstream()
    app, _ = make_app(upstream)
    async with caller(app) as c:
        prefixed = await c.get("/fluidmcp/gupshup-chat/x?y=1")
        bare = await c.get("/gupshup-chat/x")
    assert prefixed.status_code == 200
    assert str(upstream.requests[0].url) == "https://media.gupshup.com/x?y=1"
    assert bare.status_code == 404 and len(upstream.requests) == 1


@pytest.mark.parametrize("path", ["/gupshup-chat/a/%2e%2e/b", "/gupshup-chat/%2E%2E", "/gupshup-chat/%2e/x"])
async def test_dot_segments_rejected(path):
    upstream = Upstream()
    app, _ = make_app(upstream)
    # Send the path verbatim: httpx would otherwise normalise literal dot segments.
    async with caller(app) as c:
        r = await c.send(httpx.Request("GET", httpx.URL("http://gateway").copy_with(raw_path=path.encode())))
    assert r.status_code == 400 and r.headers[ERROR_HEADER] == "bad_path"
    assert upstream.requests == []


async def test_literal_dot_segments_rejected():
    # httpx always normalises literal "..", so drive the ASGI app directly,
    # as a client like `curl --path-as-is` would reach it.
    upstream = Upstream()
    app, _ = make_app(upstream)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": "/gupshup-chat/../admin", "raw_path": b"/gupshup-chat/../admin",
        "root_path": "", "query_string": b"", "headers": [], "server": ("gateway", 80), "client": ("1.2.3.4", 1),
    }
    await app(scope, receive, send)
    assert sent[0]["status"] == 400
    assert upstream.requests == []


# ── Secure mode ─────────────────────────────────────────────────────────────

@pytest.fixture
def secure(monkeypatch):
    monkeypatch.setenv("FMCP_SECURE_MODE", "true")
    monkeypatch.setenv("FMCP_BEARER_TOKEN", TOKEN)


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": f"Bearer {TOKEN}"},
    {"FluidMCP-Authorization": "Bearer wrong"},
    {"FluidMCP-Authorization": "Bearer"},
])
async def test_secure_mode_rejects_without_fluidmcp_token(secure, headers):
    upstream = Upstream()
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.get("/gupshup-chat/x", headers=headers)
    assert r.status_code == 401
    assert r.headers[ERROR_HEADER] == "unauthorized"
    assert upstream.requests == []


@pytest.mark.parametrize("value", [f"Bearer {TOKEN}", f"bearer {TOKEN}", TOKEN])
async def test_secure_mode_accepts_fluidmcp_token_and_forwards_authorization(secure, value):
    upstream = Upstream()
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.get("/gupshup-chat/x", headers={"FluidMCP-Authorization": value, "Authorization": "Bearer upstream-key"})
    assert r.status_code == 200
    sent = upstream.requests[0].headers
    assert sent["authorization"] == "Bearer upstream-key"
    assert "fluidmcp-authorization" not in sent


async def test_secure_mode_without_configured_token(monkeypatch):
    monkeypatch.setenv("FMCP_SECURE_MODE", "true")
    monkeypatch.delenv("FMCP_BEARER_TOKEN", raising=False)
    upstream = Upstream()
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.get("/gupshup-chat/x", headers={"FluidMCP-Authorization": "Bearer x"})
    assert r.status_code == 500 and r.headers[ERROR_HEADER] == "misconfigured"


# ── Upstream failures ───────────────────────────────────────────────────────

def _raise(exc):
    def respond(request):
        raise exc
    return respond


async def test_unreachable_upstream_returns_tagged_502():
    upstream = Upstream(_raise(httpx.ConnectError("refused")))
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.get("/gupshup-chat/x")
    assert r.status_code == 502
    assert r.headers[ERROR_HEADER] == "upstream_unreachable"
    assert r.json()["error"] == "upstream_unreachable"


async def test_upstream_timeout_returns_tagged_504():
    upstream = Upstream(_raise(httpx.ReadTimeout("slow")))
    app, _ = make_app(upstream)
    async with caller(app) as c:
        r = await c.get("/gupshup-chat/x")
    assert r.status_code == 504 and r.headers[ERROR_HEADER] == "upstream_timeout"


# ── Shared client ───────────────────────────────────────────────────────────

async def test_shared_client_adds_no_default_headers(monkeypatch):
    monkeypatch.setenv("FMCP_REST_PROXY_TIMEOUT", "12")
    await rest_proxy.close_client()
    client = await rest_proxy.get_client()
    try:
        assert dict(client.headers) == {}
        assert client.follow_redirects is False
        assert client.timeout.read == 12 and client.timeout.connect == rest_proxy.CONNECT_TIMEOUT_SECONDS
        assert await rest_proxy.get_client() is client
    finally:
        await rest_proxy.close_client()
    assert rest_proxy._client is None
