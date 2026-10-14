"""
Outbound tunnel client.

Keeps one authenticated, encrypted WebSocket open to GPT Engine and forwards the MCP
requests it receives to this gateway's own /{server}/mcp route on localhost.
"""

import asyncio
import hashlib
import json
import random
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Set, Tuple

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from loguru import logger
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from . import metrics
from .protocol import (
    HANDSHAKE_TIMEOUT,
    MAX_FRAME,
    ClientHandshake,
    ControlMessage,
    Env,
    ProtocolError,
    SecureChannel,
)


class TunnelAuthError(Exception):
    """GPT Engine rejected the token or the handshake; retrying quickly would not help."""


@dataclass
class _Operation:
    """One accepted request id. Every message carrying that id shares `task` and its outcome."""

    fingerprint: str
    task: asyncio.Task


@dataclass
class _Completed:
    fingerprint: str
    finished_at: float


class _Connection:
    """An established tunnel: socket, encrypted channel and the lock that keeps records in order."""

    def __init__(self, ws: ClientConnection, channel: SecureChannel):
        self.ws = ws
        self.channel = channel
        self.lock = asyncio.Lock()

    async def send(self, message: Dict[str, Any]) -> None:
        data = json.dumps(message, separators=(",", ":")).encode("utf-8")
        async with self.lock:
            await self.ws.send(self.channel.encrypt(data))


