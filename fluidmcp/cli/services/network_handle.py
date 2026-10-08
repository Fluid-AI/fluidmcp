"""
Network transport handle for MCP servers (SSE and streamable-http).

Kept in its own module to avoid circular imports between
package_launcher.py and server_manager.py.
"""
import asyncio
import json
import subprocess
import httpx
from loguru import logger


_NO_ID = object()


def parse_sse_jsonrpc_response(text: str, request_id=_NO_ID) -> dict:
    """Extract the JSON-RPC response from a streamable-http SSE body.

    A single request's SSE stream may carry server notifications (log messages,
    progress updates from ctx.info()/ctx.report_progress()) before the actual
    response, so the first ``data:`` line is not necessarily the answer. Return
    the message that carries ``result``/``error`` and, when ``request_id`` is
    given, whose ``id`` matches it.
    """
    responses = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        message = json.loads(payload)
        if isinstance(message, dict) and ("result" in message or "error" in message):
            responses.append(message)

    if request_id is not _NO_ID:
        for message in responses:
            if message.get("id") == request_id:
                return message
    if responses:
        return responses[0]
    raise ValueError(f"No JSON-RPC response in SSE body: {text[:500]!r}")


class NetworkSubprocessHandle:
    """
    Wraps a subprocess.Popen for a network-transport MCP server (SSE or streamable-http).

    We still OWN the process (spawned via uv/python/etc.) so we keep the
    real Popen for lifecycle management (kill/terminate/poll).
    Communication happens over HTTP instead of stdin/stdout.

    For HTTP transport a shared persistent httpx.AsyncClient is kept alive for
    the lifetime of the server. This gives all concurrent gateway requests a
    pre-established connection pool so they reach FastMCP simultaneously
    instead of serially (one new TCP handshake per request).

    Attributes:
        _process:    The real subprocess.Popen — used for kill/terminate/poll.
        base_url:    Base HTTP URL, e.g. "http://127.0.0.1:8000".
        transport:   Transport type: "sse" or "http".
        http_client: Shared httpx.AsyncClient for HTTP transport (None for SSE).
        pid:         Delegated to the underlying process.
        returncode:  Delegated to the underlying process.
    """

    def __init__(self, process: subprocess.Popen, base_url: str, transport: str, session_id: str = None):
        self._process = process
        self.base_url = base_url
        self.transport = transport
        self.session_id = session_id

        # HTTP transport gets a single long-lived client shared across all requests to
        # this server. Reusing pooled TCP connections lets 100 concurrent gateway
        # requests reach FastMCP simultaneously instead of one-at-a-time (each new
        # AsyncClient() would pay a fresh TCP handshake, staggering arrival and forcing
        # FastMCP to process them serially). SSE transport doesn't need this — it uses
        # a streaming GET, not repeated POSTs.
        if transport == "http":
            import os
            self.http_client = httpx.AsyncClient(
                limits=httpx.Limits(
                    max_connections=int(os.getenv("FMCP_HTTP_POOL_MAX_CONNECTIONS", "200")),
                    max_keepalive_connections=int(os.getenv("FMCP_HTTP_POOL_MAX_KEEPALIVE", "100")),
                    keepalive_expiry=int(os.getenv("FMCP_HTTP_POOL_KEEPALIVE_EXPIRY", "30")),
                ),
                timeout=httpx.Timeout(float(os.getenv("FMCP_HTTP_POOL_TIMEOUT", "60.0"))),
            )
            logger.debug(f"Created shared httpx client pool for {base_url}")
        else:
            self.http_client = None

    @property
    def pid(self):
        return self._process.pid

    @property
    def returncode(self):
        return self._process.returncode

    def poll(self):
        return self._process.poll()

    def terminate(self):
        self._process.terminate()

    def kill(self):
        self._process.kill()

    def wait(self, timeout=None):
        return self._process.wait(timeout=timeout)

    async def aclose(self):
        """Close the shared HTTP client pool. Call this when the server stops."""
        if self.http_client is not None:
            await self.http_client.aclose()
            self.http_client = None
            logger.debug(f"Closed shared httpx client pool for {self.base_url}")

    def close_nowait(self):
        """Schedule client pool closure from sync context (e.g. cleanup_all).

        cleanup_all() is synchronous (called from signal handlers / __del__), so
        we can't simply await aclose(). If an event loop is already running we
        schedule the coroutine as a fire-and-forget task; otherwise we run it
        synchronously. Either way the pool gets closed without blocking the caller.
        """
        if self.http_client is not None:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.aclose())
                else:
                    loop.run_until_complete(self.aclose())
            except Exception as e:
                logger.debug(f"Could not close httpx client pool for {self.base_url}: {e}")