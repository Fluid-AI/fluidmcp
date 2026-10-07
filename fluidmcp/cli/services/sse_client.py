"""An owned MCP SSE session with SDK-managed request/response correlation."""

import asyncio
from datetime import timedelta
from typing import Optional

from loguru import logger
from mcp import ClientSession, McpError, types
from mcp.client.sse import sse_client


class SseJsonRpcClient:
    """Keep SDK task groups in one owner task throughout their lifetime.

    Concurrent callers share the initialized session, but the SDK gives every
    request a different upstream ID and a separate response waiter.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._task = None
        self._ready = None
        self._stop = asyncio.Event()
        self._closed = False

    async def start(self):
        if self._closed:
            raise ConnectionError("SSE session is closed")
        if self._task is None:
            self._ready = asyncio.get_running_loop().create_future()
            # A caller may time out before initialization fails. Retrieve the
            # exception even in that case to avoid an unobserved-future warning.
            self._ready.add_done_callback(lambda future: future.exception()
                                          if not future.cancelled() else None)
            self._task = asyncio.create_task(self._run())
        session = await asyncio.shield(self._ready)
        if self._task.done():
            raise ConnectionError("SSE session disconnected")
        return session

    async def _run(self):
        try:
            async with sse_client(f"{self.base_url.rstrip('/')}/sse") as streams:
                async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=30)) as session:
                    await session.initialize()
                    self._ready.set_result(session)
                    await self._stop.wait()
        except Exception as exc:
            if not self._ready.done():
                self._ready.set_exception(ConnectionError(f"SSE initialization failed: {exc}"))
            elif not self._closed:
                logger.warning(f"SSE session disconnected at {self.base_url}: {exc}")
        finally:
            if not self._ready.done():
                self._ready.set_exception(ConnectionError("SSE session closed during initialization"))

    async def request(self, payload: dict, timeout: float = 60.0) -> Optional[dict]:
        async def send():
            session = await self.start()
            method = payload["method"]
            params = payload.get("params")
            if "id" not in payload:
                # A downstream cancellation ID is not an SDK upstream ID.
                # Cancellation is optional; never cancel another caller's work
                # by forwarding an unscoped, untranslated requestId.
                if method != "notifications/cancelled":
                    await session.send_notification(
                        types.Notification[Optional[dict], str](method=method, params=params)
                    )
                return None
            envelope = {"jsonrpc": "2.0", "id": payload["id"]}
            try:
                result = await session.send_request(
                    types.Request[Optional[dict], str](method=method, params=params),
                    types.Result,
                    request_read_timeout_seconds=timedelta(seconds=timeout),
                )
                envelope["result"] = result.model_dump(by_alias=True, mode="json", exclude_unset=True)
            except McpError as exc:
                envelope["error"] = exc.error.model_dump(by_alias=True, mode="json", exclude_none=True)
            return envelope

        # Covers initialization and sending too. Cancellation removes the SDK's
        # response waiter; late responses cannot be delivered to another caller.
        return await asyncio.wait_for(send(), timeout=timeout)

    async def aclose(self):
        self._closed = True
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
