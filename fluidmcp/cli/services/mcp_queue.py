"""
McpQueue — per-server async queue for serializing MCP subprocess stdio I/O.

All writes to stdin and reads from stdout for a given subprocess are
funnelled through a single drain loop coroutine, eliminating the race
condition that occurs when multiple concurrent HTTP requests attempt to
share the same pipe pair simultaneously.

Protocol: 1 request → 1 response line (JSON-RPC over newline-delimited
stdio). For the multi-response SSE streaming path, callers should acquire
``queue.io_lock`` directly and perform their own multi-line read loop
instead of going through ``send()``.
"""
import asyncio
import os
import subprocess
from typing import Optional, Tuple

from loguru import logger

# Maximum number of requests that can be queued per server before callers
# receive HTTP 429.  Override via environment variable for high-concurrency
# deployments.
_DEFAULT_QUEUE_SIZE = int(os.getenv("FMCP_QUEUE_SIZE", "100"))

# Timeout (seconds) applied to each individual stdout.readline() inside the
# drain loop.  Prevents the loop from hanging forever if an MCP server stops
# responding without closing its pipe.
_DRAIN_READ_TIMEOUT = 30.0

# Maximum number of response lines the SSE streaming path will read in a
# single lock-hold before giving up, to prevent an infinite loop if the
# subprocess never emits a "result" field.
_SSE_MAX_LINES = 500


