"""Tests for the tunnel client (fluidmcp/cli/tunnel) against the fake GPT Engine server."""

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger

from fluidmcp.cli.tunnel import protocol, tunnel_from_env
from fluidmcp.cli.tunnel.client import TunnelClient
from fluidmcp.cli.tunnel.protocol import generate_identity_key, private_key_to_b64, public_key_to_b64
from tests.tunnel_fake_server import FakeTunnelServer

TOKEN = "tunnel-token"
CONNECTOR = "site-a"
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


def raw_public(key) -> bytes:
    return key.public_key().public_bytes_raw()


class Gateway:
    """Stands in for the local FluidMCP gateway behind the tunnel."""

    def __init__(self, handler=None):
        self.requests = []
        self._handler = handler or (lambda request: httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}))
        self.transport = httpx.MockTransport(self._record)

    async def _record(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        result = self._handler(request)
        return await result if asyncio.iscoroutine(result) else result


async def start_pair(gateway, client_key=None, server_token=TOKEN, pinned_server_key=None, **client_kwargs):
    client_key = client_key or generate_identity_key()
    server = FakeTunnelServer(server_token, CONNECTOR, [raw_public(client_key)])
    url = await server.start()
    client = TunnelClient(
        url=url,
        token=TOKEN,
        connector_id=CONNECTOR,
        allowed_servers=["srv-a", "srv-b"],
        server_public_keys=[pinned_server_key or server.public_key],
        identity_key=client_key,
        local_base_url="http://127.0.0.1:8099/fluidmcp",
        local_token="gateway-token",
        transport=gateway.transport,
        **client_kwargs,
    )
    client.start()
    return server, client


async def stop_pair(server, client):
    await client.stop()
    await server.stop()


@pytest.mark.asyncio
async def test_round_trip_through_tunnel():
    gateway = Gateway()
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        assert server.hello["connector"] == CONNECTOR
        assert server.hello["servers"] == ["srv-a", "srv-b"]

        reply = await server.send_request("srv-a", LIST_TOOLS)
        assert reply["type"] == "response"
        assert reply["status"] == 200
        assert reply["body"]["result"] == {"tools": []}

        request = gateway.requests[0]
        assert str(request.url) == "http://127.0.0.1:8099/fluidmcp/srv-a/mcp"
        assert request.headers["Authorization"] == "Bearer gateway-token"
        assert request.headers["X-Trace-ID"] == reply["id"]
        assert json.loads(request.content) == LIST_TOOLS
        assert client.status()["connected"] is True
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_server_not_in_allowlist_is_rejected():
    gateway = Gateway()
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        reply = await server.send_request("not-allowed", LIST_TOOLS)
        assert reply == {"type": "error", "id": reply["id"], "code": "server_not_allowed"}
        assert gateway.requests == []
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_local_timeout_reported():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    server, client = await start_pair(Gateway(handler))
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        reply = await server.send_request("srv-a", LIST_TOOLS)
        assert reply["code"] == "local_timeout"
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_non_json_and_empty_responses():
    def handler(request):
        if request.url.path.endswith("srv-a/mcp"):
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(204)

    server, client = await start_pair(Gateway(handler))
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        text_reply = await server.send_request("srv-a", LIST_TOOLS)
        assert (text_reply["status"], text_reply["body"]) == (502, "bad gateway")
        empty_reply = await server.send_request("srv-b", LIST_TOOLS)
        assert (empty_reply["status"], empty_reply["body"]) == (204, None)
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_concurrent_requests_are_limited():
    in_flight = 0
    peak = 0

    async def handler(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return httpx.Response(200, json={"echo": json.loads(request.content)["id"]})

    server, client = await start_pair(Gateway(handler), max_concurrency=5)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        bodies = [{"jsonrpc": "2.0", "id": i, "method": "tools/list"} for i in range(25)]
        replies = await asyncio.gather(*(server.send_request("srv-a", body) for body in bodies))
        assert [r["body"]["echo"] for r in replies] == list(range(25))
        assert peak <= 5
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_rekey_keeps_requests_flowing(monkeypatch):
    monkeypatch.setattr(protocol, "REKEY_INTERVAL", 0.0)
    monkeypatch.setattr(TunnelClient, "TICK_INTERVAL", 0.05)
    server, client = await start_pair(Gateway())
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        for _ in range(10):
            assert (await server.send_request("srv-a", LIST_TOOLS))["status"] == 200
            await asyncio.sleep(0.05)
        assert client.status()["key_no"] > 2
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_wrong_token_is_rejected():
    server, client = await start_pair(Gateway(), server_token="other-token")
    try:
        await asyncio.sleep(0.5)
        assert server.rejected == 1
        assert server.hello is None
        assert client.status()["connected"] is False
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_impostor_server_is_rejected():
    server, client = await start_pair(Gateway(), pinned_server_key=raw_public(generate_identity_key()))
    try:
        await asyncio.sleep(0.5)
        assert server.hello is None
        assert client.status()["connected"] is False
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_unknown_client_key_is_rejected():
    client_key = generate_identity_key()
    server = FakeTunnelServer(TOKEN, CONNECTOR, [raw_public(generate_identity_key())])
    url = await server.start()
    client = TunnelClient(url, TOKEN, CONNECTOR, ["srv-a"], [server.public_key], client_key, "http://127.0.0.1:8099")
    client.start()
    try:
        await asyncio.sleep(0.5)
        assert server.rejected == 1
        assert server.hello is None
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_reconnects_after_server_restart():
    client_key = generate_identity_key()
    server, client = await start_pair(Gateway(), client_key=client_key)
    port = int(client._url.rsplit(":", 1)[1])
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        await server.stop()

        restarted = FakeTunnelServer(TOKEN, CONNECTOR, [raw_public(client_key)])
        restarted.identity_key, restarted.public_key = server.identity_key, server.public_key
        await restarted.start(port=port)
        server = restarted
        await asyncio.wait_for(server.connected.wait(), 10)
        assert (await server.send_request("srv-a", LIST_TOOLS))["status"] == 200
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_bodies_are_not_logged():
    secret = "member-ssn-123-45-6789"
    lines = []
    sink = logger.add(lambda message: lines.append(str(message)), level="DEBUG")
    gateway = Gateway(lambda request: httpx.Response(200, json={"result": secret}))
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        await server.send_request("srv-a", {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"q": secret}})
    finally:
        await stop_pair(server, client)
        logger.remove(sink)
    assert lines
    assert not any(secret in line for line in lines)


async def send_raw(server, plaintext: bytes):
    async with server._lock:
        await server._ws.send(server._channel.encrypt(plaintext))


async def wait_for(predicate, timeout=5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "condition not met in time"
        await asyncio.sleep(0.02)


def tool_call(tag):
    params = {"name": "send_otp", "arguments": {"tag": tag}}
    return {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": params}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
async def test_gateway_error_status_passed_through(status):
    body = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "nope"}}
    gateway = Gateway(lambda request: httpx.Response(status, json=body))
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        reply = await server.send_request("srv-a", LIST_TOOLS)
        assert (reply["type"], reply["status"], reply["body"]) == ("response", status, body)
        assert len(gateway.requests) == 1
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_gateway_refusing_connections_reports_not_delivered(monkeypatch):
    monkeypatch.setattr(TunnelClient, "LOCAL_CONNECT_RETRY", 0.3)

    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    gateway = Gateway(handler)
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        reply = await server.send_request("srv-a", tool_call("refused"))
        # A refused connection means the gateway never received the request, so a retry is safe.
        assert (reply["code"], reply["reason"]) == ("not_delivered", "gateway_unreachable")
        assert len(gateway.requests) >= 1  # retried only because the connection was refused
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_failure_after_request_sent_is_not_retried():
    def handler(request):
        raise httpx.ReadError("connection reset after the request was sent", request=request)

    gateway = Gateway(handler)
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        reply = await server.send_request("srv-a", tool_call("reset"))
        assert reply["code"] == "local_call_failed"
        assert len(gateway.requests) == 1
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_disconnect_with_request_in_flight_runs_it_once():
    release = asyncio.Event()

    async def handler(request):
        await release.wait()
        return httpx.Response(200, json={"ok": True})

    gateway = Gateway(handler)
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        pending = asyncio.create_task(server.send_request("srv-a", tool_call("in-flight"), timeout=1))
        await wait_for(lambda: len(gateway.requests) == 1)
        await server._ws.close(1012)
        await wait_for(lambda: not server.connected.is_set())
        await asyncio.wait_for(server.connected.wait(), 5)  # reconnected
        release.set()
        with pytest.raises(asyncio.TimeoutError):
            await pending  # the reply was lost with the old connection
        await wait_for(lambda: not client._inflight)  # the call outlived its connection and finished
        assert len(gateway.requests) == 1
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_stop_with_request_in_flight():
    async def handler(request):
        await asyncio.sleep(30)
        return httpx.Response(200, json={})

    gateway = Gateway(handler)
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        asyncio.create_task(server.send_request("srv-a", tool_call("shutdown"), timeout=5))
        await wait_for(lambda: len(gateway.requests) == 1)
        await asyncio.wait_for(client.stop(), 2)
        assert client.status()["connected"] is False
        assert not client.is_running()
        assert client._inflight == {} and client._deliveries == set()
        assert client._semaphore._value == 20  # slot released
        assert len(gateway.requests) == 1
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_repeated_request_id_runs_once():
    gateway = Gateway()
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        message = json.dumps({"type": "request", "id": "same-id", "server": "srv-a", "body": tool_call("dup")}).encode()
        await send_raw(server, message)
        await send_raw(server, message)
        await asyncio.sleep(0.5)
        assert len(gateway.requests) == 1
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_malformed_messages_are_ignored():
    gateway = Gateway()
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        for raw in (b"not json", b"[1, 2]", b'{"type": "bogus", "id": "x"}',
                    b'{"type": "request", "server": "srv-a", "body": {}}',
                    b'{"type": "request", "id": 5, "server": "srv-a", "body": {}}'):
            await send_raw(server, raw)
        reply = await server.send_request("srv-a", "not an object")
        assert reply["code"] == "bad_request"
        assert (await server.send_request("srv-a", LIST_TOOLS))["status"] == 200
        assert len(gateway.requests) == 1
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_oversized_reply_reports_response_too_large():
    def handler(request):
        if request.url.path.endswith("srv-a/mcp"):
            return httpx.Response(200, text="x" * (protocol.MAX_PLAINTEXT + 1))
        return httpx.Response(200, json={})

    gateway = Gateway(handler)
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        reply = await server.send_request("srv-a", LIST_TOOLS)
        assert reply["code"] == "response_too_large"
        assert (await server.send_request("srv-b", LIST_TOOLS))["type"] == "response"  # still connected
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
@pytest.mark.parametrize("attack", ["oversized_frame", "tampered_record", "text_frame"])
async def test_bad_frame_closes_connection_without_forwarding(attack):
    gateway = Gateway()
    server, client = await start_pair(gateway)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        ws = server._ws
        if attack == "oversized_frame":
            await ws.send(bytes(protocol.MAX_FRAME + 1))
        elif attack == "tampered_record":
            async with server._lock:
                frame = bytearray(server._channel.encrypt(json.dumps(
                    {"type": "request", "id": "t", "server": "srv-a", "body": LIST_TOOLS}).encode()))
                frame[20] ^= 1
                await ws.send(bytes(frame))
        else:
            await ws.send("text")
        await ws.wait_closed()
        assert ws.close_code == (1009 if attack == "oversized_frame" else 1008)
        await asyncio.wait_for(server.connected.wait(), 5)  # fresh handshake
        assert gateway.requests == []
    finally:
        await stop_pair(server, client)


@pytest.mark.asyncio
async def test_tokens_and_keys_are_not_logged():
    lines = []
    sink = logger.add(lambda message: lines.append(str(message)), level="DEBUG")
    client_key = generate_identity_key()
    gateway = Gateway()
    server, client = await start_pair(gateway, client_key=client_key)
    rejected_server, rejected_client = await start_pair(Gateway(), server_token="other-token")
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        await server.send_request("srv-a", LIST_TOOLS)
        await asyncio.sleep(0.5)
    finally:
        await stop_pair(server, client)
        await stop_pair(rejected_server, rejected_client)
        logger.remove(sink)
    text = "\n".join(lines)
    for secret in (TOKEN, "gateway-token", private_key_to_b64(client_key)):
        assert secret not in text


class TestTunnelFromEnv:
    @pytest.fixture
    def tunnel_env(self, monkeypatch, tmp_path):
        key = generate_identity_key()
        key_file = tmp_path / "identity.key"
        key_file.write_text(private_key_to_b64(key))
        key_file.chmod(0o600)
        monkeypatch.setenv("FMCP_TUNNEL_URL", "wss://engine.example.com/ws/mcp-tunnel")
        monkeypatch.setenv("FMCP_TUNNEL_TOKEN", TOKEN)
        monkeypatch.setenv("FMCP_TUNNEL_CONNECTOR_ID", CONNECTOR)
        monkeypatch.setenv("FMCP_TUNNEL_ALLOWED_SERVERS", "srv-a, srv-b")
        monkeypatch.setenv("FMCP_TUNNEL_SERVER_PUBLIC_KEYS", public_key_to_b64(generate_identity_key()))
        monkeypatch.setenv("FMCP_TUNNEL_KEY_PATH", str(key_file))
        monkeypatch.setenv("MCP_ROOT_PATH", "/fluidmcp")
        monkeypatch.setenv("FMCP_SECURE_MODE", "true")
        monkeypatch.setenv("FMCP_BEARER_TOKEN", "gateway-token")
        return monkeypatch

    def test_disabled_without_url(self, monkeypatch):
        monkeypatch.delenv("FMCP_TUNNEL_URL", raising=False)
        assert tunnel_from_env(8099) is None

    def test_valid_settings(self, tunnel_env):
        client = tunnel_from_env(8499, ["srv-a", "srv-b"])
        assert client is not None
        assert client._local_base_url == "http://127.0.0.1:8499/fluidmcp"
        assert client._local_token == "gateway-token"
        assert client._allowed_servers == {"srv-a", "srv-b"}

    @pytest.mark.parametrize("url", ["ws://engine.example.com/ws", "https://engine.example.com/ws"])
    def test_insecure_url_refused(self, tunnel_env, url):
        tunnel_env.setenv("FMCP_TUNNEL_URL", url)
        assert tunnel_from_env(8099) is None

    def test_plain_ws_allowed_for_localhost(self, tunnel_env):
        tunnel_env.setenv("FMCP_TUNNEL_URL", "ws://127.0.0.1:8765")
        assert tunnel_from_env(8099) is not None

    @pytest.mark.parametrize("name", ["FMCP_TUNNEL_TOKEN", "FMCP_TUNNEL_CONNECTOR_ID",
                                      "FMCP_TUNNEL_ALLOWED_SERVERS", "FMCP_TUNNEL_SERVER_PUBLIC_KEYS"])
    def test_missing_setting_refused(self, tunnel_env, name):
        tunnel_env.delenv(name)
        assert tunnel_from_env(8099) is None

    def test_missing_key_file_refused(self, tunnel_env, tmp_path):
        tunnel_env.setenv("FMCP_TUNNEL_KEY_PATH", str(tmp_path / "missing.key"))
        assert tunnel_from_env(8099) is None

    def test_key_file_readable_by_others_refused(self, tunnel_env, tmp_path):
        (tmp_path / "identity.key").chmod(0o644)
        assert tunnel_from_env(8099) is None

    @pytest.mark.parametrize("name,value", [("FMCP_TUNNEL_CONNECTOR_ID", "bad id"),
                                            ("FMCP_TUNNEL_SERVER_PUBLIC_KEYS", "not-base64"),
                                            ("FMCP_TUNNEL_MAX_CONCURRENCY", "many"),
                                            ("FMCP_TUNNEL_REQUEST_TIMEOUT", "soon")])
    def test_invalid_setting_refused(self, tunnel_env, name, value):
        tunnel_env.setenv(name, value)
        assert tunnel_from_env(8099) is None

    def test_gateway_token_only_in_secure_mode(self, tunnel_env):
        tunnel_env.delenv("FMCP_SECURE_MODE")
        assert tunnel_from_env(8499)._local_token is None

    def test_invalid_settings_do_not_log_the_token(self, tunnel_env):
        lines = []
        sink = logger.add(lambda message: lines.append(str(message)), level="DEBUG")
        tunnel_env.setenv("FMCP_TUNNEL_URL", f"ws://engine.example.com/?token={TOKEN}x")
        tunnel_env.setenv("FMCP_TUNNEL_TOKEN", "secret-tunnel-token")
        try:
            assert tunnel_from_env(8099) is None
        finally:
            logger.remove(sink)
        assert not any("secret-tunnel-token" in line for line in lines)


def test_health_reports_tunnel_without_changing_status():
    from fluidmcp.cli.services.run_servers import _add_health_endpoint

    class StubTunnel:
        def status(self):
            return {"enabled": True, "connected": False, "last_connected_at": None, "key_no": None}

    app = FastAPI()
    app.state.tunnel = StubTunnel()
    _add_health_endpoint(app)
    response = TestClient(app).get("/health")
    assert response.json()["tunnel"]["connected"] is False
    assert response.json()["status"] == "degraded"


def test_health_has_no_tunnel_field_when_disabled():
    from fluidmcp.cli.services.run_servers import _add_health_endpoint

    app = FastAPI()
    app.state.tunnel = None
    _add_health_endpoint(app)
    assert "tunnel" not in TestClient(app).get("/health").json()
