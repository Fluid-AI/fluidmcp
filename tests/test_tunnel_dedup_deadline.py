"""
Request-id de-duplication and the end-to-end request deadline in the tunnel client.

Every test counts calls that reach the (mocked) local gateway, which stands in for an MCP tool
that changes state, such as sending an OTP.
"""

import asyncio
import contextlib
import json
import time

import httpx
import pytest

from fluidmcp.cli.tunnel.client import TunnelClient
from tests.test_tunnel_client import Gateway, send_raw, start_pair, stop_pair, wait_for


def call(tag, rpc_id=7):
    params = {"name": "send_otp", "arguments": {"tag": tag}}
    return {"jsonrpc": "2.0", "id": rpc_id, "method": "tools/call", "params": params}


def tag_of(request: httpx.Request) -> str:
    return json.loads(request.content)["params"]["arguments"]["tag"]


def calls(gateway, tag=None):
    return [r for r in gateway.requests if tag is None or tag_of(r) == tag]


async def send(server, request_id, body, target="srv-a"):
    await send_raw(server, json.dumps({"type": "request", "id": request_id, "server": target, "body": body}).encode())


def replies(server, request_id):
    return [m for m in server.received if m["id"] == request_id]


async def replies_for(server, request_id, count=1, timeout=5.0):
    await wait_for(lambda: len(replies(server, request_id)) >= count, timeout)
    return replies(server, request_id)


@contextlib.asynccontextmanager
async def tunnel(handler=None, **client_kwargs):
    gateway = Gateway(handler)
    server, client = await start_pair(gateway, **client_kwargs)
    try:
        await asyncio.wait_for(server.connected.wait(), 5)
        yield gateway, server, client
    finally:
        await stop_pair(server, client)


def blocking_handler(release: asyncio.Event):
    async def handler(request):
        await release.wait()
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 7, "result": {"tag": tag_of(request)}})

    return handler


def sleeping_handler(seconds_by_tag, default=0.0):
    async def handler(request):
        await asyncio.sleep(seconds_by_tag.get(tag_of(request), default))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 7, "result": {"tag": tag_of(request)}})

    return handler


# ---------------------------------------------------------------------------------------------
# Request-id de-duplication
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_01_sequential_duplicate_runs_once():
    async with tunnel() as (gateway, server, _):
        await send(server, "req-1", call("seq"))
        first = (await replies_for(server, "req-1"))[0]
        await send(server, "req-1", call("seq"))
        both = await replies_for(server, "req-1", 2)
        assert len(calls(gateway)) == 1
        assert both[1] == first and first["status"] == 200


@pytest.mark.asyncio
async def test_dedup_02_many_concurrent_duplicates_run_once_and_share_outcome():
    async with tunnel(sleeping_handler({}, default=0.2)) as (gateway, server, _):
        await asyncio.gather(*(send(server, "req-2", call("burst")) for _ in range(25)))
        received = await replies_for(server, "req-2", 25)
        assert len(calls(gateway)) == 1
        assert all(r == received[0] for r in received)
        assert received[0]["status"] == 200


@pytest.mark.asyncio
async def test_dedup_03_duplicates_during_execution_add_no_gateway_calls():
    release = asyncio.Event()
    async with tunnel(blocking_handler(release)) as (gateway, server, client):
        await send(server, "req-3", call("slow"))
        await wait_for(lambda: len(calls(gateway)) == 1)
        for _ in range(3):
            await send(server, "req-3", call("slow"))
        await asyncio.sleep(0.2)
        assert len(calls(gateway)) == 1
        assert replies(server, "req-3") == []  # still running; nobody got an answer early
        assert list(client._inflight) == ["req-3"]
        release.set()
        received = await replies_for(server, "req-3", 4)
        assert len(calls(gateway)) == 1
        assert {r["status"] for r in received} == {200}


@pytest.mark.asyncio
async def test_dedup_04_reused_id_with_different_payload_is_not_executed():
    release = asyncio.Event()
    async with tunnel(blocking_handler(release)) as (gateway, server, _):
        await send(server, "req-4", call("original"))
        await wait_for(lambda: len(calls(gateway)) == 1)
        # While the original runs: different arguments, then a different server.
        await send(server, "req-4", call("other"))
        await send(server, "req-4", call("original"), target="srv-b")
        conflicts = await replies_for(server, "req-4", 2)
        assert all(r == {"type": "error", "id": "req-4", "code": "duplicate_request", "reason": "payload_mismatch"}
                   for r in conflicts)
        release.set()
        await replies_for(server, "req-4", 3)
        # After it finished: different arguments again.
        await send(server, "req-4", call("other"))
        late = await replies_for(server, "req-4", 4)
        assert late[-1]["code"] == "duplicate_request"
        assert [tag_of(r) for r in calls(gateway)] == ["original"]


