"""
Tests for JSON-RPC response correlation on stdio MCP subprocesses.

A real fake MCP server subprocess (FAKE_SERVER below) is driven through
StdioJsonRpcRouter and through the gateway's dynamic router. The fake server
can hold responses and later release them in an arbitrary order inside a
SINGLE stdout write, which reproduces the production failure patterns:

  * out-of-order responses (B before A)
  * a timed-out request whose late response arrives before the next response
  * several JSON-RPC messages in one stdout chunk

Invariant under test: a response is delivered only to the request whose
JSON-RPC ID it carries; anything else is dropped.
"""

import asyncio
import json
import random
import subprocess
import sys
import textwrap

import httpx
import pytest
from fastapi import FastAPI

from fluidmcp.cli.services import package_launcher
from fluidmcp.cli.services.package_launcher import create_dynamic_router, initialize_mcp_server
from fluidmcp.cli.services.stdio_jsonrpc import (
    StdioJsonRpcRouter,
    StdioProcessClosed,
    StdioRequestTimeout,
    get_stdio_router,
)


# Fake MCP server. Requests carry params.tag; the result echoes the tag and the
# wire ID the server saw. Control messages are notifications (no ID):
#   test/flush    {"order": [tags]}  — emit held responses in this order, ONE write
#   test/emit_raw {"data": str}      — write raw text to stdout
#   test/exit                        — exit (stdout EOF)
FAKE_SERVER = textwrap.dedent(r'''
    import json, sys
    held = {}
    received_replies = []

    def out(text):
        sys.stdout.write(text)
        sys.stdout.flush()

    for line in sys.stdin:
        msg = json.loads(line)
        method = msg.get("method")
        params = msg.get("params") or {}
        if method is None:                       # reply from the gateway to our request
            received_replies.append(msg)
            continue
        if "id" not in msg:                      # notification / control message
            if method == "test/flush":
                out("".join(json.dumps(held.pop(t)) + "\n" for t in params["order"]))
            elif method == "test/emit_raw":
                out(params["data"])
            elif method == "test/exit":
                sys.exit(0)
            continue
        if method == "initialize":
            out(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                            "result": {"protocolVersion": "2024-11-05", "capabilities": {},
                                       "serverInfo": {"name": "fake", "version": "0"}}}) + "\n")
            continue
        if method == "test/replies":
            out(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"replies": received_replies}}) + "\n")
            continue
        tag = params.get("tag")
        if params.get("error"):
            resp = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": "boom " + str(tag)}}
        else:
            resp = {"jsonrpc": "2.0", "id": msg["id"], "result": {"tag": tag, "wire_id": msg["id"]}}
        prefix = ""
        if params.get("progress"):
            token = params["_meta"]["progressToken"]
            prefix = json.dumps({"jsonrpc": "2.0", "method": "notifications/progress",
                                 "params": {"progressToken": token, "progress": 1}}) + "\n"
        if params.get("notify_first"):
            prefix += json.dumps({"jsonrpc": "2.0", "method": "notifications/message",
                                  "params": {"level": "info", "data": "hello"}}) + "\n"
        if params.get("hold"):
            held[tag] = resp
            if prefix:
                out(prefix)
        else:
            out(prefix + json.dumps(resp) + "\n")   # notification + response in ONE chunk
''')


@pytest.fixture
def fake_server_script(tmp_path):
    path = tmp_path / "fake_mcp_server.py"
    path.write_text(FAKE_SERVER)
    return path


