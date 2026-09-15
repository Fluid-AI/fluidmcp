"""Gateway self-monitoring: boot identity, config validity, and self-resources.

Everything else in the monitoring stack watches the *MCP servers*. This module
watches **FluidMCP itself** — the case where the container is redeployed with a
bad Mongo URI or a missing bearer token and answers health checks while being
functionally broken.

The key export is ``boot_id``: generated once per process. A monitoring system
comparing ``boot_id`` across polls can tell a deploy from a crash from a network
blip, which is otherwise undiagnosable from outside.
"""

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

try:
    import psutil
    _PSUTIL = True
except ImportError:  # pragma: no cover - psutil is a hard dependency in practice
    _PSUTIL = False

#: Generated once at import — identifies this gateway process for its lifetime.
BOOT_ID: str = f"boot_{uuid.uuid4().hex[:20]}"

#: Wall-clock and monotonic start markers.
STARTED_AT: datetime = datetime.now(timezone.utc)
_STARTED_MONOTONIC: float = time.monotonic()

#: Set from the persisted boot record once the DB is reachable (see record_boot).
_BOOT_COUNT: int = 0

#: Populated by validate_gateway_config() at startup.
_CONFIG_ERRORS: List[Dict[str, str]] = []
_CONFIG_WARNINGS: List[Dict[str, str]] = []

#: Event-loop lag, refreshed by the lag monitor task.
_EVENT_LOOP_LAG_MS: float = 0.0


def gateway_id() -> str:
    """Stable identifier for this deployment. Set FMCP_GATEWAY_ID in production."""
    return os.getenv("FMCP_GATEWAY_ID") or os.getenv("RAILWAY_SERVICE_NAME") or "fluidmcp"


def uptime_seconds() -> float:
    """Seconds since this process started."""
    return time.monotonic() - _STARTED_MONOTONIC


def boot_count() -> int:
    """Number of times this gateway has booted (0 until a boot record is written)."""
    return _BOOT_COUNT


def set_boot_count(count: int) -> None:
    """Record the boot count read back from persistence."""
    global _BOOT_COUNT
    _BOOT_COUNT = count


def set_event_loop_lag(lag_ms: float) -> None:
    """Record the most recent event-loop lag sample."""
    global _EVENT_LOOP_LAG_MS
    _EVENT_LOOP_LAG_MS = lag_ms


def event_loop_lag_ms() -> float:
    """Most recent event-loop lag in milliseconds.

    The highest-signal gateway metric: a blocked loop stops the gateway
    responding to everything, including its own health checks, and is invisible
    in CPU and memory figures.
    """
    return round(_EVENT_LOOP_LAG_MS, 1)


# ==================== Configuration validation ====================