@pytest.mark.asyncio
async def test_dedup_05_different_ids_execute_independently():
    async with tunnel() as (gateway, server, _):
        # Same JSON-RPC id (GPT Engine may reuse it) under different tunnel ids: both run.
        await send(server, "req-5a", call("same", rpc_id=1))
        await send(server, "req-5b", call("same", rpc_id=1))
        # Tunnel ids are compared exactly: these are all different.
        for request_id in ("abc", "ABC", "abc "):
            await send(server, request_id, call(f"case-{request_id}"))
        # JSON-RPC ids 1 and "1" are forwarded unchanged and are not conflated.
        await send(server, "req-5c", call("num", rpc_id=1))
        await send(server, "req-5d", call("str", rpc_id="1"))
        for request_id in ("req-5a", "req-5b", "abc", "ABC", "abc ", "req-5c", "req-5d"):
            await replies_for(server, request_id)
        assert len(calls(gateway)) == 7
        forwarded_ids = {tag_of(r): json.loads(r.content)["id"] for r in calls(gateway)}
        assert forwarded_ids["num"] == 1 and forwarded_ids["str"] == "1"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["http_500", "read_error", "timeout"])
async def test_dedup_06_errors_and_timeouts_are_shared_by_duplicates(outcome):
    async def handler(request):
        if outcome == "http_500":
            error = {"code": -32000, "message": "tool failed"}
            return httpx.Response(500, json={"jsonrpc": "2.0", "id": 7, "error": error})
        if outcome == "read_error":
            raise httpx.ReadError("reset after send", request=request)
        await asyncio.sleep(1.0)
        return httpx.Response(200, json={})

    async with tunnel(handler, request_timeout=0.3) as (gateway, server, _):
        await send(server, "req-6", call(outcome))
        await send(server, "req-6", call(outcome))  # concurrent duplicate
        first_two = await replies_for(server, "req-6", 2)
        await send(server, "req-6", call(outcome))  # duplicate after completion
        received = await replies_for(server, "req-6", 3)
        assert received[0] == first_two[1] == received[2]
        expected = {"http_500": ("response", None), "read_error": ("error", "local_call_failed"),
                    "timeout": ("error", "local_timeout")}[outcome]
        assert (received[0]["type"], received[0].get("code")) == expected
        assert len(calls(gateway)) == 1


@pytest.mark.asyncio
async def test_dedup_07_cancelling_one_waiter_keeps_the_shared_call():
    release = asyncio.Event()
    async with tunnel(blocking_handler(release)) as (gateway, server, client):
        await send(server, "req-7", call("shared"))
        await wait_for(lambda: len(calls(gateway)) == 1)
        await send(server, "req-7", call("shared"))
        await wait_for(lambda: len(client._deliveries) == 2)
        operation = client._inflight["req-7"]
        waiter = next(iter(client._deliveries))
        waiter.cancel()
        await asyncio.sleep(0.05)
        assert not operation.task.done()
        release.set()
        received = await replies_for(server, "req-7", 1)
        await asyncio.sleep(0.1)
        assert len(replies(server, "req-7")) == 1  # the cancelled waiter sent nothing
        assert received[0]["status"] == 200
        assert operation.task.done() and not operation.task.cancelled()
        assert len(calls(gateway)) == 1


