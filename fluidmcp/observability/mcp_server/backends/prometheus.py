"""
Async Prometheus HTTP client.

Wraps the Prometheus HTTP API v1 and returns typed models.
All time parameters accept either a Unix timestamp (float) or an
ISO-8601 string; helpers convert to the Unix seconds Prometheus expects.
"""
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx

from ..models import Alert, AlertsResult, MetricSample, MetricSeries, MetricsResult


PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
_DEFAULT_TIMEOUT = 30.0


def _parse_time(t: Optional[str], default_offset_seconds: int = 0) -> float:
    """Convert an ISO-8601 string or 'now-Xm' shorthand to a Unix timestamp."""
    if t is None:
        return time.time() + default_offset_seconds
    if isinstance(t, (int, float)):
        return float(t)
    t = t.strip()
    # Shorthand: "now-15m", "now-1h", "now-30s"
    if t.startswith("now"):
        rest = t[3:].strip()
        if not rest:
            return time.time()
        sign = -1 if rest[0] == "-" else 1
        rest = rest[1:]
        unit = rest[-1]
        amount = float(rest[:-1])
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return time.time() + sign * amount * multipliers.get(unit, 60)
    # ISO-8601
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        return time.time()


def _window_to_seconds(window: str) -> int:
    """Convert a shorthand like '30m', '1h', '2d' to seconds."""
    unit = window[-1]
    amount = int(window[:-1])
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return amount * multipliers.get(unit, 60)


def _build_series(raw: List[Dict[str, Any]]) -> List[MetricSeries]:
    series = []
    for item in raw:
        samples = [MetricSample(timestamp=v[0], value=v[1]) for v in item.get("values", [])]
        # instant vector → single-element list
        if not samples and "value" in item:
            v = item["value"]
            samples = [MetricSample(timestamp=v[0], value=v[1])]
        series.append(MetricSeries(metric=item.get("metric", {}), values=samples))
    return series


async def query_range(
    promql: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    step: str = "60s",
) -> MetricsResult:
    """Execute a PromQL range query and return typed MetricsResult."""
    start_ts = _parse_time(start, default_offset_seconds=-900)   # default: 15 min ago
    end_ts = _parse_time(end)

    params = {
        "query": promql,
        "start": start_ts,
        "end": end_ts,
        "step": step,
    }

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params)
            resp.raise_for_status()
            body = resp.json()

        if body.get("status") != "success":
            return MetricsResult(query=promql, result_type="error", series=[], error=body.get("error"))

        data = body.get("data", {})
        return MetricsResult(
            query=promql,
            result_type=data.get("resultType", "matrix"),
            series=_build_series(data.get("result", [])),
        )
    except httpx.HTTPStatusError as exc:
        return MetricsResult(query=promql, result_type="error", series=[], error=str(exc))
    except Exception as exc:
        return MetricsResult(query=promql, result_type="error", series=[], error=str(exc))


async def query_instant(promql: str, at: Optional[str] = None) -> MetricsResult:
    """Execute a PromQL instant query."""
    params: Dict[str, Any] = {"query": promql}
    if at:
        params["time"] = _parse_time(at)

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params=params)
            resp.raise_for_status()
            body = resp.json()

        if body.get("status") != "success":
            return MetricsResult(query=promql, result_type="error", series=[], error=body.get("error"))

        data = body.get("data", {})
        return MetricsResult(
            query=promql,
            result_type=data.get("resultType", "vector"),
            series=_build_series(data.get("result", [])),
        )
    except Exception as exc:
        return MetricsResult(query=promql, result_type="error", series=[], error=str(exc))


async def get_alerts() -> AlertsResult:
    """Fetch all Prometheus alerts with current state."""
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{PROMETHEUS_URL}/api/v1/alerts")
            resp.raise_for_status()
            body = resp.json()

        firing: List[Alert] = []
        pending: List[Alert] = []

        for raw in body.get("data", {}).get("alerts", []):
            labels = raw.get("labels", {})
            annotations = raw.get("annotations", {})
            alert = Alert(
                name=labels.get("alertname", "unknown"),
                state=raw.get("state", "unknown"),
                severity=labels.get("severity", "unknown"),
                summary=annotations.get("summary", ""),
                description=annotations.get("description", ""),
                labels=labels,
                fired_at=raw.get("activeAt"),
            )
            if alert.state == "firing":
                firing.append(alert)
            elif alert.state == "pending":
                pending.append(alert)

        return AlertsResult(firing=firing, pending=pending, total_firing=len(firing))
    except Exception as exc:
        return AlertsResult(firing=[], pending=[], total_firing=0, error=str(exc))


async def get_error_rate(window: str = "15m") -> Optional[float]:
    """Return the average error rate (errors/sec) over the given window. None on failure."""
    promql = (
        f"sum(rate(fluidmcp_errors_total[{window}])) / "
        f"sum(rate(fluidmcp_requests_total[{window}]))"
    )
    result = await query_instant(promql)
    if result.error or not result.series:
        return None
    try:
        return float(result.series[0].values[0].value)
    except (IndexError, ValueError):
        return None


async def get_error_counts_by_server(window: str = "15m") -> List[Dict[str, Any]]:
    """Return error counts grouped by server_id over the given window."""
    promql = f"sum by(server_id) (rate(fluidmcp_errors_total[{window}]))"
    result = await query_instant(promql)
    out = []
    for series in result.series:
        try:
            rate_val = float(series.values[0].value) if series.values else 0.0
        except (IndexError, ValueError):
            rate_val = 0.0
        out.append({
            "server_id": series.metric.get("server_id", "unknown"),
            "error_rate": round(rate_val, 6),
        })
    return sorted(out, key=lambda x: x["error_rate"], reverse=True)
