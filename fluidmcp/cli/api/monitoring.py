"""Monitoring API — the contract external monitoring systems consume.

Endpoints:

- ``GET  /monitoring/health``                  fleet rollup (primary poll target)
- ``GET  /monitoring/gateway``                 FluidMCP's own health + boot identity
- ``GET  /monitoring/events``                  incremental event feed (seq cursor)
- ``GET  /monitoring/stream``                  SSE live event push
- ``GET  /monitoring/servers/{id}/diagnosis``  why is this server failing
- ``GET  /monitoring/uptime``                  uptime %, MTTR, MTBF per server
- ``POST /monitoring/webhooks``                register a push receiver
- ``GET|DELETE /monitoring/webhooks[/{id}]``   manage receivers
- ``POST /monitoring/webhooks/{id}/test``      synthetic delivery

Design notes:

- ``/health`` serves from in-memory state plus at most one DB read: it is polled
  every 30s forever, so it must stay cheap.
- ``/events`` is cursor-based on ``seq``, never on timestamps — clock skew and
  same-millisecond writes cause silent event loss with timestamp cursors.
- Every payload carries ``gateway_id`` and ``boot_id`` so a consumer can detect a
  gateway restart (which resets ``seq``) and aggregate several deployments.
"""

import asyncio
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from ..models.events import EventType, MonitoringEvent, Severity
from ..services import gateway_info
from ..services.dependency_probe import DependencyProbe
from ..services.event_bus import get_event_bus
from ..services.failure_classifier import diagnose
from ..utils.error_utils import redact_secrets
from ..services.network_handle import NetworkSubprocessHandle
from ..services.tool_error_tracker import get_tool_error_tracker
from ..services.webhook_dispatcher import (
    get_webhook_dispatcher,
    validate_webhook_url,
)

try:
    import psutil as _psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

router = APIRouter()
security = HTTPBearer(auto_error=False)


def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Bearer-token guard, matching the management API's behaviour."""
    from ..auth import verify_token
    verify_token(credentials)
    return credentials.credentials if credentials else None


def get_server_manager(request: Request):
    if not hasattr(request.app.state, "server_manager"):
        raise HTTPException(500, "ServerManager not initialized")
    return request.app.state.server_manager


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _human_bytes(value: Optional[int]) -> Optional[str]:
    if not value:
        return None
    return f"{value / (1024 * 1024):.1f} MB"


# ==================== Fleet rollup ====================