@pytest.mark.asyncio
async def test_dedup_08_inflight_ids_are_never_evicted(monkeypatch):
    monkeypatch.setattr(TunnelClient, "DEDUP_MAX_IDS", 3)
    release = asyncio.Event()

    async def handler(request):
        if tag_of(request) == "long":
            await release.wait()
        return httpx.Response(200, json={})

    async with tunnel(handler) as (gateway, server, client):
        await send(server, "long", call("long"))
        await wait_for(lambda: len(calls(gateway)) == 1)
        for request_id in ("done-1", "done-2"):
            await send(server, request_id, call(request_id))
            await replies_for(server, request_id)
        # Capacity is full (1 in flight + 2 completed): a new id is refused, not run, and nothing is evicted.
        await send(server, "new", call("new"))
        refused = (await replies_for(server, "new"))[0]
        assert refused == {"type": "error", "id": "new", "code": "not_delivered", "reason": "dedup_capacity"}
        assert "long" in client._inflight and set(client._completed) == {"done-1", "done-2"}
        await send(server, "long", call("long"))  # still recognised as in flight
        await send(server, "done-1", call("done-1"))  # still recognised as completed
        await replies_for(server, "done-1", 2)
        release.set()
        await replies_for(server, "long", 2)
        assert sorted(tag_of(r) for r in calls(gateway)) == ["done-1", "done-2", "long"]


@pytest.mark.asyncio
async def test_dedup_09_cache_limits_never_rerun_inside_the_window(monkeypatch):
    monkeypatch.setattr(TunnelClient, "DEDUP_MAX_RESULT_BYTES", 400)  # room for one reply (~303 bytes)

    async with tunnel() as (gateway, server, client):
        for request_id in ("r-1", "r-2", "r-3"):
            await send(server, request_id, call(request_id))
            await replies_for(server, request_id)
        assert client._result_bytes <= 400 and list(client._results) == ["r-3"]
        # r-1's reply body was dropped to respect the limit, but its id is still remembered: not run again.
        await send(server, "r-1", call("r-1"))
        expired = (await replies_for(server, "r-1", 2))[1]
        assert expired == {"type": "error", "id": "r-1", "code": "duplicate_request", "reason": "outcome_expired"}
        await send(server, "r-3", call("r-3"))
        assert (await replies_for(server, "r-3", 2))[1]["status"] == 200  # still cached
        assert len(calls(gateway)) == 3

        # Outside the documented window an id is forgotten and treated as new.
        monkeypatch.setattr(TunnelClient, "DEDUP_WINDOW", 0.2)
        await asyncio.sleep(0.3)
        await send(server, "r-2", call("r-2"))
        await replies_for(server, "r-2", 2)
        assert set(client._completed) == {"r-2"} and client._result_bytes <= 400
        assert len(calls(gateway, "r-2")) == 2


@pytest.mark.asyncio
async def test_dedup_10_duplicate_after_reconnect_gets_the_original_outcome():
    release = asyncio.Event()
    async with tunnel(blocking_handler(release)) as (gateway, server, client):
        await send(server, "req-10", call("across"))
        await wait_for(lambda: len(calls(gateway)) == 1)
        await server._ws.close(1012)
        await wait_for(lambda: not server.connected.is_set())
        await asyncio.wait_for(server.connected.wait(), 5)
        assert "req-10" in client._inflight  # the call continues without its connection

        await send(server, "req-10", call("across"))  # resent on the new connection
        await asyncio.sleep(0.1)
        assert len(calls(gateway)) == 1
        release.set()
        received = await replies_for(server, "req-10", 1)
        assert received[-1]["status"] == 200
        await send(server, "req-10", call("across"))
        assert (await replies_for(server, "req-10", 2))[-1] == received[-1]
        assert len(calls(gateway)) == 1


# ---------------------------------------------------------------------------------------------
# End-to-end deadline (queue wait + gateway call)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deadline_01_expired_in_queue_never_reaches_gateway():
    release = asyncio.Event()
    async with tunnel(blocking_handler(release), max_concurrency=1, request_timeout=5.0) as (gateway, server, client):
        await send(server, "holder", call("holder"))
        await wait_for(lambda: len(calls(gateway)) == 1)
        client._request_timeout = 0.4  # deadlines are fixed on acceptance; this one applies to "queued"
        await send(server, "queued", call("queued"))
        reply = (await replies_for(server, "queued"))[0]
        assert reply == {"type": "error", "id": "queued", "code": "not_delivered", "reason": "queue_timeout"}
        assert calls(gateway, "queued") == []
        release.set()


@pytest.mark.asyncio
async def test_deadline_02_late_slot_gets_only_the_remaining_time():
    handler = sleeping_handler({"first": 0.3, "second": 5.0})
    async with tunnel(handler, max_concurrency=1, request_timeout=1.0) as (gateway, server, _):
        await send(server, "first", call("first"))
        started = time.monotonic()
        await send(server, "second", call("second"))
        reply = (await replies_for(server, "second"))[0]
        elapsed = time.monotonic() - started
        assert reply["code"] == "local_timeout"  # it got a slot and reached the gateway
        assert len(calls(gateway, "second")) == 1
        assert 0.9 <= elapsed < 1.25, elapsed  # 1.0 s from acceptance, not 0.3 s queue + 1.0 s


