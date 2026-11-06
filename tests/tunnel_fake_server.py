"""
Minimal GPT Engine side of the tunnel, for tests and local end-to-end runs.

It is also the reference for GPT Engine's /ws/mcp-tunnel endpoint: check the token before
accepting, run the handshake, then hold one lock around every decrypt/encrypt and its send.

Local run (prints the server public key to put in FMCP_TUNNEL_SERVER_PUBLIC_KEYS):
    PYTHONPATH=. python tests/tunnel_fake_server.py --token TOKEN --client-public-key KEY --connector site-a
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import uuid
from typing import Any, Dict, Optional, Sequence

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from fluidmcp.cli.tunnel.protocol import (
    HANDSHAKE_TIMEOUT,
    MAX_FRAME,
    ControlMessage,
    Env,
    ProtocolError,
    SecureChannel,
    ServerHandshake,
    generate_identity_key,
    parse_public_key_list,
    public_key_to_b64,
)


class FakeTunnelServer:
    def __init__(self, token: str, connector_id: str, client_public_keys: Sequence[bytes], env: Env = Env()):
        self.identity_key = generate_identity_key()
        self.public_key = self.identity_key.public_key().public_bytes_raw()
        self.connector_id = connector_id
        self.hello: Optional[Dict[str, Any]] = None
        self.connected = asyncio.Event()
        self.rejected = 0
        self._token_sha256 = hashlib.sha256(token.encode()).hexdigest()
        self._client_public_keys = tuple(client_public_keys)
        self._env = env
        self._server: Optional[Server] = None
        self._ws: Optional[ServerConnection] = None
        self._channel: Optional[SecureChannel] = None
        self._lock = asyncio.Lock()
        self._pending: Dict[str, asyncio.Future] = {}

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> str:
        self._server = await serve(
            self._handler, host, port, process_request=self._check_token, max_size=MAX_FRAME, compression=None
        )
        bound_port = self._server.sockets[0].getsockname()[1]
        return f"ws://{host}:{bound_port}"

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def send_request(self, server: str, body: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        """Send one MCP request through the tunnel and wait for its response or error."""
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        data = json.dumps({"type": "request", "id": request_id, "server": server, "body": body}).encode()
        async with self._lock:
            await self._ws.send(self._channel.encrypt(data))
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(request_id, None)

    def _check_token(self, connection: ServerConnection, request):
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        token_ok = hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), self._token_sha256)
        connector_ok = hmac.compare_digest(request.headers.get("X-Connector-Id", ""), self.connector_id)
        if not (token_ok and connector_ok):
            self.rejected += 1
            return connection.respond(403, "Forbidden\n")
        return None

    async def _handler(self, ws: ServerConnection) -> None:
        try:
            channel = await asyncio.wait_for(self._handshake(ws), HANDSHAKE_TIMEOUT)
        except (ProtocolError, ConnectionClosed, asyncio.TimeoutError):
            self.rejected += 1
            await ws.close(1008)
            return

        self._ws, self._channel = ws, channel
        try:
            async for frame in ws:
                async with self._lock:
                    message = channel.decrypt(frame)
                    if isinstance(message, ControlMessage):
                        await ws.send(message.reply)
                        continue
                data = json.loads(message)
                if data["type"] == "hello":
                    self.hello = data
                    self.connected.set()
                elif data["id"] in self._pending:
                    self._pending[data["id"]].set_result(data)
        except ProtocolError:
            await ws.close(1008)
        finally:
            self.connected.clear()

    async def _handshake(self, ws: ServerConnection) -> SecureChannel:
        handshake = ServerHandshake(self.identity_key, self._client_public_keys, self.connector_id, self._env)
        client_hello = await ws.recv()
        if not isinstance(client_hello, bytes):
            raise ProtocolError("text_frame")
        await ws.send(handshake.receive_client_hello(client_hello))
        client_finish = await ws.recv()
        if not isinstance(client_finish, bytes):
            raise ProtocolError("text_frame")
        return handshake.receive_client_finish(client_finish)


async def _main(args: argparse.Namespace) -> None:
    server = FakeTunnelServer(args.token, args.connector, parse_public_key_list(args.client_public_key))
    url = await server.start(port=args.port)
    print(f"Listening on {url}")
    print(f"FMCP_TUNNEL_SERVER_PUBLIC_KEYS={public_key_to_b64(server.identity_key)}")
    while True:
        await server.connected.wait()
        print(f"Connected: {server.hello}")
        for name in server.hello["servers"]:
            result = await server.send_request(name, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, timeout=50)
            print(f"{name}: {json.dumps(result)[:300]}")
        while server.connected.is_set():
            await asyncio.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fake GPT Engine tunnel endpoint")
    parser.add_argument("--token", required=True)
    parser.add_argument("--client-public-key", required=True)
    parser.add_argument("--connector", required=True)
    parser.add_argument("--port", type=int, default=8765)
    asyncio.run(_main(parser.parse_args()))
