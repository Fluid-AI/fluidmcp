"""
Async Loki HTTP client.

Wraps the Loki HTTP query API and returns typed LogsResult / LogLine models.
Handles both the query_range (time-series logs) and tail (recent lines) endpoints.
"""
import os
import time
from typing import Dict, List, Optional

import httpx

from ..models import LogLine, LogsResult


LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")
_DEFAULT_TIMEOUT = 30.0
_DEFAULT_LIMIT = 100


def _parse_loki_time(t: Optional[str], default_offset_ns: int = 0) -> str:
    """
    Convert time shorthand / ISO-8601 to a nanosecond Unix timestamp string,
    which is what Loki's HTTP API requires.
    """
    now_ns = int(time.time() * 1e9)

    if t is None:
        return str(now_ns + default_offset_ns)
    if isinstance(t, (int, float)):
        return str(int(t * 1e9))

    t = t.strip()
    if t.startswith("now"):
        rest = t[3:].strip()
        if not rest:
            return str(now_ns)
        sign = -1 if rest[0] == "-" else 1
        rest = rest[1:]
        unit = rest[-1]
        amount = float(rest[:-1])
        multipliers = {"s": 1e9, "m": 60e9, "h": 3600e9, "d": 86400e9}
        return str(int(now_ns + sign * amount * multipliers.get(unit, 60e9)))

    try:
        from datetime import datetime
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1e9))
    except ValueError:
        return str(now_ns)


def _parse_stream_labels(labels_raw: Dict) -> Dict[str, str]:
    return {k: str(v) for k, v in labels_raw.items()}


def _extract_log_lines(streams: List[Dict], labels_filter: Dict[str, str]) -> List[LogLine]:
    lines: List[LogLine] = []
    for stream in streams:
        labels = _parse_stream_labels(stream.get("stream", {}))
        # Apply caller-side label filter if provided
        if labels_filter and not all(labels.get(k) == v for k, v in labels_filter.items()):
            continue
        for entry in stream.get("values", []):
            ts_ns, message = entry[0], entry[1]
            # Convert nanosecond string to readable timestamp
            ts_sec = int(ts_ns) / 1e9
            from datetime import datetime, timezone
            ts_iso = datetime.fromtimestamp(ts_sec, tz=timezone.utc).isoformat()

            # If the message is itself JSON (FluidMCP structured logs), extract fields
            trace_id = span_id = None
            try:
                import json
                parsed = json.loads(message)
                trace_id = parsed.get("trace_id")
                span_id = parsed.get("span_id")
                # Use the human-readable "message" field if present
                message = parsed.get("message", message)
            except (ValueError, TypeError):
                pass

            lines.append(LogLine(
                timestamp=ts_iso,
                message=message,
                labels=labels,
                trace_id=trace_id,
                span_id=span_id,
            ))
    return lines


async def query_logs(
    logql: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = _DEFAULT_LIMIT,
    labels_filter: Optional[Dict[str, str]] = None,
) -> LogsResult:
    """
    Execute a LogQL query over a time range and return typed LogsResult.

    logql examples:
      '{service="fluidmcp"}'
      '{service="fluidmcp", level="error"}'
      '{service="fluidmcp"} |= "timeout"'
    """
    start_ns = _parse_loki_time(start, default_offset_ns=-int(15 * 60 * 1e9))
    end_ns = _parse_loki_time(end)

    params = {
        "query": logql,
        "start": start_ns,
        "end": end_ns,
        "limit": limit,
        "direction": "backward",   # most recent first
    }

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{LOKI_URL}/loki/api/v1/query_range", params=params)
            resp.raise_for_status()
            body = resp.json()

        streams = body.get("data", {}).get("result", [])
        lines = _extract_log_lines(streams, labels_filter or {})

        return LogsResult(query=logql, lines=lines, total=len(lines))

    except httpx.HTTPStatusError as exc:
        return LogsResult(query=logql, lines=[], total=0, error=f"HTTP {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        return LogsResult(query=logql, lines=[], total=0, error=str(exc))


async def get_error_logs(
    window: str = "15m",
    limit: int = 50,
    service: str = "fluidmcp",
) -> LogsResult:
    """Convenience wrapper: fetch ERROR-level logs for a service."""
    logql = f'{{service="{service}", level="error"}}'
    return await query_logs(
        logql=logql,
        start=f"now-{window}",
        limit=limit,
    )


async def get_logs_for_trace(trace_id: str, window: str = "1h") -> LogsResult:
    """
    Fetch all log lines that contain a specific trace_id.
    Uses Loki's line-filter expression for efficient index lookup.
    """
    logql = f'{{service="fluidmcp"}} |= "{trace_id}"'
    return await query_logs(
        logql=logql,
        start=f"now-{window}",
        limit=200,
    )