@pytest.mark.asyncio
async def test_deadline_02b_slot_with_almost_no_time_left_is_not_used():
    # Both requests have the same 0.4 s timeout. "holder" expires first and frees the slot when "queued"
    # has only milliseconds left; starting the call then would only produce an unknown outcome.
    release = asyncio.Event()
    async with tunnel(blocking_handler(release), max_concurrency=1, request_timeout=0.4) as (gateway, server, _):
        await send(server, "holder", call("holder"))
        await wait_for(lambda: len(calls(gateway)) == 1)
        await send(server, "queued", call("queued"))
        assert (await replies_for(server, "holder"))[0]["code"] == "local_timeout"
        reply = (await replies_for(server, "queued"))[0]
        assert reply == {"type": "error", "id": "queued", "code": "not_delivered", "reason": "queue_timeout"}
        assert calls(gateway, "queued") == []
        release.set()


@pytest.mark.asyncio
async def test_deadline_03_completes_within_total_deadline():
    async with tunnel(sleeping_handler({"ok": 0.3}), max_concurrency=1, request_timeout=1.0) as (gateway, server, _):
        await send(server, "a", call("ok"))
        await send(server, "b", call("ok"))  # queued 0.3 s, runs 0.3 s: within 1.0 s
        assert (await replies_for(server, "a"))[0]["status"] == 200
        assert (await replies_for(server, "b"))[0]["status"] == 200


@pytest.mark.asyncio
async def test_deadline_04_gateway_slower_than_deadline_reports_local_timeout():
    async with tunnel(sleeping_handler({"slow": 2.0}), request_timeout=0.3) as (gateway, server, _):
        await send(server, "slow", call("slow"))
        reply = (await replies_for(server, "slow"))[0]
        assert reply == {"type": "error", "id": "slow", "code": "local_timeout"}  # may have run: no "not_delivered"
        assert len(calls(gateway)) == 1


@pytest.mark.asyncio
async def test_deadline_05_late_gateway_answer_does_not_rerun():
    finished = []

    async def handler(request):
        await asyncio.sleep(0.5)
        finished.append(tag_of(request))
        return httpx.Response(200, json={})

    async with tunnel(handler, request_timeout=0.2) as (gateway, server, _):
        await send(server, "late", call("late"))
        assert (await replies_for(server, "late"))[0]["code"] == "local_timeout"
        await asyncio.sleep(0.5)  # the gateway call would have finished by now
        await send(server, "late", call("late"))
        assert (await replies_for(server, "late", 2))[1]["code"] == "local_timeout"
        assert len(calls(gateway)) == 1


@pytest.mark.asyncio
async def test_deadline_06_slots_are_released_on_every_path():
    release = asyncio.Event()

    async def handler(request):
        tag = tag_of(request)
        if tag == "timeout":
            await asyncio.sleep(5)
        elif tag == "error":
            raise httpx.ReadError("reset", request=request)
        elif tag == "cancel":
            await release.wait()
        return httpx.Response(200, json={})

    async with tunnel(handler, max_concurrency=2, request_timeout=0.3) as (gateway, server, client):
        await send(server, "timeout", call("timeout"))
        await send(server, "error", call("error"))
        await replies_for(server, "timeout")
        await replies_for(server, "error")
        assert client._semaphore._value == 2

        client._request_timeout = 5.0  # applies to the next accepted request
        await send(server, "cancel", call("cancel"))
        await wait_for(lambda: len(calls(gateway, "cancel")) == 1)
        assert client._semaphore._value == 1
        client._inflight["cancel"].task.cancel()
        await wait_for(lambda: "cancel" not in client._inflight)
        assert client._semaphore._value == 2

        # Both slots are usable again.
        await send(server, "after-1", call("after-1"))
        await send(server, "after-2", call("after-2"))
        assert (await replies_for(server, "after-1"))[0]["status"] == 200
        assert (await replies_for(server, "after-2"))[0]["status"] == 200
        # A duplicate of the cancelled call is not run again.
        await send(server, "cancel", call("cancel"))
        assert (await replies_for(server, "cancel"))[0]["reason"] == "outcome_expired"
        assert len(calls(gateway, "cancel")) == 1


