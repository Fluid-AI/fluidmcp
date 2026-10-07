"""Unit tests for the streamable-http proxy's JSON-RPC notification handling.

Regression coverage for a bug where a JSON-RPC *notification* (a request with
no "id", e.g. "notifications/initialized") sent through the streamable-http
gateway crashed: the upstream MCP server correctly acks notifications with an
empty-body 202, but the proxy unconditionally called `resp.json()`, raising
JSONDecodeError on the empty body. That became an opaque 500 (or blank
response) to the real client, breaking its handshake at stage 2 (initialize ->
notifications/initialized -> first real request).
"""
import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from fluidmcp.cli.services.package_launcher import _proxy_to_http_server


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_notification_ack_does_not_crash():
    """A notification (no "id") gets an empty-body 202 ack — must not raise."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert "id" not in json.loads(request.content)
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
            json={"jsonrpc": "2.0", "id": json.loads(request.content)["id"], "result": {"ok": True}},
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
        body = 'data: ' + json.dumps({"jsonrpc": "2.0", "id": json.loads(request.content)["id"],
                                     "result": {"tools": []}}) + '\n\n'
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


@pytest.mark.asyncio
async def test_concurrent_identical_ids_are_unique_upstream_and_restored():
    outgoing_ids = set()
    all_arrived = asyncio.Event()
    count = 100

    async def handler(request):
        body = json.loads(request.content)
        assert body["id"] != 1
        assert body["id"] not in outgoing_ids
        outgoing_ids.add(body["id"])
        if len(outgoing_ids) == count:
            all_arrived.set()
        await asyncio.wait_for(all_arrived.wait(), timeout=5)
        token = body["params"]["token"]
        await asyncio.sleep((count - token) / 10000)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                                         "result": {"token": token}})

    payloads = [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"token": i}}
                for i in range(count)]
    async with _mock_client(handler) as client:
        responses = await asyncio.gather(*(
            _proxy_to_http_server("http://localhost", payload, session_id="shared", client=client)
            for payload in payloads
        ))
    assert len(outgoing_ids) == count
    for i, (response, _) in enumerate(responses):
        assert response == {"jsonrpc": "2.0", "id": 1, "result": {"token": i}}
        assert payloads[i]["id"] == 1  # The helper must not mutate caller data.


@pytest.mark.asyncio
@pytest.mark.parametrize("original_id", [0, "client-request", None])
async def test_error_responses_restore_original_id(original_id):
    error = {"code": -32601, "message": "Unknown method"}

    def handler(request):
        body = json.loads(request.content)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "error": error})

    async with _mock_client(handler) as client:
        response, _ = await _proxy_to_http_server(
            "http://localhost", {"jsonrpc": "2.0", "id": original_id, "method": "unknown"}, client=client,
        )
    assert response == {"jsonrpc": "2.0", "id": original_id, "error": error}


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_wrong_upstream_id_is_rejected_before_restoring(streaming):
    def handler(request):
        body = {"jsonrpc": "2.0", "id": "another-request", "result": {"secret": "other-user"}}
        if streaming:
            return httpx.Response(200, text=f"data: {json.dumps(body)}\n\n",
                                  headers={"Content-Type": "text/event-stream"})
        return httpx.Response(200, json=body)

    async with _mock_client(handler) as client:
        with pytest.raises(HTTPException) as exc:
            await _proxy_to_http_server("http://localhost", {"id": 1, "method": "tools/list"}, client=client)
    assert exc.value.status_code == 502
    assert "secret" not in exc.value.detail


@pytest.mark.asyncio
async def test_sse_progress_and_multiline_data_are_not_mistaken_for_result():
    def handler(request):
        body = json.loads(request.content)
        result = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"ok": True}}, indent=2)
        stream = 'data: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n\n'
        stream += '\n'.join('data: ' + line for line in result.splitlines()) + '\n\n'
        return httpx.Response(200, text=stream, headers={"Content-Type": "text/event-stream"})

    async with _mock_client(handler) as client:
        response, _ = await _proxy_to_http_server("http://localhost", {"id": 1, "method": "tools/list"}, client=client)
    assert response == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
