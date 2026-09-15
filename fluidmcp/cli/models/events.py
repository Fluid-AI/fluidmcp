"""Monitoring event types and envelope.

Events are the contract between FluidMCP and external monitoring systems.
Every event carries a monotonic ``seq`` that consumers use as a cursor, and a
``boot_id`` identifying the gateway process that produced it. A consumer keyed
on ``(gateway_id, boot_id)`` can detect a gateway restart (which resets ``seq``)
and re-sync without gaps or duplicates.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class Severity(str, Enum):
    """Event severity. Ordered — see SEVERITY_ORDER for filtering."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


class EventType(str, Enum):
    """All monitoring event types.

    Kept as a closed enum so the integration guide's reference table and the
    emitted values cannot drift apart.
    """
    # Server lifecycle
    SERVER_STARTED = "server.started"
    SERVER_STOPPED = "server.stopped"
    SERVER_CRASHED = "server.crashed"
    SERVER_RESTARTING = "server.restarting"
    SERVER_RESTARTED = "server.restarted"
    SERVER_RESTART_FAILED = "server.restart_failed"
    SERVER_UNSTABLE = "server.unstable"
    SERVER_RECOVERED = "server.recovered"
    SERVER_ZOMBIE = "server.zombie"

    # Degradation / dependencies
    SERVER_DEGRADED = "server.degraded"
    SERVER_DEPENDENCY_FAILED = "server.dependency_failed"

    # Configuration
    SERVER_CONFIG_INVALID = "server.config_invalid"
    GATEWAY_CONFIG_INVALID = "gateway.config_invalid"

    # Resources
    RESOURCE_MEMORY_WARNING = "resource.memory_warning"
    RESOURCE_MEMORY_KILLED = "resource.memory_killed"
    RESOURCE_CPU_STUCK = "resource.cpu_stuck"

    # Gateway lifecycle
    GATEWAY_STARTED = "gateway.started"
    GATEWAY_STOPPING = "gateway.stopping"


#: Default severity per event type. Emitters may override.
DEFAULT_SEVERITY: Dict[EventType, Severity] = {
    EventType.SERVER_STARTED: Severity.INFO,
    EventType.SERVER_STOPPED: Severity.INFO,
    EventType.SERVER_CRASHED: Severity.CRITICAL,
    EventType.SERVER_RESTARTING: Severity.WARNING,
    EventType.SERVER_RESTARTED: Severity.INFO,
    EventType.SERVER_RESTART_FAILED: Severity.CRITICAL,
    EventType.SERVER_UNSTABLE: Severity.CRITICAL,
    EventType.SERVER_RECOVERED: Severity.INFO,
    EventType.SERVER_ZOMBIE: Severity.CRITICAL,
    EventType.SERVER_DEGRADED: Severity.WARNING,
    EventType.SERVER_DEPENDENCY_FAILED: Severity.CRITICAL,
    EventType.SERVER_CONFIG_INVALID: Severity.CRITICAL,
    EventType.GATEWAY_CONFIG_INVALID: Severity.CRITICAL,
    EventType.RESOURCE_MEMORY_WARNING: Severity.WARNING,
    EventType.RESOURCE_MEMORY_KILLED: Severity.CRITICAL,
    EventType.RESOURCE_CPU_STUCK: Severity.WARNING,
    EventType.GATEWAY_STARTED: Severity.INFO,
    EventType.GATEWAY_STOPPING: Severity.INFO,
}


@dataclass
class MonitoringEvent:
    """A single monitoring event.

    ``seq`` is assigned by the EventBus at emit time, not by the caller.
    """
    type: EventType
    severity: Severity
    server_id: Optional[str] = None
    server_name: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = ""
    seq: int = 0
    gateway_id: str = ""
    boot_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe representation. This is the wire format consumers see."""
        return {
            "event_id": self.event_id,
            "seq": self.seq,
            "type": self.type.value if isinstance(self.type, EventType) else str(self.type),
            "severity": (
                self.severity.value if isinstance(self.severity, Severity) else str(self.severity)
            ),
            "gateway_id": self.gateway_id,
            "boot_id": self.boot_id,
            "server_id": self.server_id,
            "server_name": self.server_name,
            "timestamp": _iso(self.timestamp),
            "data": self.data,
        }


def _iso(ts: Any) -> Optional[str]:
    """Render a timestamp as an ISO-8601 UTC string with a trailing Z."""
    if ts is None:
        return None
    if isinstance(ts, str):
        return ts
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(ts)
