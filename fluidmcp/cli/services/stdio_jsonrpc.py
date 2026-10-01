"""
JSON-RPC response correlation for stdio MCP subprocesses.

An MCP stdio subprocess has exactly one stdout stream, but the gateway serves
many concurrent HTTP clients (and internal callers such as tool discovery) on
top of it. Reading "the next line" after writing a request is not safe:

  * responses may arrive out of order when the server handles requests
    concurrently;
  * a request that timed out leaves its response in the pipe, and the next
    reader would receive it (A times out → late A is returned to B);
  * notifications and server-initiated requests share the same stream.

StdioJsonRpcRouter fixes this by making ONE daemon thread the sole owner of a
subprocess's stdout. Every outgoing request gets a gateway-unique integer ID
(the caller's ID is restored on the response), a waiter is registered in the
pending registry BEFORE the request is written, and the reader delivers each
response strictly by ``response["id"]``. Responses whose ID is not pending
(late responses after a timeout, unknown IDs) are logged and dropped. On
stdout EOF every pending waiter fails with StdioProcessClosed.

Use get_stdio_router(process) to obtain the router for a Popen — never read
process.stdout directly once a router exists for it.
"""

import asyncio
import concurrent.futures
import itertools
import json
import threading
from typing import Any, Callable, Dict, Optional, Tuple

from loguru import logger


NotificationCallback = Callable[[Dict[str, Any]], None]


class StdioProcessClosed(ConnectionError):
    """The subprocess's stdout closed (EOF/crash) before a response arrived."""


class StdioRequestTimeout(Exception):
    """No response with the request's JSON-RPC ID arrived within the timeout.

    Deliberately not a TimeoutError: that subclasses OSError, and callers catch
    OSError for broken pipes (503) separately from timeouts (504).
    """


def _preview(value: Any, max_len: int = 80) -> str:
    """Printable, length-capped repr of an ID for logs (never message bodies)."""
    text = "".join(ch for ch in repr(value) if ch.isprintable())
    return text[:max_len]


class PendingRequest:
    """A request that is registered with a router and already written to stdin.

    Returned by StdioJsonRpcRouter.start(). Both wait() and wait_sync() remove
    the waiter when they return, raise or are cancelled, so a response arriving
    afterwards is dropped by the reader instead of reaching another request.
    """

    def __init__(self, router: "StdioJsonRpcRouter", original_id: Any, internal_id: int,
                 future: concurrent.futures.Future):
        self._router = router
        self.original_id = original_id
        self.internal_id = internal_id
        self._future = future

    async def wait(self, timeout: Optional[float]) -> Dict[str, Any]:
        """Await the response carrying this request's ID (None waits indefinitely)."""
        try:
            response = await asyncio.wait_for(asyncio.wrap_future(self._future), timeout)
        except asyncio.TimeoutError:
            raise self._timed_out(timeout) from None
        finally:
            self.cancel()
        return self._restore_id(response)

    def wait_sync(self, timeout: Optional[float]) -> Dict[str, Any]:
        """Blocking variant of wait() for code running outside the event loop."""
        try:
            response = self._future.result(timeout)
        except concurrent.futures.TimeoutError:
            raise self._timed_out(timeout) from None
        finally:
            self.cancel()
        return self._restore_id(response)

    def cancel(self) -> None:
        """Stop waiting; a response that arrives later is dropped."""
        self._router._forget(self.internal_id)

    def _timed_out(self, timeout: Optional[float]) -> "StdioRequestTimeout":
        self._router._on_timeout(self.internal_id, self.original_id, timeout)
        return StdioRequestTimeout(
            f"No response for request id={_preview(self.original_id)} within {timeout}s"
        )

    def _restore_id(self, response: Dict[str, Any]) -> Dict[str, Any]:
        restored = dict(response)
        restored["id"] = self.original_id
        return restored