class McpQueue:
    """
    Serializes all stdin/stdout I/O for a single MCP subprocess.

    Attributes
    ----------
    server_name:
        Human-readable identifier used in log messages.
    io_lock:
        ``asyncio.Lock`` held for every write+read pair executed by the drain
        loop.  The SSE streaming endpoint **must** acquire this lock directly
        when performing its own multi-line read loop, ensuring mutual
        exclusion with the drain loop.
    """

    def __init__(
        self,
        server_name: str,
        process: subprocess.Popen,
        maxsize: int = _DEFAULT_QUEUE_SIZE,
    ) -> None:
        self.server_name = server_name
        self._process = process
        self._queue: asyncio.Queue[Tuple[str, "asyncio.Future[str]"]] = asyncio.Queue(
            maxsize=maxsize
        )
        # Single lock that serializes all stdio access on this subprocess.
        # Exposed publicly so the SSE multi-line path can acquire it directly.
        self.io_lock: asyncio.Lock = asyncio.Lock()
        self._drain_task: Optional[asyncio.Task] = None
        self._stopped: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the background drain loop task.

        Must be called from within a running event loop (i.e. after the
        FastAPI application has started).  Calling ``start()`` more than once
        is a no-op.
        """
        if self._drain_task is not None:
            return
        self._drain_task = asyncio.create_task(
            self._drain_loop(),
            name=f"mcp-drain-{self.server_name}",
        )
        logger.debug(f"[{self.server_name}] McpQueue drain loop started")

    async def stop(self) -> None:
        """
        Signal the drain loop to stop and wait for it to finish.

        Any items still in the queue when ``stop()`` is called are resolved
        immediately with a ``RuntimeError`` so callers are not left waiting
        indefinitely.
        """
        if self._stopped:
            return
        self._stopped = True

        # Cancel the drain task first so it stops consuming new items.
        if self._drain_task is not None and not self._drain_task.done():
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
            self._drain_task = None

        # Drain remaining items and resolve their futures with an error.
        error = RuntimeError(f"Server '{self.server_name}' stopped")
        while not self._queue.empty():
            try:
                _, future = self._queue.get_nowait()
                if not future.done():
                    future.set_exception(error)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

        logger.debug(f"[{self.server_name}] McpQueue stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send(self, msg: str, timeout: float = 30.0) -> str:
        """
        Enqueue *msg*, wait for the drain loop to process it, and return the
        raw response line.

        Parameters
        ----------
        msg:
            JSON-RPC request string (without trailing newline).
        timeout:
            Seconds to wait for a response before raising
            ``asyncio.TimeoutError``.

        Returns
        -------
        str
            Raw response line (still JSON-encoded, no trailing newline).

        Raises
        ------
        asyncio.QueueFull
            Queue is at capacity → caller should return HTTP 429.
        asyncio.TimeoutError
            No response within *timeout* → caller should return HTTP 504.
        RuntimeError
            Server stopped while waiting.
        OSError / BrokenPipeError
            I/O error on the subprocess pipe.
        """
        if self._stopped:
            raise RuntimeError(f"Server '{self.server_name}' queue is stopped")

        loop = asyncio.get_event_loop()
        future: asyncio.Future[str] = loop.create_future()

        # put_nowait raises QueueFull immediately if at capacity — the caller
        # maps this to HTTP 429 without blocking.
        self._queue.put_nowait((msg, future))
        logger.debug(
            f"[{self.server_name}] Enqueued request "
            f"(queue size ~{self._queue.qsize()})"
        )

        # asyncio.shield ensures that if the HTTP caller's coroutine is
        # cancelled (e.g. client disconnect), the Future itself is NOT
        # cancelled.  The drain loop can still finish the write+read cycle
        # and discard the result cleanly, leaving the pipe in a known state.
        return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)

    async def write_stdin_only(self, msg: str) -> None:
        """
        Write *msg* to stdin without enqueuing a corresponding read.

        **Must only be called while holding** ``self.io_lock``.

        This is intended exclusively for the SSE multi-line read path, which
        writes one request and then reads an indeterminate number of response
        lines in its own loop.
        """
        await asyncio.to_thread(self._write_stdin, msg)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_stdin(self, msg: str) -> None:
        """Write msg + newline to stdin and flush.  Runs in a thread pool."""
        self._process.stdin.write(msg + "\n")
        self._process.stdin.flush()

    async def _drain_loop(self) -> None:
        """
        Single coroutine that serializes all stdio access.

        For each queue item:

        1. Acquire ``io_lock``  ← blocks SSE endpoint from concurrent access
        2. Write msg to ``process.stdin`` (via ``asyncio.to_thread``)
        3. Read one response line from ``process.stdout`` (via
           ``asyncio.to_thread`` with a hard timeout)
        4. Release ``io_lock``
        5. Resolve the future with the response (or exception)
        """
        while True:
            # Wait for the next queued request.
            try:
                msg, future = await self._queue.get()
            except asyncio.CancelledError:
                break

            try:
                async with self.io_lock:
                    # ── write ──────────────────────────────────────────────
                    try:
                        await asyncio.to_thread(self._write_stdin, msg)
                    except (BrokenPipeError, OSError) as exc:
                        logger.warning(
                            f"[{self.server_name}] Broken pipe on write: {exc}"
                        )
                        if not future.done():
                            future.set_exception(exc)
                        self._queue.task_done()
                        continue

                    # ── read (with hard timeout to prevent drain-loop hang) ─
                    try:
                        response_line = await asyncio.wait_for(
                            asyncio.to_thread(self._process.stdout.readline),
                            timeout=_DRAIN_READ_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        logger.error(
                            f"[{self.server_name}] stdout.readline timed out "
                            f"after {_DRAIN_READ_TIMEOUT}s in drain loop"
                        )
                        exc = asyncio.TimeoutError(
                            f"Server '{self.server_name}' did not respond within "
                            f"{_DRAIN_READ_TIMEOUT}s"
                        )
                        if not future.done():
                            future.set_exception(exc)
                        self._queue.task_done()
                        continue
                    except OSError as exc:
                        logger.warning(
                            f"[{self.server_name}] OSError on stdout read: {exc}"
                        )
                        if not future.done():
                            future.set_exception(exc)
                        self._queue.task_done()
                        continue

                    # Empty readline → pipe closed (process died).
                    if not response_line:
                        exc = OSError(
                            f"Server '{self.server_name}' stdout closed "
                            "(process died)"
                        )
                        logger.warning(f"[{self.server_name}] stdout closed")
                        if not future.done():
                            future.set_exception(exc)
                        self._queue.task_done()
                        continue

                # Resolve outside the lock — response is ready.
                if not future.done():
                    future.set_result(response_line)

            except asyncio.CancelledError:
                # Drain loop cancelled mid-item; resolve pending future.
                if not future.done():
                    future.set_exception(
                        RuntimeError(f"Server '{self.server_name}' stopped")
                    )
                break
            except Exception as exc:
                logger.exception(
                    f"[{self.server_name}] Unexpected error in drain loop: {exc}"
                )
                if not future.done():
                    future.set_exception(exc)
            finally:
                try:
                    self._queue.task_done()
                except ValueError:
                    # task_done() called more times than get() — defensive guard.
                    pass


# Expose constants so callers (e.g. the SSE endpoint) can reuse them.
SSE_MAX_LINES = _SSE_MAX_LINES
