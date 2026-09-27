"""Unit tests for the streamable-http proxy's JSON-RPC notification handling.

Regression coverage for a bug where a JSON-RPC *notification* (a request with
no "id", e.g. "notifications/initialized") sent through the streamable-http
gateway crashed: the upstream MCP server correctly acks notifications with an
empty-body 202, but the proxy unconditionally called `resp.json()`, raising
JSONDecodeError on the empty body. That became an opaque 500 (or blank
response) to the real client, breaking its handshake at stage 2 (initialize ->
notifications/initialized -> first real request).
"""
import httpx
import pytest

from fluidmcp.cli.services.package_launcher import _proxy_to_http_server


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_notification_ack_does_not_crash():
    """A notification (no "id") gets an empty-body 202 ack — must not raise."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, content=b"")

    client = _mock_client(handler)
    try:
        response, session_id = await _proxy_to_http_server(
            "http://127.0.0.1:9999",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            client=client,
        )
    finally:
        await client.aclose()

    assert response is None
    assert session_id is None


@pytest.mark.asyncio
async def test_notification_ack_propagates_session_header():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, content=b"", headers={"Mcp-Session-Id": "sess-123"})

    client = _mock_client(handler)
    try:
        response, session_id = await _proxy_to_http_server(
            "http://127.0.0.1:9999",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            client=client,
        )
    finally:
        await client.aclose()

    assert response is None
    assert session_id == "sess-123"


@pytest.mark.asyncio
async def test_regular_request_returns_parsed_body_and_session_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}},
            headers={"Mcp-Session-Id": "sess-abc"},
        )

    client = _mock_client(handler)
    try:
        response, session_id = await _proxy_to_http_server(
            "http://127.0.0.1:9999",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            client=client,
        )
    finally:
        await client.aclose()

    assert response == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    assert session_id == "sess-abc"


@pytest.mark.asyncio
async def test_sse_envelope_still_unwrapped_for_regular_requests():
    def handler(request: httpx.Request) -> httpx.Response:
        body = 'data: {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}\n\n'
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = _mock_client(handler)
    try:
        response, session_id = await _proxy_to_http_server(
            "http://127.0.0.1:9999",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            client=client,
        )
    finally:
        await client.aclose()

    assert response == {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}
    assert session_id is None


@pytest.mark.asyncio
async def test_session_id_header_sent_when_provided():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["mcp-session-id"] = request.headers.get("mcp-session-id")
        return httpx.Response(202, content=b"")

    client = _mock_client(handler)
    try:
        await _proxy_to_http_server(
            "http://127.0.0.1:9999",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            session_id="existing-session",
            client=client,
        )
    finally:
        await client.aclose()

    assert captured["mcp-session-id"] == "existing-session"