@router.get("/monitoring/health")
async def fleet_health(
    request: Request,
    include_disabled: bool = Query(False, description="Include disabled servers"),
    token: str = Depends(get_token),
):
    """Fleet-wide health rollup — every server plus a summary, in one call.

    This is the primary polling endpoint. A monitoring system should treat a
    failed call or a stale ``generated_at`` as its highest-severity alert: a dead
    gateway sends no webhooks, so silence is otherwise indistinguishable from
    everything being healthy.
    """
    manager = get_server_manager(request)
    tracker = get_tool_error_tracker()
    monitor = getattr(manager, "_health_monitor", None)
    probe: Optional[DependencyProbe] = getattr(monitor, "_dependency_probe", None) if monitor else None

    try:
        configs = await manager.db.list_server_configs(
            enabled_only=not include_disabled, include_deleted=False
        )
    except Exception as e:
        logger.error(f"[monitoring] Failed to list server configs: {e}")
        configs = []

    # Merge in-memory-only configs (servers started without persistence).
    known = {c.get("id") for c in configs}
    for server_id, config in manager.configs.items():
        if server_id not in known:
            merged = dict(config)
            merged.setdefault("id", server_id)
            configs.append(merged)

    servers: List[Dict[str, Any]] = []
    summary = {
        "total": 0, "running": 0, "degraded": 0, "failed": 0,
        "stopped": 0, "config_error": 0, "unstable": 0,
        "dependency_failed": 0, "crashes_last_hour": 0,
    }

    for config in configs:
        server_id = config.get("id")
        if not server_id:
            continue

        try:
            status = await manager.get_server_status(server_id)
        except Exception as e:
            logger.warning(f"[monitoring] status failed for '{server_id}': {e}")
            status = {"id": server_id, "state": "unknown"}

        state = status.get("state", "unknown")
        error_snapshot = tracker.snapshot(server_id)
        probe_status = probe.status(server_id) if probe else {}
        config_issues = (manager.config_issues.get(server_id)
                         if hasattr(manager, "config_issues") else None)

        # Effective state layers runtime health over the raw process state: a
        # running process whose every tool call fails is not "running" as far as
        # a monitoring dashboard is concerned, and a server that cannot start
        # because a credential is missing is not merely "stopped".
        has_config_errors = bool(config_issues and config_issues.get("errors"))
        effective_state = state

        if state == "running":
            # Runtime failure outranks config: the server did start, so whatever
            # is breaking calls now is the more actionable signal.
            if probe_status.get("dependency_failed") or error_snapshot.get("degraded"):
                effective_state = "degraded"
            elif has_config_errors:
                effective_state = "config_error"
        elif has_config_errors:
            # Not running AND misconfigured — the config is why. Report that
            # rather than a bare "failed"/"not_found", which tells an operator
            # nothing about what to do.
            effective_state = "config_error"
        elif state == "not_found":
            # The server is in the config list (we are iterating it), so
            # "not_found" only means no instance record exists yet. From a
            # monitoring standpoint that is "never started", not "unknown".
            effective_state = "stopped"

        entry: Dict[str, Any] = {
            "id": server_id,
            "name": config.get("name") or server_id,
            "state": effective_state,
            "process_state": state,
            "pid": status.get("pid"),
            "uptime_seconds": status.get("uptime"),
            "restart_count": status.get("restart_count", 0),
            "stability": status.get("stability", "stable"),
            "transport": status.get("transport"),
            "error_rate_5m": error_snapshot.get("error_rate_5m", 0.0),
            "calls_5m": error_snapshot.get("calls_5m", 0),
            "failing_tools": error_snapshot.get("failing_tools", []),
            "config_issues": {
                "missing_env": (config_issues or {}).get("missing_env", []),
                "placeholder_env": (config_issues or {}).get("placeholder_env", []),
                "unresolved_env": (config_issues or {}).get("unresolved_env", []),
            } if config_issues else {"missing_env": [], "placeholder_env": [], "unresolved_env": []},
            **probe_status,
        }

        # Resource snapshot from the health monitor's cache (no fresh psutil call).
        if monitor is not None:
            snapshot = monitor._last_resource_snapshot.get(server_id) or {}
            entry["memory_rss_bytes"] = snapshot.get("memory_rss_bytes")
            entry["memory_rss_human"] = _human_bytes(snapshot.get("memory_rss_bytes"))
            entry["cpu_percent"] = snapshot.get("cpu_percent")
            entry["active_requests"] = snapshot.get("active_requests")
            try:
                entry["memory_trend"] = monitor.get_memory_trend(server_id)
            except Exception:
                entry["memory_trend"] = "unknown"

        # Last classified error, whatever its source.
        last_error = tracker.last_error(server_id)
        if last_error:
            entry["failure_category"] = last_error.get("failure_category")
            entry["failure_owner"] = last_error.get("failure_owner")
            entry["last_error"] = last_error.get("message")
        elif config_issues and config_issues.get("errors"):
            entry["failure_category"] = "missing_credentials"
            entry["failure_owner"] = "customer"
            entry["last_error"] = config_issues.get("remediation")

        # Most recent crash, for context on a currently-running server.
        try:
            crashes = await manager.db.list_crash_events(server_id, limit=1)
            if crashes:
                crash = crashes[0]
                timestamp = crash.get("timestamp")
                entry["last_crash"] = {
                    "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat")
                    else timestamp,
                    "exit_code": crash.get("exit_code"),
                    "exit_label": crash.get("exit_label"),
                }
        except Exception:
            pass

        servers.append(entry)

        summary["total"] += 1
        if effective_state in summary:
            summary[effective_state] += 1
        if entry.get("stability") == "unstable":
            summary["unstable"] += 1
        if probe_status.get("dependency_failed"):
            summary["dependency_failed"] += 1

    # Fleet crash count over the last hour.
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()
    total_crashes = 0
    for entry in servers:
        try:
            total_crashes += await manager.db.count_crash_events_since(
                entry["id"], one_hour_ago
            )
        except Exception:
            pass
    summary["crashes_last_hour"] = total_crashes

    database_connected = _db_connected(request)
    config_status = gateway_info.validate_gateway_config(db_connected=database_connected)

    return {
        **gateway_info.identity(),
        "generated_at": _now_iso(),
        "gateway": {
            "status": _gateway_status(config_status, database_connected),
            "uptime_seconds": round(gateway_info.uptime_seconds(), 1),
            "database": "connected" if database_connected else "disconnected",
            "config_valid": config_status["valid"],
            "health_monitor_running": bool(monitor and monitor.is_running()),
        },
        "summary": summary,
        "servers": servers,
    }