class TunnelClient:
    """Background tunnel to GPT Engine with automatic reconnect."""

    TICK_INTERVAL = 5.0
    PING_INTERVAL = 20.0
    MAX_BACKOFF = 60.0
    STABLE_AFTER = 30.0
    LOCAL_CONNECT_RETRY = 10.0
    # A request id is never executed twice while it is in flight, or for DEDUP_WINDOW seconds after it
    # finished (within this process). New ids are refused, not executed, if that would exceed DEDUP_MAX_IDS.
    DEDUP_WINDOW = 600.0
    DEDUP_MAX_IDS = 50_000
    # Finished replies kept for duplicates; beyond this the oldest bodies are dropped (the ids are kept).
    DEDUP_MAX_RESULT_BYTES = 64 * 1024 * 1024
    MAX_REQUEST_ID_LEN = 128
    # A request that gets a concurrency slot with less time left than this is not sent to the gateway.
    MIN_CALL_TIME = 0.5

    def __init__(
        self,
        url: str,
        token: str,
        connector_id: str,
        allowed_servers: Sequence[str],
        server_public_keys: Sequence[bytes],
        identity_key: Ed25519PrivateKey,
        local_base_url: str,
        local_token: Optional[str] = None,
        max_concurrency: int = 20,
        request_timeout: float = 45.0,
        version: str = "unknown",
        env: Env = Env(),
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self._url = url
        self._token = token
        self._connector_id = connector_id
        self._allowed_servers = frozenset(allowed_servers)
        self._server_public_keys = tuple(server_public_keys)
        self._identity_key = identity_key
        self._local_base_url = local_base_url.rstrip("/")
        self._local_token = local_token
        self._request_timeout = request_timeout
        self._version = version
        self._env = env
        self._transport = transport
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._deliveries: Set[asyncio.Task] = set()
        self._inflight: Dict[str, _Operation] = {}
        self._completed: "OrderedDict[str, _Completed]" = OrderedDict()
        self._results: "OrderedDict[str, Tuple[Dict[str, Any], int]]" = OrderedDict()
        self._result_bytes = 0
        self._task: Optional[asyncio.Task] = None
        self._connection: Optional[_Connection] = None
        self._last_connected_at: Optional[float] = None
        self._log = logger.bind(component="tunnel", connector=connector_id)

    def start(self) -> None:
        """Start the tunnel in the background."""
        if self.is_running():
            return
        self._task = asyncio.create_task(self._run())
        self._log.info(f"Tunnel client started ({self._url}, servers: {', '.join(sorted(self._allowed_servers))})")

    async def stop(self) -> None:
        """Stop the tunnel and close the connection."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        # Calls that outlived their connection keep running until their deadline; stop them now.
        operations = [op.task for op in self._inflight.values()]
        for task in operations:
            task.cancel()
        await asyncio.gather(*operations, return_exceptions=True)
        self._log.info("Tunnel client stopped")

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> Dict[str, Any]:
        """Tunnel state for /health."""
        last = self._last_connected_at
        return {
            "enabled": True,
            "connected": self._connection is not None,
            "last_connected_at": datetime.fromtimestamp(last, timezone.utc).isoformat() if last else None,
            "key_no": self._connection.channel.key_no if self._connection else None,
        }

    async def _run(self) -> None:
        backoff = 1.0
        async with httpx.AsyncClient(transport=self._transport, timeout=self._request_timeout) as http:
            while True:
                started = time.monotonic()
                try:
                    await self._session(http)
                    self._log.warning("Tunnel closed by GPT Engine; reconnecting")
                except TunnelAuthError as e:
                    metrics.record_handshake_failure()
                    self._log.error(f"Tunnel rejected: {e}. Check the tunnel token and keys; retrying in {self.MAX_BACKOFF:.0f}s")
                    backoff = self.MAX_BACKOFF
                except ProtocolError as e:
                    self._log.warning(f"Tunnel protocol error ({e.code}); reconnecting")
                except Exception as e:
                    # Never let the tunnel take the gateway down; keep retrying.
                    self._log.warning(f"Tunnel connection failed: {type(e).__name__}: {e}")
                if time.monotonic() - started >= self.STABLE_AFTER:
                    backoff = 1.0
                await asyncio.sleep(backoff + random.uniform(0, 1))
                backoff = min(backoff * 2, self.MAX_BACKOFF)

    async def _session(self, http: httpx.AsyncClient) -> None:
        headers = {"Authorization": f"Bearer {self._token}", "X-Connector-Id": self._connector_id}
        try:
            ws = await connect(
                self._url,
                additional_headers=headers,
                compression=None,
                max_size=MAX_FRAME,
                open_timeout=HANDSHAKE_TIMEOUT,
                ping_interval=self.PING_INTERVAL,
                ping_timeout=self.PING_INTERVAL,
            )
        except InvalidStatus as e:
            if e.response.status_code in (401, 403):
                raise TunnelAuthError(f"HTTP {e.response.status_code}") from None
            raise

        async with ws:
            try:
                channel = await asyncio.wait_for(self._handshake(ws), HANDSHAKE_TIMEOUT)
            except (ProtocolError, ConnectionClosed, asyncio.TimeoutError) as e:
                await ws.close(1008)
                reason = e.code if isinstance(e, ProtocolError) else type(e).__name__
                raise TunnelAuthError(f"handshake failed ({reason})") from None

            conn = _Connection(ws, channel)
            await conn.send({
                "type": "hello",
                "protocol": 1,
                "version": self._version,
                "connector": self._connector_id,
                "servers": sorted(self._allowed_servers),
            })
            self._connection = conn
            self._last_connected_at = time.time()
            metrics.set_connected(True)
            self._log.info("Tunnel connected")

            tasks = [asyncio.create_task(self._receive(conn, http)), asyncio.create_task(self._tick(conn))]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            except ProtocolError:
                await ws.close(1008)
                raise
            finally:
                # Only the replies tied to this connection stop. Operations already accepted run to their
                # deadline, so a duplicate of the same id after a reconnect gets their outcome.
                for task in tasks + list(self._deliveries):
                    task.cancel()
                self._connection = None
                metrics.set_connected(False)

    async def _handshake(self, ws: ClientConnection) -> SecureChannel:
        handshake = ClientHandshake(self._identity_key, self._server_public_keys, self._connector_id, self._env)
        await ws.send(handshake.start())
        server_hello = await ws.recv()
        if not isinstance(server_hello, bytes):
            raise ProtocolError("text_frame")
        client_finish, channel = handshake.receive_server_hello(server_hello)
        await ws.send(client_finish)
        return channel

    async def _tick(self, conn: _Connection) -> None:
        while True:
            await asyncio.sleep(self.TICK_INTERVAL)
            async with conn.lock:
                conn.channel.check_timers()
                if conn.channel.needs_rekey():
                    await conn.ws.send(conn.channel.start_rekey())

    async def _receive(self, conn: _Connection, http: httpx.AsyncClient) -> None:
        async for frame in conn.ws:
            async with conn.lock:
                message = conn.channel.decrypt(frame)
            if isinstance(message, ControlMessage):
                self._log.debug(f"Tunnel keys rotated (key {message.key_no})")
                continue
            try:
                request = json.loads(message)
            except ValueError:
                self._log.warning("Ignoring tunnel message that is not valid JSON")
                continue
            if not isinstance(request, dict) or request.get("type") != "request":
                continue
            request_id = request.get("id")
            if not isinstance(request_id, str) or not 0 < len(request_id) <= self.MAX_REQUEST_ID_LEN:
                self._log.warning("Ignoring tunnel request without a valid id")
                continue
            self._dispatch(conn, http, request_id, request)

    def _dispatch(self, conn: _Connection, http: httpx.AsyncClient, request_id: str, request: Dict[str, Any]) -> None:
        """
        Start the request, or attach to the operation already started for its id.

        Synchronous on purpose: the lookup and the registration of a new operation cannot be
        interleaved with another message, so one id can only ever start one operation.
        """
        fingerprint = _fingerprint(request)
        self._expire_completed()

        operation = self._inflight.get(request_id)
        if operation is not None:
            if operation.fingerprint != fingerprint:
                self._reply_later(conn, self._duplicate_error(request_id, request, "payload_mismatch"))
            else:
                self._log.info(f"Duplicate tunnel request {request_id}: waiting for the original call")
                metrics.record_duplicate(self._server_label(request))
                self._deliver(conn, request_id, operation)
            return

        completed = self._completed.get(request_id)
        if completed is not None:
            if completed.fingerprint != fingerprint:
                self._reply_later(conn, self._duplicate_error(request_id, request, "payload_mismatch"))
            elif request_id in self._results:
                self._log.info(f"Duplicate tunnel request {request_id}: returning the original outcome")
                metrics.record_duplicate(self._server_label(request))
                self._reply_later(conn, self._results[request_id][0])
            else:
                self._reply_later(conn, self._duplicate_error(request_id, request, "outcome_expired"))
            return

        if len(self._inflight) + len(self._completed) >= self.DEDUP_MAX_IDS:
            # Evicting a remembered id could let a duplicate run again; refuse the new id instead.
            self._log.warning(f"Tunnel request {request_id} refused: duplicate-protection capacity reached")
            metrics.record_request(self._server_label(request), "not_delivered", 0.0)
            self._reply_later(conn, _not_delivered(request_id, "dedup_capacity"))
            return

        # The deadline starts when the request is accepted, so time spent queued counts against it.
        deadline = time.monotonic() + self._request_timeout
        operation = _Operation(fingerprint, asyncio.create_task(self._execute(http, request_id, request, deadline)))
        self._inflight[request_id] = operation
        operation.task.add_done_callback(lambda task: self._finish(request_id, operation))
        self._deliver(conn, request_id, operation)

    def _finish(self, request_id: str, operation: _Operation) -> None:
        """Move a finished operation to the completed set; keep its reply for later duplicates."""
        if self._inflight.get(request_id) is operation:
            del self._inflight[request_id]
        self._completed[request_id] = _Completed(operation.fingerprint, time.monotonic())
        task = operation.task
        if not task.cancelled() and task.exception() is None:
            reply, size = task.result()
            self._results[request_id] = (reply, size)
            self._result_bytes += size
            while self._result_bytes > self.DEDUP_MAX_RESULT_BYTES and self._results:
                _, (_, dropped) = self._results.popitem(last=False)
                self._result_bytes -= dropped
        self._expire_completed()

    def _expire_completed(self) -> None:
        cutoff = time.monotonic() - self.DEDUP_WINDOW
        while self._completed:
            request_id, completed = next(iter(self._completed.items()))
            if completed.finished_at > cutoff:
                break
            del self._completed[request_id]
            if request_id in self._results:
                _, size = self._results.pop(request_id)
                self._result_bytes -= size

    def _duplicate_error(self, request_id: str, request: Dict[str, Any], reason: str) -> Dict[str, Any]:
        self._log.warning(f"Tunnel request {request_id} not executed: id already used ({reason})")
        metrics.record_request(self._server_label(request), "duplicate_request", 0.0)
        return {"type": "error", "id": request_id, "code": "duplicate_request", "reason": reason}

    def _server_label(self, request: Dict[str, Any]) -> str:
        server = request.get("server")
        return server if server in self._allowed_servers else "-"  # keep metric labels bounded

    def _deliver(self, conn: _Connection, request_id: str, operation: _Operation) -> None:
        """Send the operation's reply on `conn` once it is ready."""

        async def deliver() -> None:
            try:
                # shield: cancelling this reply (disconnect, or one duplicate going away) never
                # cancels the shared operation.
                reply, _ = await asyncio.shield(operation.task)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._log.exception(f"Tunnel request {request_id} failed")
                reply = {"type": "error", "id": request_id, "code": "local_call_failed"}
            await self._reply(conn, reply)

        self._track(asyncio.create_task(deliver()))

    def _reply_later(self, conn: _Connection, message: Dict[str, Any]) -> None:
        self._track(asyncio.create_task(self._reply(conn, message)))

    def _track(self, task: asyncio.Task) -> None:
        self._deliveries.add(task)
        task.add_done_callback(self._deliveries.discard)

    async def _execute(
        self, http: httpx.AsyncClient, request_id: str, request: Dict[str, Any], deadline: float
    ) -> Tuple[Dict[str, Any], int]:
        """Run one accepted request. Returns (reply, approximate size of the reply in bytes)."""
        server, body = request.get("server"), request.get("body")
        if server not in self._allowed_servers:
            self._log.warning(f"Rejected tunnel request for server not in allowlist: {server!r}")
            metrics.record_request("-", "server_not_allowed", 0.0)
            return {"type": "error", "id": request_id, "code": "server_not_allowed"}, 0
        if not isinstance(body, dict):
            metrics.record_request(server, "bad_request", 0.0)
            return {"type": "error", "id": request_id, "code": "bad_request"}, 0

        headers = {"X-Trace-ID": request_id}
        if self._local_token:
            headers["Authorization"] = f"Bearer {self._local_token}"
        started = time.monotonic()
        reply, result, size = await self._call_gateway(http, request_id, server, body, headers, deadline)
        metrics.record_request(server, result, time.monotonic() - started)
        return reply, size

    async def _call_gateway(
        self,
        http: httpx.AsyncClient,
        request_id: str,
        server: str,
        body: Dict[str, Any],
        headers: Dict[str, str],
        deadline: float,
    ) -> Tuple[Dict[str, Any], str, int]:
        """
        Wait for a concurrency slot and call the gateway, both within `deadline` (monotonic).

        Returns (reply, metrics result, size). `not_delivered` means the gateway never received the
        request; `local_timeout` and `local_call_failed` mean it may have, and the tool may still run.
        """
        if not await self._acquire_slot(deadline):
            return _not_delivered(request_id, "queue_timeout"), "not_delivered", 0
        try:
            # Don't start a call that has almost no time left: its outcome would be unknown.
            if deadline - time.monotonic() < min(self.MIN_CALL_TIME, self._request_timeout / 2):
                return _not_delivered(request_id, "queue_timeout"), "not_delivered", 0
            progress = {"maybe_sent": False}
            try:
                response = await asyncio.wait_for(
                    self._post_local(http, server, body, headers, deadline, progress), deadline - time.monotonic()
                )
            except (asyncio.TimeoutError, httpx.TimeoutException) as e:
                if not progress["maybe_sent"] or isinstance(e, (httpx.ConnectTimeout, httpx.PoolTimeout)):
                    return _not_delivered(request_id, "gateway_unreachable"), "not_delivered", 0
                return {"type": "error", "id": request_id, "code": "local_timeout"}, "local_timeout", 0
            except httpx.ConnectError:
                self._log.warning(f"Local call to '{server}' failed: gateway not reachable")
                return _not_delivered(request_id, "gateway_unreachable"), "not_delivered", 0
            except httpx.HTTPError as e:
                self._log.warning(f"Local call to '{server}' failed: {type(e).__name__}")
                return {"type": "error", "id": request_id, "code": "local_call_failed"}, "local_call_failed", 0
        finally:
            self._semaphore.release()
        reply = {"type": "response", "id": request_id, "status": response.status_code, "body": _decode_body(response)}
        return reply, str(response.status_code), len(response.content) + 256

    async def _acquire_slot(self, deadline: float) -> bool:
        """Wait for a concurrency slot until `deadline`. True if acquired (the caller must release it)."""
        # Not asyncio.wait_for: on Python 3.10 it can return an acquired slot and swallow a
        # cancellation that arrives at the same moment (bpo-42130).
        acquire = asyncio.ensure_future(self._semaphore.acquire())
        try:
            await asyncio.wait({acquire}, timeout=max(deadline - time.monotonic(), 0))
        except BaseException:
            if acquire.done() and not acquire.cancelled() and acquire.exception() is None:
                self._semaphore.release()
            else:
                acquire.cancel()
            raise
        if acquire.done():
            return True
        acquire.cancel()  # Semaphore.acquire hands a wake-up it can no longer use to the next waiter
        return False

    async def _post_local(
        self,
        http: httpx.AsyncClient,
        server: str,
        body: Dict[str, Any],
        headers: Dict[str, str],
        deadline: float,
        progress: Dict[str, bool],
    ) -> httpx.Response:
        # A refused connection means the request never reached the gateway, so retrying cannot
        # run a tool twice. This covers the gap between startup hooks and uvicorn binding its port.
        retry_until = min(time.monotonic() + self.LOCAL_CONNECT_RETRY, deadline)
        while True:
            progress["maybe_sent"] = True
            try:
                return await http.post(
                    f"{self._local_base_url}/{server}/mcp",
                    json=body,
                    headers=headers,
                    timeout=max(deadline - time.monotonic(), 0.001),
                )
            except httpx.ConnectError:
                progress["maybe_sent"] = False
                if time.monotonic() >= retry_until:
                    raise
                await asyncio.sleep(min(0.5, max(retry_until - time.monotonic(), 0)))

    async def _reply(self, conn: _Connection, message: Dict[str, Any]) -> None:
        try:
            try:
                await conn.send(message)
            except ValueError:
                self._log.warning(f"Reply {message['id']} exceeds the tunnel message limit")
                await conn.send({"type": "error", "id": message["id"], "code": "response_too_large"})
        except (ConnectionClosed, ProtocolError):
            self._log.warning(f"Reply {message['id']} not sent: tunnel closed")


def _fingerprint(request: Dict[str, Any]) -> str:
    """Identifies what a request asks for, so a reused id with different content is recognised."""
    canonical = json.dumps(
        {"server": request.get("server"), "body": request.get("body")}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _not_delivered(request_id: str, reason: str) -> Dict[str, Any]:
    """The gateway never received this request, so the tool did not run and a retry is safe."""
    return {"type": "error", "id": request_id, "code": "not_delivered", "reason": reason}


def _decode_body(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text