def validate_gateway_config(db_connected: bool = True) -> Dict[str, Any]:
    """Validate the gateway's own configuration.

    Called at startup and re-evaluated on each /health request (cheap: only env
    reads). Results are reported on the **unauthenticated** /health endpoint by
    design — if the bearer token is the thing that is broken, a monitoring system
    cannot authenticate to find out.

    Returns:
        ``{"valid": bool, "errors": [...], "warnings": [...]}``
    """
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    secure_mode = os.getenv("FMCP_SECURE_MODE", "").lower() == "true"
    token = os.getenv("FMCP_BEARER_TOKEN")

    # The redeploy failure mode: secure mode on, token missing. auth.py then
    # returns 500 on every /api request with nothing explaining why.
    if secure_mode and not token:
        errors.append({
            "key": "FMCP_BEARER_TOKEN",
            "problem": "not set while FMCP_SECURE_MODE=true",
            "impact": "all /api requests will return HTTP 500",
        })

    if secure_mode and token and len(token) < 16:
        warnings.append({
            "key": "FMCP_BEARER_TOKEN",
            "problem": f"only {len(token)} characters",
            "impact": "weak token — generate with `openssl rand -hex 32`",
        })

    mongodb_uri = os.getenv("MONGODB_URI") or os.getenv("FMCP_MONGODB_URI")
    if not mongodb_uri:
        warnings.append({
            "key": "MONGODB_URI",
            "problem": "not set",
            "impact": "running in-memory — crash history, events and uptime "
                      "history are lost on restart",
        })
    elif not db_connected:
        errors.append({
            "key": "MONGODB_URI",
            "problem": "set but the database is unreachable",
            "impact": "crash history and monitoring events are not being persisted",
        })

    for numeric_var in (
        "FMCP_HEALTH_CHECK_INTERVAL",
        "FMCP_EVENT_RETENTION_DAYS",
        "FMCP_DEGRADED_MIN_SAMPLES",
    ):
        raw = os.getenv(numeric_var)
        if raw is not None:
            try:
                if int(raw) <= 0:
                    warnings.append({
                        "key": numeric_var,
                        "problem": f"non-positive value {raw!r}",
                        "impact": "falling back to the built-in default",
                    })
            except ValueError:
                warnings.append({
                    "key": numeric_var,
                    "problem": f"not an integer: {raw!r}",
                    "impact": "falling back to the built-in default",
                })

    rate = os.getenv("FMCP_DEGRADED_ERROR_RATE")
    if rate is not None:
        try:
            value = float(rate)
            if not 0.0 < value <= 1.0:
                warnings.append({
                    "key": "FMCP_DEGRADED_ERROR_RATE",
                    "problem": f"{value} is outside (0, 1]",
                    "impact": "degradation detection may never trigger",
                })
        except ValueError:
            warnings.append({
                "key": "FMCP_DEGRADED_ERROR_RATE",
                "problem": f"not a number: {rate!r}",
                "impact": "falling back to the built-in default",
            })

    global _CONFIG_ERRORS, _CONFIG_WARNINGS
    _CONFIG_ERRORS = errors
    _CONFIG_WARNINGS = warnings

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def config_status() -> Dict[str, Any]:
    """Last computed configuration validity."""
    return {
        "valid": not _CONFIG_ERRORS,
        "errors": _CONFIG_ERRORS,
        "warnings": _CONFIG_WARNINGS,
    }


# ==================== Self resources ====================

def self_resources() -> Dict[str, Any]:
    """FluidMCP's own resource usage.

    These values exist in the Prometheus registry already; this surfaces them in
    the JSON rollup so a monitoring system does not have to scrape and parse
    Prometheus text to answer "is the gateway itself healthy".
    """
    resources: Dict[str, Any] = {
        "memory_rss_bytes": None,
        "memory_rss_human": None,
        "cpu_percent": None,
        "open_fds": None,
        "threads": None,
        "event_loop_lag_ms": event_loop_lag_ms(),
    }

    if not _PSUTIL:
        return resources

    try:
        proc = psutil.Process(os.getpid())
        rss = proc.memory_info().rss
        resources["memory_rss_bytes"] = rss
        resources["memory_rss_human"] = f"{rss / (1024 * 1024):.1f} MB"
        # interval=None returns usage since the previous call — non-blocking.
        resources["cpu_percent"] = proc.cpu_percent(interval=None)
        resources["threads"] = proc.num_threads()
        if hasattr(proc, "num_fds"):
            resources["open_fds"] = proc.num_fds()
    except Exception as e:
        logger.debug(f"Failed to read gateway self-resources: {e}")

    return resources


def identity() -> Dict[str, Any]:
    """Boot identity block included in every monitoring payload."""
    return {
        "gateway_id": gateway_id(),
        "boot_id": BOOT_ID,
        "boot_count": boot_count(),
        "started_at": STARTED_AT.isoformat().replace("+00:00", "Z"),
        "uptime_seconds": round(uptime_seconds(), 1),
    }


async def record_boot(db: Any) -> None:
    """Persist a boot record and read back the cumulative boot count.

    Called as early as possible after the DB connects — before any fail-fast
    exit — so that a crash-looping gateway leaves a trail explaining the gap
    once the database is reachable again.
    """
    try:
        count = await db.save_boot_record({
            "gateway_id": gateway_id(),
            "boot_id": BOOT_ID,
            "started_at": STARTED_AT,
            "config_errors": _CONFIG_ERRORS,
            "config_warnings": _CONFIG_WARNINGS,
            "version": os.getenv("FMCP_VERSION", "unknown"),
        })
        if isinstance(count, int) and count > 0:
            set_boot_count(count)
            logger.info(f"Gateway boot recorded: boot_id={BOOT_ID} boot_count={count}")
    except Exception as e:
        # Never let boot bookkeeping prevent startup.
        logger.warning(f"Could not persist boot record: {e}")