def _db_connected(request: Request) -> bool:
    db = getattr(request.app.state, "db_manager", None)
    return bool(db is not None and getattr(db, "client", None) is not None)


def _gateway_status(config_status: Dict[str, Any], database_connected: bool) -> str:
    if config_status.get("errors"):
        return "degraded"
    if not database_connected:
        return "degraded"
    return "healthy"


# ==================== Gateway self-monitoring ====================

@router.get("/monitoring/gateway")
async def gateway_health(request: Request, token: str = Depends(get_token)):
    """FluidMCP's own health: boot identity, config validity, self-resources.

    ``boot_id`` is the field that matters most — it changes only when the process
    restarts, which is what lets a monitoring system distinguish a deploy from a
    crash from a network blip.
    """
    manager = getattr(request.app.state, "server_manager", None)
    database_connected = _db_connected(request)
    config_status = gateway_info.validate_gateway_config(db_connected=database_connected)
    bus = get_event_bus()
    dispatcher = get_webhook_dispatcher()
    monitor = getattr(manager, "_health_monitor", None) if manager else None

    boots: List[Dict[str, Any]] = []
    if manager is not None:
        try:
            boots = await manager.db.list_boot_records(
                gateway_id=gateway_info.gateway_id(), limit=5
            )
        except Exception:
            pass

    return {
        **gateway_info.identity(),
        "generated_at": _now_iso(),
        "status": _gateway_status(config_status, database_connected),
        "config": config_status,
        "database": {
            "connected": database_connected,
            "persistence_enabled": database_connected,
        },
        "resources": gateway_info.self_resources(),
        "servers_managed": len(manager.processes) if manager else 0,
        "health_monitor": {
            "running": bool(monitor and monitor.is_running()),
            "check_interval_seconds": getattr(monitor, "check_interval", None),
        },
        "event_bus": bus.stats(),
        "webhooks": dispatcher.stats(),
        "recent_boots": boots,
    }


# ==================== Event feed ====================

@router.get("/monitoring/events")
async def list_events(
    request: Request,
    since: Optional[int] = Query(None, ge=0, description="Last seq processed (exclusive)"),
    limit: int = Query(100, ge=1, le=500),
    severity: Optional[str] = Query(None, pattern="^(info|warning|critical)$"),
    server_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None, alias="type"),
    token: str = Depends(get_token),
):
    """Incremental event feed, ordered by ``seq`` ascending.

    Persist ``latest_seq`` after each batch and pass it back as ``since``. Key
    the cursor on ``(gateway_id, boot_id)``: ``seq`` restarts at 1 on every
    gateway boot, so a changed ``boot_id`` means reset the cursor to 0.
    """
    bus = get_event_bus()
    events = await bus.list_events(
        since=since,
        limit=limit,
        severity=severity,
        server_id=server_id,
        event_type=type,
    )
    return {
        **gateway_info.identity(),
        "generated_at": _now_iso(),
        "latest_seq": bus.latest_seq,
        "returned": len(events),
        "events": events,
    }


