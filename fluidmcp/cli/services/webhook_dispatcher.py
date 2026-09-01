"""Webhook delivery for monitoring events.

Push side of the monitoring contract: drops crash-to-alert latency from one poll
interval (~30s) to under a second.

Design constraints:

- **Fire-and-forget on a bounded queue.** A slow or dead receiver must never
  back-pressure the health monitor that produced the event.
- **HMAC-signed.** The receiver is internet-reachable and its payloads create
  incidents, so it must be able to verify authenticity.
- **SSRF-guarded.** Webhook URLs are attacker-influenced if the API is exposed;
  cloud metadata endpoints and link-local ranges are blocked.
"""

import asyncio
import fnmatch
import hashlib
import hmac
import ipaddress
import json
import os
import socket
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from ..models.events import SEVERITY_ORDER, MonitoringEvent, Severity

#: Ranges never allowed as webhook targets — cloud metadata and loopback-adjacent
#: space. Blocking these prevents the webhook API being used to probe internals.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
]

#: Private ranges — blocked only when FMCP_WEBHOOK_ALLOW_INSECURE is not set,
#: since a same-VPC monitoring receiver is a legitimate and common target.
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]


def _allow_insecure() -> bool:
    return os.getenv("FMCP_WEBHOOK_ALLOW_INSECURE", "").lower() == "true"