@pytest.mark.asyncio
async def test_deadline_06b_cancelled_while_queued_never_runs_and_leaks_no_slot():
    release = asyncio.Event()
    async with tunnel(blocking_handler(release), max_concurrency=1, request_timeout=5.0) as (gateway, server, client):
        await send(server, "holder", call("holder"))
        await wait_for(lambda: len(calls(gateway)) == 1)
        await send(server, "queued", call("queued"))
        await wait_for(lambda: "queued" in client._inflight)
        await asyncio.sleep(0.05)
        client._inflight["queued"].task.cancel()
        await wait_for(lambda: "queued" not in client._inflight)
        release.set()
        await replies_for(server, "holder")
        await asyncio.sleep(0.2)
        assert client._semaphore._value == 1
        assert [tag_of(r) for r in calls(gateway)] == ["holder"]


@pytest.mark.asyncio
async def test_deadline_07_duplicates_share_the_original_deadline():
    async with tunnel(sleeping_handler({"shared": 5.0}), request_timeout=0.6) as (gateway, server, _):
        started = time.monotonic()
        await send(server, "dl-7", call("shared"))
        await asyncio.sleep(0.4)
        await send(server, "dl-7", call("shared"))
        received = await replies_for(server, "dl-7", 2)
        elapsed = time.monotonic() - started
        assert [r["code"] for r in received] == ["local_timeout", "local_timeout"]
        assert elapsed < 0.9, elapsed  # the duplicate did not restart the 0.6 s clock
        assert len(calls(gateway)) == 1


@pytest.mark.asyncio
async def test_deadline_08_expired_queued_request_never_runs_after_a_slot_frees():
    release = asyncio.Event()
    async with tunnel(blocking_handler(release), max_concurrency=1, request_timeout=5.0) as (gateway, server, client):
        await send(server, "holder", call("holder"))
        await wait_for(lambda: len(calls(gateway)) == 1)
        client._request_timeout = 0.3
        await send(server, "queued", call("queued"))
        assert (await replies_for(server, "queued"))[0]["code"] == "not_delivered"
        release.set()  # the slot frees after the queued request expired
        await replies_for(server, "holder")
        await asyncio.sleep(0.3)
        assert [tag_of(r) for r in calls(gateway)] == ["holder"]
        assert client._semaphore._value == 1


@pytest.mark.asyncio
async def test_deadline_09_never_delivered_is_still_retried_locally_and_reported_safe(monkeypatch):
    monkeypatch.setattr(TunnelClient, "LOCAL_CONNECT_RETRY", 5.0)
    attempts = []

    def handler(request):
        attempts.append(tag_of(request))
        if tag_of(request) == "starting" and len(attempts) < 3:
            raise httpx.ConnectError("refused", request=request)  # gateway not listening yet
        if tag_of(request) == "down":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={})

    async with tunnel(handler, request_timeout=1.2) as (gateway, server, _):
        await send(server, "starting", call("starting"))
        assert (await replies_for(server, "starting", timeout=5))[0]["status"] == 200
        assert attempts.count("starting") == 3  # refused connections are retried: nothing was sent

        await send(server, "down", call("down"))
        reply = (await replies_for(server, "down", timeout=5))[0]
        assert reply == {"type": "error", "id": "down", "code": "not_delivered", "reason": "gateway_unreachable"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["read_error", "remote_protocol_error", "write_error", "read_timeout"])
async def test_deadline_10_possibly_delivered_calls_are_never_retried(failure):
    def handler(request):
        exc = {"read_error": httpx.ReadError, "remote_protocol_error": httpx.RemoteProtocolError,
               "write_error": httpx.WriteError, "read_timeout": httpx.ReadTimeout}[failure]
        raise exc("failed after the request may have been sent", request=request)

    async with tunnel(handler) as (gateway, server, _):
        await send(server, "maybe", call("maybe"))
        reply = (await replies_for(server, "maybe"))[0]
        assert reply["code"] == ("local_timeout" if failure == "read_timeout" else "local_call_failed")
        await send(server, "maybe", call("maybe"))  # GPT Engine re-sending the id must not re-run it
        await replies_for(server, "maybe", 2)
        assert len(calls(gateway)) == 1