@router.get("/monitoring/stream")
async def stream_events(
    request: Request,
    severity: Optional[str] = Query(None, pattern="^(info|warning|critical)$"),
    server_id: Optional[str] = Query(None),
    token: str = Depends(get_token),
):
    """SSE live event stream.

    Emits a ``: heartbeat`` comment every 15s; a consumer seeing no heartbeat for
    45s should reconnect. The stream does not replay events missed while
    disconnected — always backfill via ``/monitoring/events?since=<cursor>`` on
    reconnect.
    """
    from ..models.events import SEVERITY_ORDER

    bus = get_event_bus()
    queue = bus.subscribe()
    min_rank = SEVERITY_ORDER.get(Severity(severity), 0) if severity else 0

    async def generate():
        try:
            # Preamble tells the consumer which boot it is attached to, so it can
            # decide whether its stored cursor is still valid.
            yield (
                "event: connected\ndata: "
                + json.dumps({
                    **gateway_info.identity(),
                    "latest_seq": bus.latest_seq,
                })
                + "\n\n"
            )

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if event is None:  # Shutdown sentinel from the bus.
                    break

                if server_id and event.server_id != server_id:
                    continue
                if min_rank and SEVERITY_ORDER.get(Severity(event.severity), 0) < min_rank:
                    continue

                event_name = (
                    event.type.value if hasattr(event.type, "value") else str(event.type)
                )
                yield f"event: {event_name}\ndata: {json.dumps(event.to_dict())}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[monitoring] SSE stream error: {e}")
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering.
        },
    )


# ==================== Diagnosis ====================

@router.get("/monitoring/servers/{id}/diagnosis")
async def server_diagnosis(
    request: Request,
    id: str,
    stderr_lines: int = Query(40, ge=1, le=200),
    token: str = Depends(get_token),
):
    """Why is this server failing — classification, evidence, and remediation.

    ``summary`` and ``remediation`` are written to be pasted straight into a
    ticket or a message to the customer.
    """
    manager = get_server_manager(request)
    tracker = get_tool_error_tracker()
    monitor = getattr(manager, "_health_monitor", None)
    probe: Optional[DependencyProbe] = getattr(monitor, "_dependency_probe", None) if monitor else None

    config = manager.configs.get(id) or await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    status = await manager.get_server_status(id)

    # Gather evidence.
    stderr_text = ""
    try:
        tail = manager.get_stderr_tail(id, lines=stderr_lines)
        stderr_text = "\n".join(tail.get("lines", []))
    except Exception as e:
        logger.debug(f"[monitoring] stderr read failed for '{id}': {e}")

    tool_stats = tracker.tool_stats(id)
    tool_errors = [
        stat["last_error"] for stat in tool_stats
        if stat.get("last_error") and stat["errors"] > 0
    ]

    crashes: List[Dict[str, Any]] = []
    try:
        crashes = await manager.db.list_crash_events(id, limit=5)
    except Exception:
        pass

    exit_code = status.get("exit_code")
    if exit_code is None and crashes:
        exit_code = crashes[0].get("exit_code")

    config_issues = (manager.config_issues.get(id)
                     if hasattr(manager, "config_issues") else None)

    verdict = diagnose(
        exit_code=exit_code,
        stderr=stderr_text or None,
        tool_errors=tool_errors or None,
        config_issues=config_issues,
    )

    # The verdict's evidence quotes raw stderr and tool errors, which routinely
    # contain connection strings. Redact before returning — this response is
    # meant to be pasted into tickets and forwarded to customers.
    for item in verdict.get("evidence", []):
        for field in ("sample", "matched", "line"):
            if isinstance(item.get(field), str):
                item[field] = redact_secrets(item[field])

    # Restart attribution: say plainly whether restarting would help, because a
    # restart loop on a credentials problem just hides the fault.
    restart_would_help = verdict.get("restart_would_help")
    is_dependency = verdict.get("is_dependency_failure", False)

    if restart_would_help is False:
        restart_reason = (
            "Restarting will not fix this. The fault is outside the process — a "
            "credential, a configuration value, or an unreachable dependency — so "
            "FluidMCP does not restart automatically. A restart loop here only "
            "hides the cause. Apply the remediation above instead."
        )
    elif is_dependency:
        restart_reason = (
            "A restart may clear this (for example a leaked connection pool), but "
            "if it recurs the dependency itself needs attention."
        )
    else:
        restart_reason = (
            "Process-level failure — FluidMCP restarts this automatically with "
            "exponential backoff, up to max_restarts."
        )

    auto_restart = {
        "attempted": bool(status.get("restart_count", 0)),
        "restart_count": status.get("restart_count", 0),
        "would_help": restart_would_help,
        "reason": restart_reason,
    }

    error_rate, samples = tracker.server_error_rate(id)

    for crash in crashes:
        crash.pop("_id", None)
        if hasattr(crash.get("timestamp"), "isoformat"):
            crash["timestamp"] = crash["timestamp"].isoformat()

    return {
        **gateway_info.identity(),
        "generated_at": _now_iso(),
        "server_id": id,
        "state": status.get("state"),
        "diagnosis": {
            "failure_category": verdict.get("failure_category"),
            "owner": verdict.get("failure_owner"),
            "confidence": verdict.get("confidence"),
            "summary": verdict.get("summary"),
            "remediation": verdict.get("remediation"),
            "is_dependency_failure": verdict.get("is_dependency_failure", False),
            "evidence": verdict.get("evidence", []),
        },
        "error_rate_5m": error_rate,
        "calls_5m": samples,
        "failing_tools": tracker.failing_tools(id),
        "tool_stats": tool_stats,
        "dependency_probe": probe.status(id) if probe else {"configured": False},
        "config_issues": config_issues or {},
        "recent_crashes": crashes,
        "auto_restart": auto_restart,
    }


