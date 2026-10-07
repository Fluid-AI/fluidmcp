"""Black-box response isolation under mixed-transport concurrent load."""

import asyncio
import json
import time
import uuid
from collections import Counter

import httpx
import pytest
from mcp import ClientSession
from mcp.client.sse import sse_client


TRANSPORTS = ("http", "stdio", "sse")


def rpc_result(response, request_id=None):
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text[:500]}"
    if "text/event-stream" in response.headers.get("content-type", ""):
        envelopes = [json.loads(line[6:]) for line in response.text.splitlines()
                     if line.startswith("data: ")]
        assert len(envelopes) == 1, f"Expected one response, got {envelopes!r}"
        body = envelopes[0]
    else:
        body = response.json()
    assert body.get("jsonrpc") == "2.0", body
    assert "id" in body, f"Missing JSON-RPC response ID: {body!r}"
    if request_id is not None:
        assert body["id"] == request_id, f"Wrong JSON-RPC response ID: {body!r}"
    assert "error" not in body, body
    assert "result" in body, body
    return body["result"]


async def run_load(gateway, concurrency, endpoint, id_mode):
    batch = uuid.uuid4().hex
    start = asyncio.Event()
    ready = asyncio.Queue()
    completed = {transport: [] for transport in TRANSPORTS}
    results = {transport: [] for transport in TRANSPORTS}
    inflight = {transport: 0 for transport in TRANSPORTS}
    peak = dict(inflight)
    timeout = httpx.Timeout(40, connect=5, pool=5)
    # Separate MCP sessions/headers per user; the shared TCP pool has room for
    # every simultaneous call and does not impose a hidden concurrency limit.
    limits = httpx.Limits(max_connections=3 * concurrency,
                         max_keepalive_connections=3 * concurrency)
    # Avoid idle-connection races while hundreds of sessions initialize, and
    # never reuse initialization connections after waiting at the barrier.
    initialization_limits = httpx.Limits(max_connections=3 * concurrency,
                                       max_keepalive_connections=0)
    async with (
        httpx.AsyncClient(timeout=timeout, trust_env=False, limits=initialization_limits) as client,
        httpx.AsyncClient(timeout=timeout, trust_env=False, limits=limits) as load_client,
    ):
        async def caller(transport, index):
            user = f"{batch}-{transport}-user-{index}"
            token = uuid.uuid4().hex
            rpc_id = 1 if id_mode == "reused" else token
            if endpoint == "tools-call":
                rpc_id = None  # This caller supplies no JSON-RPC envelope or ID.
            expected = {"user_id": user, "response_id": token, "batch": batch,
                        "delay": (5, 1, 4, 2, 3)[index % 5], "transport": transport}
            row = {"expected": expected, "rpc_id": rpc_id, "error": None}
            url = f"{gateway['url']}/{gateway['names'][transport]}/mcp"
            headers = {"Accept": "application/json, text/event-stream"}
            try:
                if endpoint == "jsonrpc":
                    response = await client.post(url, headers=headers, json={
                        "jsonrpc": "2.0", "id": "init", "method": "initialize",
                        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                   "clientInfo": {"name": user, "version": "1.0"}},
                    })
                    rpc_result(response, "init")
                    headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
                    headers["MCP-Protocol-Version"] = "2025-03-26"
                    response = await client.post(url, headers=headers, json={
                        "jsonrpc": "2.0", "method": "notifications/initialized",
                    })
                    assert response.status_code in (202, 204), response.text
            except Exception as exc:
                row["error"] = f"Initialization: {type(exc).__name__}: {exc}"
            finally:
                ready.put_nowait(None)
            await start.wait()
            if row["error"] is None:
                inflight[transport] += 1
                peak[transport] = max(peak[transport], inflight[transport])
                t0 = time.monotonic()
                try:
                    tool_call = {"name": "echo", "arguments": {
                        key: value for key, value in expected.items() if key != "transport"
                    }}
                    if endpoint == "tools-call":
                        url += "/tools/call"
                        payload = tool_call
                    else:
                        payload = {"jsonrpc": "2.0", "id": rpc_id,
                                   "method": "tools/call", "params": tool_call}
                    row["url"] = url
                    row["request_body"] = payload
                    response = await load_client.post(url, headers=headers, json=payload)
                    result = rpc_result(response, rpc_id)
                    assert not result.get("isError", False), result
                    content = result["content"]
                    assert len(content) == 1 and content[0]["type"] == "text", result
                    row["actual"] = json.loads(content[0]["text"])
                    assert row["actual"] == expected, (
                        f"CROSS-USER/REQUEST RESPONSE: expected={expected!r}, actual={row['actual']!r}"
                    )
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    row["elapsed"] = time.monotonic() - t0
                    inflight[transport] -= 1
                    completed[transport].append(token)
            results[transport].append(row)

        tasks = [asyncio.create_task(caller(transport, index))
                 for index in range(concurrency) for transport in TRANSPORTS]
        try:
            # All callers must be ready (including raw MCP initialization)
            # before any tool call starts. The convenience API needs no handshake.
            for _ in tasks:
                await asyncio.wait_for(ready.get(), timeout=45)
            start.set()
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    report = {"batch": batch, "endpoint": endpoint,
              "concurrency_per_transport": concurrency, "id_mode": id_mode,
              "client_peak": peak, "results": results, "completion_order": completed}
    path = gateway["artifacts"] / f"load-{endpoint}-{concurrency}-{id_mode}.json"
    path.write_text(json.dumps(report, indent=2))
    return report, path