def validate_webhook_url(url: str) -> Optional[str]:
    """Validate a webhook target. Returns an error string, or None if allowed."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "malformed URL"

    if parsed.scheme not in ("http", "https"):
        return "URL must use http or https"
    if parsed.scheme == "http" and not _allow_insecure():
        return ("http:// is not allowed — use https, or set "
                "FMCP_WEBHOOK_ALLOW_INSECURE=true for a trusted internal receiver")
    if not parsed.hostname:
        return "URL has no host"

    allowlist = os.getenv("FMCP_WEBHOOK_ALLOWLIST", "").strip()
    if allowlist:
        patterns = [p.strip() for p in allowlist.split(",") if p.strip()]
        if not any(fnmatch.fnmatch(parsed.hostname, p) for p in patterns):
            return f"host '{parsed.hostname}' is not in FMCP_WEBHOOK_ALLOWLIST"

    # Resolve and check every address the host maps to, so a DNS name pointing
    # at metadata space is caught too.
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
        addresses = {info[4][0] for info in infos}
    except Exception:
        # Unresolvable now may resolve later; delivery will simply fail. Not a
        # reason to reject registration.
        return None

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                return f"host resolves to a blocked address ({address})"
        if not _allow_insecure():
            for network in _PRIVATE_NETWORKS:
                if ip in network:
                    return (f"host resolves to a private address ({address}) — set "
                            f"FMCP_WEBHOOK_ALLOW_INSECURE=true to allow this")
    return None


def sign_payload(secret: str, body: bytes) -> str:
    """Compute the X-FMCP-Signature value for a payload."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class WebhookDispatcher:
    """Delivers events to registered receivers with retry and auto-disable."""

    #: Consecutive failures after which a receiver is disabled.
    AUTO_DISABLE_AFTER = 10

    def __init__(self, db: Any = None, max_queue: int = 1000):
        self._db = db
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)
        self._worker: Optional[asyncio.Task] = None
        self._running = False
        self._receivers: List[Dict[str, Any]] = []
        self._failures: Dict[str, int] = {}
        self._dropped = 0
        self._delivered = 0
        self._failed = 0

    def set_db(self, db: Any) -> None:
        self._db = db

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        await self.reload_receivers()
        self._running = True
        self._worker = asyncio.create_task(self._run())
        logger.info(
            f"Webhook dispatcher started ({len(self._receivers)} receiver(s))"
        )

    async def stop(self) -> None:
        self._running = False
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        logger.info("Webhook dispatcher stopped")

    async def reload_receivers(self) -> None:
        """Re-read receivers from persistence."""
        if self._db is None:
            return
        try:
            self._receivers = await self._db.list_webhooks(enabled_only=True)
        except Exception as e:
            logger.error(f"Failed to load webhook receivers: {e}")

    # ── intake ────────────────────────────────────────────────────────────

    def submit(self, event: MonitoringEvent) -> None:
        """Queue an event for delivery. Never raises, never blocks."""
        if not self._receivers:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped % 50 == 1:
                logger.warning(
                    f"Webhook queue full — dropped {self._dropped} event(s). "
                    f"Receiver too slow or unreachable."
                )
        except Exception as e:
            logger.debug(f"Webhook submit failed: {e}")

    # ── delivery ──────────────────────────────────────────────────────────

    async def _run(self) -> None:
        while self._running:
            try:
                event = await self._queue.get()
                try:
                    await self._deliver_all(event)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Webhook dispatcher loop error: {e}")
                await asyncio.sleep(1)

    async def _deliver_all(self, event: MonitoringEvent) -> None:
        for receiver in list(self._receivers):
            if not self._wants(receiver, event):
                continue
            await self._deliver(receiver, event)

    @staticmethod
    def _wants(receiver: Dict[str, Any], event: MonitoringEvent) -> bool:
        """Whether a receiver has subscribed to this event."""
        types = receiver.get("events") or []
        event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
        if types and event_type not in types:
            return False

        minimum = receiver.get("min_severity")
        if minimum:
            try:
                if SEVERITY_ORDER[Severity(event.severity)] < \
                        SEVERITY_ORDER[Severity(minimum)]:
                    return False
            except (ValueError, KeyError):
                pass
        return True

    async def _deliver(self, receiver: Dict[str, Any], event: MonitoringEvent) -> None:
        """Deliver one event to one receiver, with retries."""
        url = receiver.get("url")
        secret = receiver.get("secret") or ""
        webhook_id = receiver.get("id") or url

        body = json.dumps(event.to_dict(), separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "FluidMCP-Webhook/1.0",
            "X-FMCP-Event": event.type.value if hasattr(event.type, "value") else str(event.type),
            "X-FMCP-Delivery": f"dlv_{uuid.uuid4().hex[:20]}",
            "X-FMCP-Timestamp": timestamp,
            "X-FMCP-Gateway": event.gateway_id,
        }
        if secret:
            # Sign timestamp + body so the signature also covers replay window.
            headers["X-FMCP-Signature"] = sign_payload(secret, timestamp.encode() + b"." + body)

        try:
            timeout = float(os.getenv("FMCP_WEBHOOK_TIMEOUT", "10"))
        except (ValueError, TypeError):
            timeout = 10.0
        try:
            max_retries = int(os.getenv("FMCP_WEBHOOK_MAX_RETRIES", "3"))
        except (ValueError, TypeError):
            max_retries = 3

        delay = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, content=body, headers=headers)
                if 200 <= response.status_code < 300:
                    self._delivered += 1
                    self._failures[webhook_id] = 0
                    logger.debug(
                        f"Webhook delivered {event.event_id} to {url} "
                        f"(HTTP {response.status_code})"
                    )
                    return
                logger.warning(
                    f"Webhook {url} returned HTTP {response.status_code} "
                    f"for {event.type} (attempt {attempt}/{max_retries})"
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    f"Webhook delivery to {url} failed "
                    f"(attempt {attempt}/{max_retries}): {e}"
                )

            if attempt < max_retries:
                await asyncio.sleep(delay)
                delay *= 4  # 2s, 8s, 32s

        self._failed += 1
        count = self._failures.get(webhook_id, 0) + 1
        self._failures[webhook_id] = count

        if count >= self.AUTO_DISABLE_AFTER:
            logger.error(
                f"Webhook {url} has failed {count} consecutive deliveries — "
                f"disabling it. Re-enable via the API once the receiver is fixed."
            )
            await self._disable(webhook_id)

    async def _disable(self, webhook_id: str) -> None:
        try:
            if self._db is not None:
                await self._db.set_webhook_enabled(webhook_id, False)
            self._receivers = [
                r for r in self._receivers if (r.get("id") or r.get("url")) != webhook_id
            ]
            self._failures.pop(webhook_id, None)
        except Exception as e:
            logger.error(f"Failed to disable webhook {webhook_id}: {e}")

    async def send_test(self, receiver: Dict[str, Any]) -> Dict[str, Any]:
        """Send a synthetic event to one receiver and report the result."""
        from ..models.events import EventType
        from . import gateway_info

        event = MonitoringEvent(
            type=EventType.GATEWAY_STARTED,
            severity=Severity.INFO,
            server_id=None,
            data={"test": True, "message": "FluidMCP webhook test delivery"},
            event_id=f"evt_test_{uuid.uuid4().hex[:12]}",
            seq=0,
            gateway_id=gateway_info.gateway_id(),
            boot_id=gateway_info.BOOT_ID,
        )

        body = json.dumps(event.to_dict(), separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-FMCP-Event": event.type.value,
            "X-FMCP-Delivery": f"dlv_test_{uuid.uuid4().hex[:12]}",
            "X-FMCP-Timestamp": timestamp,
        }
        secret = receiver.get("secret") or ""
        if secret:
            headers["X-FMCP-Signature"] = sign_payload(
                secret, timestamp.encode() + b"." + body
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    receiver["url"], content=body, headers=headers
                )
            return {
                "delivered": 200 <= response.status_code < 300,
                "status_code": response.status_code,
                "response_body": response.text[:500],
            }
        except Exception as e:
            return {"delivered": False, "error": str(e)[:500]}

    def stats(self) -> Dict[str, Any]:
        return {
            "receivers": len(self._receivers),
            "queue_depth": self._queue.qsize(),
            "delivered": self._delivered,
            "failed": self._failed,
            "dropped": self._dropped,
        }


_dispatcher: Optional[WebhookDispatcher] = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = WebhookDispatcher()
    return _dispatcher