@pytest.fixture
def spawn(fake_server_script):
    procs = []

    def _spawn():
        proc = subprocess.Popen(
            [sys.executable, "-u", str(fake_server_script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        procs.append(proc)
        return proc

    yield _spawn
    for proc in procs:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass


@pytest.fixture
def router(spawn):
    proc = spawn()
    return StdioJsonRpcRouter(proc, "fake")


def req(req_id, tag=None, **params):
    return {"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
            "params": {"tag": tag if tag is not None else req_id, **params}}


async def wait_for_stat(rtr, key, value, timeout=5.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while rtr.stats[key] < value:
        assert loop.time() < deadline, f"stats[{key!r}] never reached {value}: {rtr.stats}"
        await asyncio.sleep(0.01)


async def wait_for_pending(rtr, count, timeout=5.0):
    """Wait until `count` requests are registered (written to stdin)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while len(rtr._pending) < count:
        assert loop.time() < deadline
        await asyncio.sleep(0.01)


# ── Router-level tests ──────────────────────────────────────────────────────

class TestStdioRouterCorrelation:

    async def test_1_sequential_requests(self, router):
        for rid in ("A", "B", "C"):
            resp = await router.request(req(rid), timeout=5)
            assert resp["id"] == rid
            assert resp["result"]["tag"] == rid

    async def test_2_concurrent_requests_arbitrary_order(self, router):
        tasks = {rid: asyncio.ensure_future(router.request(req(rid, hold=True), timeout=5))
                 for rid in ("A", "B", "C", "D")}
        await wait_for_pending(router, 4)
        router.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["C", "A", "D", "B"]}})
        for rid, task in tasks.items():
            resp = await task
            assert resp["id"] == rid
            assert resp["result"]["tag"] == rid

    async def test_3_timeout_then_late_response_is_dropped(self, router):
        with pytest.raises(StdioRequestTimeout):
            await router.request(req("A", hold=True), timeout=0.3)
        assert router._pending == {}  # waiter removed on timeout

        # Late A arrives while nobody is waiting for it → dropped.
        router.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["A"]}})
        await wait_for_stat(router, "orphan_responses", 1)

        resp = await router.request(req("B"), timeout=5)
        assert resp["id"] == "B"
        assert resp["result"]["tag"] == "B"

    async def test_3b_late_response_in_same_chunk_before_next_response(self, router):
        """Production pattern: A times out, B is sent, then 'A\\nB\\n' arrive together."""
        with pytest.raises(StdioRequestTimeout):
            await router.request(req("A", hold=True), timeout=0.3)
        b = asyncio.ensure_future(router.request(req("B", hold=True), timeout=5))
        await wait_for_pending(router, 1)
        router.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["A", "B"]}})
        resp = await b
        assert resp["id"] == "B"
        assert resp["result"]["tag"] == "B"
        assert router.stats["orphan_responses"] == 1

    async def test_4_two_clients_same_client_ids(self, router):
        """Two clients both using id=1 (common for HTTP clients) must not collide."""
        c1 = asyncio.ensure_future(router.request(req(1, tag="client1", hold=True), timeout=5))
        c2 = asyncio.ensure_future(router.request(req(1, tag="client2", hold=True), timeout=5))
        await wait_for_pending(router, 2)
        router.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["client2", "client1"]}})
        r1, r2 = await c1, await c2
        assert (r1["id"], r1["result"]["tag"]) == (1, "client1")
        assert (r2["id"], r2["result"]["tag"]) == (1, "client2")
        # On the wire the gateway used distinct IDs.
        assert r1["result"]["wire_id"] != r2["result"]["wire_id"]

    async def test_5_error_response_routed_to_owner(self, router):
        a = asyncio.ensure_future(router.request(req("A", error=True, hold=True), timeout=5))
        b = asyncio.ensure_future(router.request(req("B", hold=True), timeout=5))
        await wait_for_pending(router, 2)
        router.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["A", "B"]}})
        ra, rb = await a, await b
        assert ra["id"] == "A" and ra["error"]["message"] == "boom A"
        assert rb["id"] == "B" and rb["result"]["tag"] == "B"

    async def test_6_notification_is_not_a_response(self, router):
        resp = await router.request(req("A", notify_first=True), timeout=5)
        assert resp["id"] == "A"
        assert "result" in resp
        assert router.stats["notifications"] == 1

    async def test_7_unknown_response_id_does_not_wake_waiter(self, router):
        a = asyncio.ensure_future(router.request(req("A", hold=True), timeout=5))
        await wait_for_pending(router, 1)
        for bad_id in ('"unknown-id"', "999999", "true", "null"):
            raw = '{"jsonrpc": "2.0", "id": %s, "result": {"tag": "intruder"}}\n' % bad_id
            router.notify({"jsonrpc": "2.0", "method": "test/emit_raw", "params": {"data": raw}})
        await wait_for_stat(router, "orphan_responses", 4)
        assert not a.done()
        router.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["A"]}})
        resp = await a
        assert resp["result"]["tag"] == "A"

    async def test_8_eof_fails_all_pending(self, router):
        tasks = [asyncio.ensure_future(router.request(req(rid, hold=True), timeout=10)) for rid in "ABC"]
        await wait_for_pending(router, 3)
        router.notify({"jsonrpc": "2.0", "method": "test/exit"})
        for task in tasks:
            with pytest.raises(StdioProcessClosed):
                await asyncio.wait_for(task, 5)
        assert router.closed
        assert router._pending == {}
        # New requests fail fast instead of hanging.
        with pytest.raises(StdioProcessClosed):
            await router.request(req("D"), timeout=5)

    async def test_9_ten_requests_randomized_order(self, router):
        ids = [f"r{i}" for i in range(10)]
        tasks = {rid: asyncio.ensure_future(router.request(req(rid, hold=True), timeout=5)) for rid in ids}
        await wait_for_pending(router, 10)
        order = ids[:]
        random.Random(1234).shuffle(order)
        router.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": order}})
        for rid, task in tasks.items():
            resp = await task
            assert resp["id"] == rid and resp["result"]["tag"] == rid

    async def test_10_many_messages_in_one_chunk_none_lost(self, router):
        ids = [f"m{i}" for i in range(50)]
        tasks = {rid: asyncio.ensure_future(router.request(req(rid, hold=True), timeout=5)) for rid in ids}
        await wait_for_pending(router, 50)
        # Interleave non-JSON log noise and a notification inside the same write.
        router.notify({"jsonrpc": "2.0", "method": "test/emit_raw",
                       "params": {"data": "log line on stdout\n" +
                                  '{"jsonrpc":"2.0","method":"notifications/message","params":{}}\n'}})
        router.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": list(reversed(ids))}})
        for rid, task in tasks.items():
            resp = await task
            assert resp["id"] == rid and resp["result"]["tag"] == rid
        assert router.stats["non_json_lines"] == 1
        assert router.stats["responses_matched"] == 50

    async def test_server_initiated_request_answered_not_routed(self, router):
        a = asyncio.ensure_future(router.request(req("A", hold=True), timeout=5))
        await wait_for_pending(router, 1)
        # Server → client requests reuse an ID that could collide with ours on the wire.
        wire_id = next(iter(router._pending))
        raw = (json.dumps({"jsonrpc": "2.0", "id": wire_id, "method": "ping"}) + "\n" +
               json.dumps({"jsonrpc": "2.0", "id": "s2", "method": "sampling/createMessage", "params": {}}) + "\n")
        router.notify({"jsonrpc": "2.0", "method": "test/emit_raw", "params": {"data": raw}})
        await wait_for_stat(router, "server_requests", 2)
        assert not a.done()
        router.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["A"]}})
        assert (await a)["result"]["tag"] == "A"

        replies = None
        for _ in range(100):  # replies are written from a helper thread
            replies = (await router.request({"jsonrpc": "2.0", "id": "q", "method": "test/replies"}, timeout=5))["result"]["replies"]
            if len(replies) == 2:
                break
            await asyncio.sleep(0.02)
        by_id = {r["id"]: r for r in replies}
        assert by_id[wire_id]["result"] == {}
        assert by_id["s2"]["error"]["code"] == -32601

    async def test_progress_notifications_routed_by_token(self, router):
        seen = []
        resp = await router.request(
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
             "params": {"tag": "P", "progress": True, "_meta": {"progressToken": "client-tok"}}},
            timeout=5, on_notification=seen.append,
        )
        assert resp["id"] == 7
        assert [n["params"]["progressToken"] for n in seen] == ["client-tok"]

    def test_request_sync_and_initialize(self, spawn):
        proc = spawn()
        assert initialize_mcp_server(proc, timeout=10, stderr_key="fake-init") is True
        rtr = get_stdio_router(proc)
        assert rtr.request_sync(req("S"), timeout=5)["result"]["tag"] == "S"
        with pytest.raises(StdioRequestTimeout):
            rtr.request_sync(req("T", hold=True), timeout=0.2)

    def test_single_router_per_process(self, spawn):
        proc = spawn()
        assert get_stdio_router(proc, "x") is get_stdio_router(proc, "x")


# ── Gateway-level tests (create_dynamic_router → /{server}/mcp) ─────────────

class _StubServerManager:
    def __init__(self, processes):
        self.processes = processes
        self.db = None

    def get_concurrency_semaphore(self, _name):
        return None

    async def update_last_used(self, _name):
        return None


@pytest.fixture
def gateway(spawn, monkeypatch):
    monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
    proc = spawn()
    app = FastAPI()
    app.include_router(create_dynamic_router(_StubServerManager({"fake": proc})))
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return client, get_stdio_router(proc, "fake")


class TestGatewayCorrelation:

    async def test_concurrent_http_clients_out_of_order(self, gateway):
        client, rtr = gateway
        async with client:
            a = asyncio.ensure_future(client.post("/fake/mcp", json=req(1, tag="A", hold=True)))
            b = asyncio.ensure_future(client.post("/fake/mcp", json=req(1, tag="B", hold=True)))
            await wait_for_pending(rtr, 2)
            rtr.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["B", "A"]}})
            ra, rb = (await a).json(), (await b).json()
        assert (ra["id"], ra["result"]["tag"]) == (1, "A")
        assert (rb["id"], rb["result"]["tag"]) == (1, "B")

    async def test_timeout_then_late_response_not_given_to_next_request(self, gateway, monkeypatch):
        """A → 504; late A arrives; B must receive B (the production bug)."""
        client, rtr = gateway
        monkeypatch.setattr(package_launcher, "_MCP_READ_TIMEOUT", 0.3)
        async with client:
            ra = await client.post("/fake/mcp", json=req("A", hold=True))
            assert ra.status_code == 504

            b = asyncio.ensure_future(client.post("/fake/mcp", json=req("B", hold=True)))
            await wait_for_pending(rtr, 1)
            rtr.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["A", "B"]}})
            rb = (await b).json()
        assert rb["id"] == "B"
        assert rb["result"]["tag"] == "B"
        assert rtr.stats["orphan_responses"] == 1

    async def test_client_notification_does_not_consume_a_response(self, gateway):
        client, rtr = gateway
        async with client:
            a = asyncio.ensure_future(client.post("/fake/mcp", json=req("A", hold=True)))
            await wait_for_pending(rtr, 1)
            rn = await client.post("/fake/mcp", json={"jsonrpc": "2.0", "method": "notifications/cancelled",
                                                      "params": {"requestId": "zzz"}})
            assert rn.status_code == 202
            rtr.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["A"]}})
            assert (await a).json()["result"]["tag"] == "A"

    async def test_tools_list_and_tools_call_endpoints(self, gateway):
        client, _rtr = gateway
        async with client:
            rl = await client.get("/fake/mcp/tools/list")
            assert rl.status_code == 200 and rl.json()["id"] == 1
            rc = await client.post("/fake/mcp/tools/call", json={"name": "t", "tag": "C"})
            assert rc.status_code == 200 and rc.json()["id"] == 2

    async def test_process_exit_returns_503(self, gateway):
        client, rtr = gateway
        async with client:
            a = asyncio.ensure_future(client.post("/fake/mcp", json=req("A", hold=True)))
            await wait_for_pending(rtr, 1)
            rtr.notify({"jsonrpc": "2.0", "method": "test/exit"})
            assert (await a).status_code == 503

    async def test_sse_stream_gets_only_its_response(self, gateway):
        client, rtr = gateway
        async with client:
            other = asyncio.ensure_future(client.post("/fake/mcp", json=req("X", hold=True)))
            sse = asyncio.ensure_future(client.post("/fake/sse", json={
                "jsonrpc": "2.0", "id": "S", "method": "tools/call",
                "params": {"tag": "S", "hold": True, "progress": True, "_meta": {"progressToken": "t1"}}}))
            await wait_for_pending(rtr, 2)
            rtr.notify({"jsonrpc": "2.0", "method": "test/flush", "params": {"order": ["X", "S"]}})
            events = [json.loads(line[6:]) for line in (await sse).text.splitlines() if line.startswith("data: ")]
            rx = (await other).json()
        assert events[0]["method"] == "notifications/progress"
        assert events[0]["params"]["progressToken"] == "t1"
        assert events[-1]["id"] == "S" and events[-1]["result"]["tag"] == "S"
        assert rx["id"] == "X" and rx["result"]["tag"] == "X"