@pytest.fixture(scope="module")
def load_report(gateway):
    return asyncio.run(run_load(gateway, *gateway["scenario"]))


def test_fake_sse_server_speaks_standard_mcp(gateway):
    """Control: establish that the same SSE fake works using the official SDK."""
    info = json.loads((gateway["artifacts"] / "sse-process.json").read_text())

    async def check():
        async with sse_client(f"http://127.0.0.1:{info['port']}/sse") as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                arguments = {"user_id": "control-user", "response_id": "control-id",
                             "batch": "control", "delay": 1}
                result = await session.call_tool("echo", arguments)
                assert not result.isError
                assert json.loads(result.content[0].text) == {**arguments, "transport": "sse"}

    asyncio.run(asyncio.wait_for(check(), timeout=15))


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_response_isolation(gateway, load_report, transport):
    report, path = load_report
    count = report["concurrency_per_transport"]
    rows = report["results"][transport]
    errors = sorted((row for row in rows if row["error"]),
                    key=lambda row: "CROSS-USER/REQUEST RESPONSE" not in row["error"])
    # Report each transport separately; SSE failure must not conceal HTTP/stdio results.
    assert len(rows) == count, f"Missing requests; report: {path}"
    assert not errors, (f"{len(errors)}/{count} {transport} requests failed; report: {path}\n"
                        + "\n".join(row["error"] for row in errors[:3]))
    assert report["client_peak"][transport] == count, f"Load was serialized; report: {path}"
    assert len({row["actual"]["response_id"] for row in rows}) == count, "Duplicate responses"

    journal = gateway["artifacts"] / f"{transport}.jsonl"
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    events = [event for event in events if event["batch"] == report["batch"]]
    starts = [event for event in events if event["event"] == "start"]
    finishes = [event for event in events if event["event"] == "finish"]
    expected_ids = Counter(row["expected"]["response_id"] for row in rows)
    assert Counter(event["response_id"] for event in starts) == expected_ids
    assert Counter(event["response_id"] for event in finishes) == expected_ids
    active = peak = 0
    for event in events:
        active += 1 if event["event"] == "start" else -1
        peak = max(peak, active)
    assert active == 0
    # Client concurrency is asserted exactly above. Arrival and completion can
    # overlap at the gateway, so backend peak need not equal the offered load.
    assert peak > 1, f"Fake server execution was serialized (peak={peak}); report: {path}"
    started_at = {event["response_id"]: event["time"] for event in starts}
    for event in finishes:
        assert event["time"] - started_at[event["response_id"]] >= event["delay"] - 0.01
    assert [event["response_id"] for event in starts] != [event["response_id"] for event in finishes], (
        "Responses never completed out of order; routing race was not exercised"
    )
    print(f"{report['endpoint']} / {transport}: {count}/{count} correctly routed, "
          f"backend peak={peak}; report: {path}")