class StdioJsonRpcRouter:
    """Single stdout reader + pending-request registry for one MCP subprocess."""

    def __init__(self, process: Any, name: str = ""):
        self._process = process
        self._name = name or f"pid={getattr(process, 'pid', '?')}"
        self._log = logger.bind(server_id=self._name)

        # Guards _pending, _progress, _closed and _stats. Never held while doing I/O.
        self._state_lock = threading.Lock()
        # Serializes stdin writes from every caller (event loop and worker threads)
        # so two JSON-RPC lines can never interleave on the pipe.
        self._write_lock = threading.Lock()

        self._ids = itertools.count(1)
        self._pending: Dict[int, concurrent.futures.Future] = {}
        # gateway progress token -> (client's original token, callback)
        self._progress: Dict[str, Tuple[Any, NotificationCallback]] = {}
        self._closed = False
        self._close_reason = ""

        self._stats = {
            "responses_matched": 0,
            "orphan_responses": 0,
            "notifications": 0,
            "server_requests": 0,
            "non_json_lines": 0,
        }

        self._thread = threading.Thread(
            target=self._reader_loop, name=f"stdio-router-{self._name}", daemon=True
        )
        self._thread.start()

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def stats(self) -> Dict[str, int]:
        """Consistent snapshot of the correlation counters (for logs/diagnostics)."""
        with self._state_lock:
            return dict(self._stats)

    def start(
        self,
        message: Dict[str, Any],
        on_notification: Optional[NotificationCallback] = None,
    ) -> PendingRequest:
        """Register a JSON-RPC request and write it to stdin.

        The caller's ``id`` is replaced on the wire by a gateway-unique ID and
        restored on the response, so concurrent clients may reuse the same IDs
        without colliding. The waiter is registered BEFORE the write because
        the response can arrive before write() returns.

        Args:
            message: JSON-RPC request (must contain "id" and "method").
            on_notification: Optional callback (invoked on the reader thread)
                     for progress notifications tied to this request's
                     params._meta.progressToken.

        Raises (synchronously, before anything is awaited):
            StdioProcessClosed: stdout already closed.
            BrokenPipeError / OSError: writing to stdin failed.
        """
        if "id" not in message:
            raise ValueError("JSON-RPC request must have an 'id'; use notify() for notifications")
        original_id = message["id"]
        future: concurrent.futures.Future = concurrent.futures.Future()
        outgoing = dict(message)

        with self._state_lock:
            if self._closed:
                raise StdioProcessClosed(self._close_reason or "stdout closed")
            internal_id = next(self._ids)
            self._pending[internal_id] = future
            outgoing["id"] = internal_id
            if on_notification is not None:
                self._register_progress(outgoing, internal_id, on_notification)

        self._log.debug(
            "[stdio.request_registered] server={} request_id={} client_id={} method={}",
            self._name, internal_id, _preview(original_id), _preview(message.get("method"), 60),
        )
        try:
            self._write(outgoing)
        except BaseException:
            self._forget(internal_id)
            raise
        self._log.debug("[stdio.request_sent] server={} request_id={}", self._name, internal_id)
        return PendingRequest(self, original_id, internal_id, future)

    async def request(
        self,
        message: Dict[str, Any],
        timeout: Optional[float],
        on_notification: Optional[NotificationCallback] = None,
    ) -> Dict[str, Any]:
        """Send a JSON-RPC request and await the response carrying its ID.

        Raises:
            StdioRequestTimeout: timed out; the waiter is removed and a late
                                 response will be dropped.
            StdioProcessClosed:  stdout closed before a response arrived.
            BrokenPipeError / OSError: writing to stdin failed.
        """
        return await self.start(message, on_notification).wait(timeout)

    def request_sync(self, message: Dict[str, Any], timeout: Optional[float]) -> Dict[str, Any]:
        """Blocking variant of request() for code running outside the event loop."""
        return self.start(message).wait_sync(timeout)

    def notify(self, message: Dict[str, Any]) -> None:
        """Write a JSON-RPC notification (no ID, no response expected)."""
        if self._closed:
            raise StdioProcessClosed(self._close_reason or "stdout closed")
        self._write(message)

    # ── Registry ────────────────────────────────────────────────────────────

    def _send(
        self, message: Dict[str, Any], on_notification: Optional[NotificationCallback]
    ) -> Tuple[Any, int, concurrent.futures.Future]:
        if "id" not in message:
            raise ValueError("JSON-RPC request must have an 'id'; use notify() for notifications")
        original_id = message["id"]
        future: concurrent.futures.Future = concurrent.futures.Future()
        outgoing = dict(message)

        # Register BEFORE writing: the response can arrive before write() returns.
        with self._state_lock:
            if self._closed:
                raise StdioProcessClosed(self._close_reason or "stdout closed")
            internal_id = next(self._ids)
            self._pending[internal_id] = future
            outgoing["id"] = internal_id
            if on_notification is not None:
                self._register_progress(outgoing, internal_id, on_notification)

        self._log.debug(
            "[stdio.request_registered] server={} request_id={} client_id={} method={}",
            self._name, internal_id, _preview(original_id), _preview(message.get("method"), 60),
        )
        try:
            self._write(outgoing)
        except BaseException:
            self._forget(internal_id)
            raise
        self._log.debug("[stdio.request_sent] server={} request_id={}", self._name, internal_id)
        return original_id, internal_id, future

    def _register_progress(self, outgoing: Dict[str, Any], internal_id: int, callback: NotificationCallback) -> None:
        """Rewrite params._meta.progressToken to a gateway-unique token (caller holds _state_lock)."""
        params = outgoing.get("params")
        meta = params.get("_meta") if isinstance(params, dict) else None
        if not isinstance(meta, dict) or "progressToken" not in meta:
            return
        token = f"fmcp-progress-{internal_id}"
        self._progress[token] = (meta["progressToken"], callback)
        outgoing["params"] = {**params, "_meta": {**meta, "progressToken": token}}

    def _forget(self, internal_id: int) -> None:
        with self._state_lock:
            self._pending.pop(internal_id, None)
            self._progress.pop(f"fmcp-progress-{internal_id}", None)

    def _on_timeout(self, internal_id: int, original_id: Any, timeout: Optional[float]) -> None:
        self._forget(internal_id)
        self._log.warning(
            "[stdio.timeout] server={} request_id={} client_id={} timeout={}s action=waiter_removed",
            self._name, internal_id, _preview(original_id), timeout,
        )
        # Per MCP spec, tell the server it may abandon the work. Best-effort only:
        # a late response is dropped by the reader regardless.
        try:
            self.notify({
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": internal_id, "reason": "Request timed out at gateway"},
            })
        except Exception:
            pass

    def _bump(self, key: str) -> None:
        with self._state_lock:
            self._stats[key] += 1

    def _write(self, message: Dict[str, Any]) -> None:
        data = json.dumps(message) + "\n"
        with self._write_lock:
            self._process.stdin.write(data)
            self._process.stdin.flush()

    # ── Reader thread ───────────────────────────────────────────────────────

    def _reader_loop(self) -> None:
        reason = "stdout EOF (process exited)"
        try:
            # Blocking readline() on a dedicated thread: every line buffered by
            # the TextIOWrapper is consumed, so several messages arriving in one
            # chunk are never stranded (unlike select() + readline()).
            while True:
                line = self._process.stdout.readline()
                if not line:
                    break
                try:
                    self._dispatch_line(line)
                except Exception:
                    self._log.exception("[stdio.dispatch_error] server={}", self._name)
        except (OSError, ValueError) as e:
            reason = f"stdout read failed: {type(e).__name__}: {e}"
        except Exception as e:
            reason = f"stdout reader crashed: {type(e).__name__}: {e}"
            self._log.exception("[stdio.reader_crash] server={}", self._name)
        finally:
            self._close(reason)

    def _close(self, reason: str) -> None:
        with self._state_lock:
            self._closed = True
            self._close_reason = reason
            pending = list(self._pending.items())
            self._pending.clear()
            self._progress.clear()
        returncode = None
        try:
            returncode = self._process.poll()
        except Exception:
            pass
        self._log.warning(
            "[stdio.closed] server={} reason={} returncode={} failed_pending={}",
            self._name, reason, returncode, len(pending),
        )
        for internal_id, future in pending:
            if not future.done():
                try:
                    future.set_exception(StdioProcessClosed(f"{reason} (returncode={returncode})"))
                except concurrent.futures.InvalidStateError:
                    pass
        _discard_router(self)

    def _dispatch_line(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            # Some servers print logs/tracebacks to stdout. Skip; never deliver.
            self._bump("non_json_lines")
            self._log.debug("[stdio.non_json] server={} len={} preview={}", self._name, len(text), text[:200])
            return

        if isinstance(message, list):  # JSON-RPC batch
            for item in message:
                self._dispatch_message(item)
        else:
            self._dispatch_message(message)

    def _dispatch_message(self, message: Any) -> None:
        if not isinstance(message, dict):
            self._log.warning("[stdio.invalid_message] server={} type={}", self._name, type(message).__name__)
            return
        if "method" in message:
            if "id" in message:
                self._handle_server_request(message)
            else:
                self._handle_notification(message)
            return
        if "id" in message and ("result" in message or "error" in message):
            self._handle_response(message)
            return
        self._log.warning("[stdio.invalid_message] server={} keys={}", self._name, sorted(message.keys())[:10])

    def _handle_response(self, message: Dict[str, Any]) -> None:
        response_id = message["id"]
        future = None
        # bool is an int subclass (True == 1) and unhashable IDs can't be ours.
        if not isinstance(response_id, bool):
            try:
                with self._state_lock:
                    future = self._pending.pop(response_id, None)
            except TypeError:
                future = None

        if future is None:
            self._bump("orphan_responses")
            self._log.warning(
                "[stdio.orphan_response] server={} response_id={} pending=false action=dropped_late_response",
                self._name, _preview(response_id),
            )
            return

        delivered = False
        if not future.done():
            try:
                future.set_result(message)
                delivered = True
            except concurrent.futures.InvalidStateError:
                pass
        if delivered:
            self._bump("responses_matched")
            self._log.debug(
                "[stdio.response_matched] server={} request_id={} response_id={} matched=true",
                self._name, response_id, response_id,
            )
        else:
            # Waiter was cancelled/timed out in the same instant — still never rerouted.
            self._bump("orphan_responses")
            self._log.warning(
                "[stdio.orphan_response] server={} response_id={} pending=cancelled action=dropped_late_response",
                self._name, _preview(response_id),
            )

    def _handle_notification(self, message: Dict[str, Any]) -> None:
        self._bump("notifications")
        params = message.get("params")
        token = params.get("progressToken") if isinstance(params, dict) else None
        entry = None
        if isinstance(token, str):
            with self._state_lock:
                entry = self._progress.get(token)
        if entry is None:
            self._log.debug(
                "[stdio.notification] server={} method={} action=ignored",
                self._name, _preview(message.get("method"), 60),
            )
            return
        original_token, callback = entry
        forwarded = {**message, "params": {**params, "progressToken": original_token}}
        try:
            callback(forwarded)
        except Exception:
            self._log.exception("[stdio.notification_callback_error] server={}", self._name)

    def _handle_server_request(self, message: Dict[str, Any]) -> None:
        """Answer server→client requests so the server never blocks on them.

        The gateway has no client session to forward these to, so it answers
        ``ping`` and rejects everything else with "method not found". These are
        never treated as responses to gateway requests.
        """
        self._bump("server_requests")
        method = message.get("method")
        self._log.info(
            "[stdio.server_request] server={} method={} id={}",
            self._name, _preview(method, 60), _preview(message.get("id")),
        )
        if method == "ping":
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": {}}
        else:
            reply = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32601, "message": f"Method not supported by FluidMCP gateway: {method}"},
            }
        # Reply off the reader thread so a full stdin pipe can never stall stdout reads.
        threading.Thread(target=self._safe_write, args=(reply,), daemon=True).start()

    def _safe_write(self, message: Dict[str, Any]) -> None:
        try:
            self._write(message)
        except Exception as e:
            self._log.debug("[stdio.reply_failed] server={} error={}", self._name, type(e).__name__)


# ── Per-process registry ────────────────────────────────────────────────────

_routers: Dict[int, StdioJsonRpcRouter] = {}
_routers_lock = threading.Lock()


def get_stdio_router(process: Any, name: str = "") -> StdioJsonRpcRouter:
    """Return the single router (and stdout reader) for a stdio subprocess.

    Created on first use and shared by every caller afterwards, so there is
    never more than one stdout consumer per process. A router removes itself
    from the registry when stdout closes; requests on a dead process then fail
    with StdioProcessClosed.
    """
    with _routers_lock:
        router = _routers.get(id(process))
        if router is not None and router._process is process:
            return router
        router = StdioJsonRpcRouter(process, name)
        _routers[id(process)] = router
        return router


def _discard_router(router: StdioJsonRpcRouter) -> None:
    with _routers_lock:
        if _routers.get(id(router._process)) is router:
            del _routers[id(router._process)]