# ==================== Uptime / SLA ====================

_WINDOWS = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000}


@router.get("/monitoring/uptime")
async def uptime_report(
    request: Request,
    window: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
    server_id: Optional[str] = Query(None),
    token: str = Depends(get_token),
):
    """Per-server uptime %, MTTR, MTBF over a window.

    ``degraded_seconds`` is reported separately from downtime: a server that was
    up but unusable is not uptime as far as a customer is concerned, and
    conflating them makes the SLA number disputable.
    """
    manager = get_server_manager(request)
    window_seconds = _WINDOWS[window]
    since_ts = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).timestamp()

    try:
        transitions = await manager.db.list_state_transitions(
            server_id=server_id, since_ts=since_ts, limit=10000
        )
    except Exception as e:
        logger.error(f"[monitoring] Failed to read state transitions: {e}")
        transitions = []

    by_server: Dict[str, List[Dict[str, Any]]] = {}
    for transition in transitions:
        by_server.setdefault(transition.get("server_id"), []).append(transition)

    # Include currently-known servers even with no transitions in the window.
    if server_id:
        by_server.setdefault(server_id, [])
    else:
        for known in list(manager.configs.keys()):
            by_server.setdefault(known, [])

    reports = []
    for sid, rows in by_server.items():
        reports.append(_uptime_for_server(sid, rows, window_seconds))

    fleet_uptime = (
        round(sum(r["uptime_pct"] for r in reports) / len(reports), 2)
        if reports else 100.0
    )

    return {
        **gateway_info.identity(),
        "generated_at": _now_iso(),
        "window": window,
        "window_seconds": window_seconds,
        "note": (
            "Uptime is computed from recorded state transitions. Periods before the "
            "first transition in the window are treated as the server's state at "
            "that transition."
        ),
        "servers": sorted(reports, key=lambda r: r["uptime_pct"]),
        "fleet": {
            "uptime_pct": fleet_uptime,
            "servers_with_incidents": sum(1 for r in reports if r["crash_count"] > 0),
            "total_crashes": sum(r["crash_count"] for r in reports),
        },
    }


_UP_STATES = {"running", "healthy", "started"}
_DEGRADED_STATES = {"degraded", "unhealthy", "config_error"}


