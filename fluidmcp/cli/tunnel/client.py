"""
Outbound tunnel client.

Keeps one authenticated, encrypted WebSocket open to GPT Engine and forwards the MCP
requests it receives to this gateway's own /{server}/mcp route on localhost.
"""

import asyncio
import json
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Set

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
        self._requests: Set[asyncio.Task] = set()
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
                for task in tasks + list(self._requests):
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
            task = asyncio.create_task(self._handle(conn, http, request))
            self._requests.add(task)
            task.add_done_callback(self._requests.discard)

    async def _handle(self, conn: _Connection, http: httpx.AsyncClient, request: Dict[str, Any]) -> None:
        request_id, server, body = request.get("id"), request.get("server"), request.get("body")
        if not isinstance(request_id, str):
            self._log.warning("Ignoring tunnel request without an id")
            return
        if server not in self._allowed_servers:
            self._log.warning(f"Rejected tunnel request for server not in allowlist: {server!r}")
            metrics.record_request("-", "server_not_allowed", 0.0)
            await self._reply(conn, {"type": "error", "id": request_id, "code": "server_not_allowed"})
            return
        if not isinstance(body, dict):
            metrics.record_request(server, "bad_request", 0.0)
            await self._reply(conn, {"type": "error", "id": request_id, "code": "bad_request"})
            return

        headers = {"X-Trace-ID": request_id}
        if self._local_token:
            headers["Authorization"] = f"Bearer {self._local_token}"
        started = time.monotonic()
        async with self._semaphore:
            try:
                response = await self._post_local(http, server, body, headers)
            except httpx.TimeoutException:
                reply, result = {"type": "error", "id": request_id, "code": "local_timeout"}, "local_timeout"
            except httpx.HTTPError as e:
                self._log.warning(f"Local call to '{server}' failed: {type(e).__name__}")
                reply, result = {"type": "error", "id": request_id, "code": "local_call_failed"}, "local_call_failed"
            else:
                reply = {"type": "response", "id": request_id, "status": response.status_code, "body": _decode_body(response)}
                result = str(response.status_code)
        metrics.record_request(server, result, time.monotonic() - started)
        await self._reply(conn, reply)

    async def _post_local(
        self, http: httpx.AsyncClient, server: str, body: Dict[str, Any], headers: Dict[str, str]
    ) -> httpx.Response:
        # A refused connection means the request never reached the gateway, so retrying cannot
        # run a tool twice. This covers the gap between startup hooks and uvicorn binding its port.
        deadline = time.monotonic() + self.LOCAL_CONNECT_RETRY
        while True:
            try:
                return await http.post(f"{self._local_base_url}/{server}/mcp", json=body, headers=headers)
            except httpx.ConnectError:
                if time.monotonic() >= deadline:
                    raise
                await asyncio.sleep(0.5)

    async def _reply(self, conn: _Connection, message: Dict[str, Any]) -> None:
        try:
            try:
                await conn.send(message)
            except ValueError:
                self._log.warning(f"Reply {message['id']} exceeds the tunnel message limit")
                await conn.send({"type": "error", "id": message["id"], "code": "response_too_large"})
        except (ConnectionClosed, ProtocolError):
            self._log.warning(f"Reply {message['id']} not sent: tunnel closed")


def _decode_body(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text
