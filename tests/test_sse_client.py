"""Lifecycle regressions for the persistent SSE session owner."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from fluidmcp.cli.services import sse_client as module


@pytest.fixture
def session_factory(monkeypatch):
    entered = []
    exited = []
    initialize_gate = asyncio.Event()
    initialize_gate.set()

    @asynccontextmanager
    async def transport(url):
        entered.append(("transport", asyncio.current_task()))
        try:
            yield (None, None)
        finally:
            exited.append(("transport", asyncio.current_task()))

    class Session:
        notifications = []

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            entered.append(("session", asyncio.current_task()))
            return self

        async def __aexit__(self, *args):
            exited.append(("session", asyncio.current_task()))

        async def initialize(self):
            await initialize_gate.wait()

        async def send_notification(self, message):
            self.notifications.append(message.method)

    monkeypatch.setattr(module, "sse_client", transport)
    monkeypatch.setattr(module, "ClientSession", Session)
    return entered, exited, initialize_gate, Session


@pytest.mark.asyncio
async def test_concurrent_start_uses_one_session_and_closes_in_owner_task(session_factory):
    entered, exited, _, _ = session_factory
    client = module.SseJsonRpcClient("http://localhost")
    sessions = await asyncio.gather(*(client.start() for _ in range(20)))
    assert all(session is sessions[0] for session in sessions)
    assert len(entered) == 2
    # Shutdown from a different task must not exit SDK cancel scopes in that task.
    await asyncio.create_task(client.aclose())
    assert exited == list(reversed(entered))
    with pytest.raises(ConnectionError, match="closed"):
        await client.start()


@pytest.mark.asyncio
async def test_cancelled_start_waiter_does_not_cancel_shared_initialization(session_factory):
    entered, exited, gate, _ = session_factory
    gate.clear()
    client = module.SseJsonRpcClient("http://localhost")
    first = asyncio.create_task(client.start())
    second = asyncio.create_task(client.start())
    try:
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        gate.set()
        assert await asyncio.wait_for(second, 1) is not None
        assert len(entered) == 2
    finally:
        await client.aclose()
    assert exited == list(reversed(entered))


@pytest.mark.asyncio
async def test_initialization_failure_reaches_waiters_and_cleans_up(monkeypatch, session_factory):
    entered, exited, _, Session = session_factory

    async def fail(self):
        raise RuntimeError("handshake failed")

    monkeypatch.setattr(Session, "initialize", fail)
    client = module.SseJsonRpcClient("http://localhost")
    try:
        with pytest.raises(ConnectionError, match="handshake failed"):
            await asyncio.wait_for(client.start(), 1)
    finally:
        await client.aclose()
    assert exited == list(reversed(entered))


@pytest.mark.asyncio
async def test_unscoped_cancellation_cannot_cancel_another_sdk_request(session_factory):
    _, _, _, Session = session_factory
    client = module.SseJsonRpcClient("http://localhost")
    try:
        assert await client.request({"method": "notifications/cancelled", "params": {"requestId": 1}}) is None
        assert Session.notifications == []
        assert await client.request({"method": "notifications/roots/list_changed"}) is None
        assert Session.notifications == ["notifications/roots/list_changed"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_failed_sse_handshake_closes_session_reaps_process_and_releases_port(monkeypatch):
    from fluidmcp.cli.services import server_manager as managers

    @asynccontextmanager
    async def stream(*args, **kwargs):
        yield SimpleNamespace(status_code=200)

    @asynccontextmanager
    async def http_client(*args, **kwargs):
        yield SimpleNamespace(stream=stream)

    handle = SimpleNamespace(
        sse_client=SimpleNamespace(start=AsyncMock(side_effect=RuntimeError("bad handshake"))),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr(managers.httpx, "AsyncClient", http_client)
    monkeypatch.setattr(managers, "NetworkSubprocessHandle", lambda **kwargs: handle)
    manager = SimpleNamespace(configs={}, _release_port=Mock())
    process = Mock()
    process.poll.return_value = None
    with pytest.raises(RuntimeError, match="bad handshake"):
        await managers.ServerManager._handshake_sse_subprocess(manager, "test", 8500, process)
    handle.aclose.assert_awaited_once()
    process.kill.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
    manager._release_port.assert_called_once_with(8500)
