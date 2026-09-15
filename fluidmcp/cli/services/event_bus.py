"""In-process event bus for monitoring events.

Responsibilities:

- assign a gap-free monotonic ``seq`` to every event (the consumer cursor)
- keep a bounded in-memory ring buffer for fast ``/events`` reads
- persist asynchronously to the database for history beyond the ring
- fan out to SSE subscribers and the webhook dispatcher

**Nothing here may raise into the caller.** Emitters are the health monitor and
the server lifecycle paths; a monitoring failure must never prevent a server
restart. Every public method swallows its own exceptions and logs.
"""

import asyncio
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

from loguru import logger

from ..models.events import (
    DEFAULT_SEVERITY,
    SEVERITY_ORDER,
    EventType,
    MonitoringEvent,
    Severity,
)
from . import gateway_info


def _buffer_size() -> int:
    try:
        return max(50, int(os.getenv("FMCP_EVENT_BUFFER_SIZE", "1000")))
    except (ValueError, TypeError):
        return 1000


class EventBus:
    """Assigns sequence numbers, buffers, persists, and fans out events."""

    def __init__(self, db: Any = None, max_queue: int = 2000):
        self._db = db
        self._seq = 0
        self._buffer: Deque[MonitoringEvent] = deque(maxlen=_buffer_size())
        self._lock = asyncio.Lock()

        # SSE subscribers: each gets its own bounded queue. A slow consumer drops
        # events rather than back-pressuring the emitter.
        self._subscribers: List[asyncio.Queue] = []

        # Persistence is offloaded so emit() never awaits a database write.
        self._persist_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)
        self._persist_task: Optional[asyncio.Task] = None

        # Set by the webhook dispatcher at startup.
        self._webhook_sink: Optional[Callable[[MonitoringEvent], Any]] = None

        self._dropped_persist = 0
        self._dropped_subscriber = 0

    # ── lifecycle ─────────────────────────────────────────────────────────

    def set_db(self, db: Any) -> None:
        self._db = db

    def set_webhook_sink(self, sink: Optional[Callable[[MonitoringEvent], Any]]) -> None:
        """Register the webhook dispatcher's intake function."""
        self._webhook_sink = sink

    def start(self) -> None:
        """Start the background persistence worker."""
        if self._persist_task and not self._persist_task.done():
            return
        self._persist_task = asyncio.create_task(self._persist_worker())
        logger.info("Event bus started")

    async def stop(self) -> None:
        """Drain and stop the persistence worker."""
        if self._persist_task:
            try:
                await asyncio.wait_for(self._persist_queue.join(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Event bus: persistence queue did not drain in 5s")
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass
            self._persist_task = None

        for queue in list(self._subscribers):
            try:
                queue.put_nowait(None)  # Sentinel: closes the SSE generator.
            except asyncio.QueueFull:
                pass
        self._subscribers.clear()
        logger.info("Event bus stopped")

    # ── emit ──────────────────────────────────────────────────────────────

    def emit(
        self,
        event_type: EventType,
        server_id: Optional[str] = None,
        server_name: Optional[str] = None,
        severity: Optional[Severity] = None,
        **data: Any,
    ) -> Optional[MonitoringEvent]:
        """Emit an event. Safe to call from sync or async context.

        Never raises. Returns the event (with ``seq`` assigned) or None if
        emission failed.
        """
        try:
            self._seq += 1
            event = MonitoringEvent(
                type=event_type,
                severity=severity or DEFAULT_SEVERITY.get(event_type, Severity.INFO),
                server_id=server_id,
                server_name=server_name,
                data=data,
                timestamp=datetime.now(timezone.utc),
                event_id=f"evt_{uuid.uuid4().hex[:20]}",
                seq=self._seq,
                gateway_id=gateway_info.gateway_id(),
                boot_id=gateway_info.BOOT_ID,
            )

            self._buffer.append(event)
            self._log(event)
            self._fanout(event)
            self._enqueue_persist(event)
            return event
        except Exception as e:
            logger.error(f"Event bus emit failed for {event_type}: {e}")
            return None

    def _log(self, event: MonitoringEvent) -> None:
        """Mirror the event into the normal log stream at a matching level."""
        target = f" '{event.server_id}'" if event.server_id else ""
        message = f"[event] {event.type.value}{target} seq={event.seq}"
        category = event.data.get("failure_category")
        if category:
            message += f" category={category} owner={event.data.get('failure_owner')}"

        if event.severity == Severity.CRITICAL:
            logger.error(message)
        elif event.severity == Severity.WARNING:
            logger.warning(message)
        else:
            logger.info(message)

    def _fanout(self, event: MonitoringEvent) -> None:
        """Push to SSE subscribers and the webhook dispatcher."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._dropped_subscriber += 1
                logger.debug("Event bus: dropped event for a slow SSE subscriber")
            except Exception:
                pass

        if self._webhook_sink is not None:
            try:
                self._webhook_sink(event)
            except Exception as e:
                logger.error(f"Event bus: webhook sink rejected event: {e}")

    def _enqueue_persist(self, event: MonitoringEvent) -> None:
        if self._db is None:
            return
        try:
            self._persist_queue.put_nowait(event)
        except asyncio.QueueFull:
            self._dropped_persist += 1
            if self._dropped_persist % 100 == 1:
                logger.warning(
                    f"Event bus: persistence queue full, dropped "
                    f"{self._dropped_persist} events (DB slow or unreachable?)"
                )

    async def _persist_worker(self) -> None:
        """Write buffered events to the database, one at a time."""
        while True:
            try:
                event = await self._persist_queue.get()
                try:
                    if self._db is not None:
                        await self._db.save_event(event.to_dict())
                except Exception as e:
                    logger.debug(f"Event bus: failed to persist {event.event_id}: {e}")
                finally:
                    self._persist_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Event bus persistence worker error: {e}")
                await asyncio.sleep(1)

    # ── read ──────────────────────────────────────────────────────────────

    async def list_events(
        self,
        since: Optional[int] = None,
        limit: int = 100,
        severity: Optional[str] = None,
        server_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return events after ``since`` (exclusive), oldest first.

        Served from the in-memory ring when possible; falls back to the database
        when the cursor predates the ring. Ordering is by ``seq``, always
        ascending, so a consumer can take the last element's seq as its next
        cursor without sorting.
        """
        min_rank = SEVERITY_ORDER.get(Severity(severity), 0) if severity else 0

        def _matches(event_dict: Dict[str, Any]) -> bool:
            if server_id and event_dict.get("server_id") != server_id:
                return False
            if event_type and event_dict.get("type") != event_type:
                return False
            if min_rank:
                try:
                    rank = SEVERITY_ORDER[Severity(event_dict.get("severity", "info"))]
                except (ValueError, KeyError):
                    rank = 0
                if rank < min_rank:
                    return False
            return True

        buffered = [e.to_dict() for e in self._buffer]
        oldest_buffered = buffered[0]["seq"] if buffered else None

        # The ring covers the request when it starts at or before the cursor+1.
        ring_covers = (
            since is None
            or oldest_buffered is None
            or oldest_buffered <= since + 1
        )

        if ring_covers:
            candidates = [
                e for e in buffered
                if (since is None or e["seq"] > since) and _matches(e)
            ]
            return candidates[:limit]

        # Cursor is older than the ring — read history from the database.
        if self._db is not None:
            try:
                rows = await self._db.list_events_since(
                    since=since,
                    limit=limit,
                    severity=severity,
                    server_id=server_id,
                    event_type=event_type,
                    boot_id=gateway_info.BOOT_ID,
                )
                if rows:
                    return rows
            except Exception as e:
                logger.warning(f"Event bus: DB event read failed, serving from ring: {e}")

        return [
            e for e in buffered
            if (since is None or e["seq"] > since) and _matches(e)
        ][:limit]

    @property
    def latest_seq(self) -> int:
        return self._seq

    def stats(self) -> Dict[str, Any]:
        return {
            "latest_seq": self._seq,
            "buffered": len(self._buffer),
            "buffer_capacity": self._buffer.maxlen,
            "subscribers": len(self._subscribers),
            "persist_queue_depth": self._persist_queue.qsize(),
            "dropped_persist": self._dropped_persist,
            "dropped_subscriber": self._dropped_subscriber,
        }

    # ── subscribe (SSE) ───────────────────────────────────────────────────

    def subscribe(self, maxsize: int = 200) -> asyncio.Queue:
        """Register an SSE subscriber. Caller must unsubscribe when done."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass


#: Process-wide singleton. Created lazily so importing this module is cheap.
_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Return the process-wide event bus, creating it if needed."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def emit(
    event_type: EventType,
    server_id: Optional[str] = None,
    server_name: Optional[str] = None,
    severity: Optional[Severity] = None,
    **data: Any,
) -> Optional[MonitoringEvent]:
    """Module-level convenience emitter. Never raises."""
    try:
        return get_event_bus().emit(
            event_type,
            server_id=server_id,
            server_name=server_name,
            severity=severity,
            **data,
        )
    except Exception as e:
        logger.error(f"emit() failed for {event_type}: {e}")
        return None