def _uptime_for_server(
    server_id: str,
    transitions: List[Dict[str, Any]],
    window_seconds: int,
) -> Dict[str, Any]:
    """Integrate time-in-state from an ordered transition list."""
    if not transitions:
        # No transitions recorded: assume steady state, report full uptime with
        # a flag so a consumer knows this is an assumption, not a measurement.
        return {
            "server_id": server_id,
            "uptime_pct": 100.0,
            "downtime_seconds": 0,
            "degraded_seconds": 0,
            "crash_count": 0,
            "restart_count": 0,
            "mttr_seconds": None,
            "mtbf_seconds": None,
            "measured": False,
        }

    def as_timestamp(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()

    ordered = sorted(
        [t for t in transitions if as_timestamp(t.get("timestamp")) is not None],
        key=lambda t: as_timestamp(t["timestamp"]),
    )
    if not ordered:
        return _uptime_for_server(server_id, [], window_seconds)

    now = datetime.now(timezone.utc).timestamp()
    window_start = now - window_seconds

    down_seconds = 0.0
    degraded_seconds = 0.0
    crash_count = 0
    restart_count = 0
    recovery_durations: List[float] = []
    failure_times: List[float] = []

    # Walk consecutive transitions, attributing the interval to the state entered.
    for index, transition in enumerate(ordered):
        start = max(as_timestamp(transition["timestamp"]), window_start)
        end = (
            as_timestamp(ordered[index + 1]["timestamp"])
            if index + 1 < len(ordered) else now
        )
        duration = max(0.0, end - start)
        state = (transition.get("to_state") or "").lower()

        if state in _DEGRADED_STATES:
            degraded_seconds += duration
        elif state not in _UP_STATES:
            down_seconds += duration
            failure_times.append(start)
            if state in ("failed", "crashed"):
                crash_count += 1
            # Time until the next up transition is the recovery time.
            for later in ordered[index + 1:]:
                if (later.get("to_state") or "").lower() in _UP_STATES:
                    recovery_durations.append(
                        max(0.0, as_timestamp(later["timestamp"]) - start)
                    )
                    break

        if state in ("restarting", "started") and index > 0:
            restart_count += 1

    uptime_seconds = max(0.0, window_seconds - down_seconds)
    mtbf = None
    if len(failure_times) > 1:
        gaps = [
            failure_times[i + 1] - failure_times[i]
            for i in range(len(failure_times) - 1)
        ]
        mtbf = round(sum(gaps) / len(gaps), 1)

    return {
        "server_id": server_id,
        "uptime_pct": round(uptime_seconds / window_seconds * 100, 2),
        "downtime_seconds": round(down_seconds, 1),
        "degraded_seconds": round(degraded_seconds, 1),
        "crash_count": crash_count,
        "restart_count": restart_count,
        "mttr_seconds": (
            round(sum(recovery_durations) / len(recovery_durations), 1)
            if recovery_durations else None
        ),
        "mtbf_seconds": mtbf,
        "measured": True,
    }


# ==================== Webhooks ====================

class WebhookCreate(BaseModel):
    """Registration payload for a webhook receiver."""
    url: str = Field(..., max_length=2048)
    events: List[str] = Field(default_factory=list, max_length=40)
    secret: Optional[str] = Field(None, min_length=16, max_length=256)
    min_severity: Optional[str] = Field(None, pattern="^(info|warning|critical)$")
    description: Optional[str] = Field(None, max_length=500)

    @field_validator("events")
    @classmethod
    def validate_events(cls, values: List[str]) -> List[str]:
        valid = {e.value for e in EventType}
        unknown = [v for v in values if v not in valid]
        if unknown:
            raise ValueError(
                f"Unknown event type(s): {', '.join(unknown)}. "
                f"Valid types: {', '.join(sorted(valid))}"
            )
        return values


@router.post("/monitoring/webhooks", status_code=201)
async def create_webhook(
    request: Request,
    payload: WebhookCreate,
    token: str = Depends(get_token),
):
    """Register a webhook receiver for pushed monitoring events.

    A generated secret is returned **once** — store it, since subsequent reads
    redact it. Deliveries are signed as
    ``HMAC-SHA256(secret, "<timestamp>.<body>")`` in ``X-FMCP-Signature``.
    """
    manager = get_server_manager(request)

    error = validate_webhook_url(payload.url)
    if error:
        raise HTTPException(400, f"Invalid webhook URL: {error}")

    secret = payload.secret or f"whsec_{secrets.token_urlsafe(32)}"
    webhook = {
        "id": f"wh_{uuid.uuid4().hex[:16]}",
        "url": payload.url,
        "events": payload.events,
        "min_severity": payload.min_severity,
        "description": payload.description,
        "secret": secret,
        "enabled": True,
        "created_at": datetime.now(timezone.utc),
    }

    if not await manager.db.save_webhook(webhook):
        raise HTTPException(500, "Failed to persist webhook")

    dispatcher = get_webhook_dispatcher()
    dispatcher.set_db(manager.db)
    await dispatcher.reload_receivers()

    logger.info(f"[monitoring] Registered webhook {webhook['id']} -> {payload.url}")

    return {
        "id": webhook["id"],
        "url": webhook["url"],
        "events": webhook["events"],
        "min_severity": webhook["min_severity"],
        "enabled": True,
        "secret": secret,
        "secret_note": "Store this now — it is not returned again.",
        "signature_scheme": 'X-FMCP-Signature: sha256=HMAC_SHA256(secret, "<X-FMCP-Timestamp>.<raw_body>")',
    }


@router.get("/monitoring/webhooks")
async def list_webhooks(request: Request, token: str = Depends(get_token)):
    """List webhook receivers. Secrets are redacted."""
    manager = get_server_manager(request)
    hooks = await manager.db.list_webhooks(enabled_only=False)
    for hook in hooks:
        if hook.get("secret"):
            hook["secret"] = "***redacted***"
        if hasattr(hook.get("created_at"), "isoformat"):
            hook["created_at"] = hook["created_at"].isoformat()
    return {"webhooks": hooks, "count": len(hooks)}


@router.delete("/monitoring/webhooks/{webhook_id}")
async def delete_webhook(
    request: Request, webhook_id: str, token: str = Depends(get_token)
):
    """Delete a webhook receiver."""
    manager = get_server_manager(request)
    if not await manager.db.delete_webhook(webhook_id):
        raise HTTPException(404, f"Webhook '{webhook_id}' not found")

    dispatcher = get_webhook_dispatcher()
    await dispatcher.reload_receivers()
    return {"deleted": True, "id": webhook_id}


@router.post("/monitoring/webhooks/{webhook_id}/test")
async def test_webhook(
    request: Request, webhook_id: str, token: str = Depends(get_token)
):
    """Send a synthetic event to one receiver and report the delivery result."""
    manager = get_server_manager(request)
    hook = await manager.db.get_webhook(webhook_id)
    if not hook:
        raise HTTPException(404, f"Webhook '{webhook_id}' not found")

    result = await get_webhook_dispatcher().send_test(hook)
    return {"id": webhook_id, "url": hook.get("url"), **result}


@router.post("/monitoring/webhooks/{webhook_id}/enable")
async def enable_webhook(
    request: Request,
    webhook_id: str,
    enabled: bool = Query(True),
    token: str = Depends(get_token),
):
    """Re-enable a webhook that was auto-disabled after repeated failures."""
    manager = get_server_manager(request)
    if not await manager.db.set_webhook_enabled(webhook_id, enabled):
        raise HTTPException(404, f"Webhook '{webhook_id}' not found")

    dispatcher = get_webhook_dispatcher()
    await dispatcher.reload_receivers()
    return {"id": webhook_id, "enabled": enabled}


# ==================== Reference ====================

@router.get("/monitoring/event-types")
async def event_types(token: str = Depends(get_token)):
    """Enumerate every event type with its default severity.

    Lets a consumer validate its alert-rule configuration against the running
    gateway instead of a doc that may have drifted.
    """
    from ..models.events import DEFAULT_SEVERITY

    return {
        "event_types": [
            {"type": event.value, "default_severity": DEFAULT_SEVERITY[event].value}
            for event in EventType
        ]
    }
