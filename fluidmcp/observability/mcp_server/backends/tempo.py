"""
Async Grafana Tempo HTTP client.

Wraps the Tempo HTTP API v2 (search + trace-by-ID) and returns
typed TraceSearchResults / TraceDetail models.
"""
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from ..models import Span, SpanAttribute, TraceDetail, TraceSearchResult, TraceSearchResults


TEMPO_URL = os.getenv("TEMPO_URL", "http://tempo:3200")
_DEFAULT_TIMEOUT = 30.0


def _ns_to_iso(ns: int) -> str:
    dt = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
    return dt.isoformat()


def _parse_duration_ms(duration_str: str) -> float:
    """Convert Tempo duration strings like '1.234s', '567ms', '890µs' to milliseconds."""
    if not duration_str:
        return 0.0
    duration_str = duration_str.strip()
    try:
        if duration_str.endswith("ms"):
            return float(duration_str[:-2])
        # µs is a two-byte UTF-8 sequence; check it before the plain "us" fallback
        if duration_str.endswith("µs"):
            return float(duration_str[: -len("µs")]) / 1000
        if duration_str.endswith("us"):
            return float(duration_str[:-2]) / 1000
        if duration_str.endswith("s"):
            return float(duration_str[:-1]) * 1000
        return float(duration_str)
    except ValueError:
        return 0.0


def _parse_time_to_unix(t: Optional[str], default_offset_seconds: int = 0) -> int:
    if t is None:
        return int(time.time()) + default_offset_seconds
    t = t.strip()
    if t.startswith("now"):
        rest = t[3:].strip()
        if not rest:
            return int(time.time())
        sign = -1 if rest[0] == "-" else 1
        rest = rest[1:]
        unit = rest[-1]
        amount = float(rest[:-1])
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return int(time.time() + sign * amount * multipliers.get(unit, 60))
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except ValueError:
        return int(time.time())


async def search_traces(
    service: Optional[str] = None,
    operation: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    min_duration_ms: Optional[float] = None,
    max_duration_ms: Optional[float] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 20,
) -> TraceSearchResults:
    """
    Search Tempo for traces matching the given criteria.

    All parameters are optional — omitting them returns the most recent traces.
    """
    start_ts = _parse_time_to_unix(start, default_offset_seconds=-3600)
    end_ts = _parse_time_to_unix(end)

    params: Dict[str, Any] = {
        "start": start_ts,
        "end": end_ts,
        "limit": limit,
    }
    if service:
        params["service.name"] = service
    if operation:
        params["name"] = operation
    if min_duration_ms is not None:
        params["minDuration"] = f"{int(min_duration_ms)}ms"
    if max_duration_ms is not None:
        params["maxDuration"] = f"{int(max_duration_ms)}ms"
    # Extra tags as key=value pairs
    if tags:
        for k, v in tags.items():
            params[k] = v

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{TEMPO_URL}/api/search", params=params)
            resp.raise_for_status()
            body = resp.json()

        results = []
        for raw in body.get("traces", []):
            # rootTraceName may be missing for in-progress traces
            root_service = raw.get("rootServiceName", "unknown")
            root_name = raw.get("rootTraceName", "unknown")
            start_time_unix_ms = raw.get("startTimeUnixNano", 0)
            start_iso = _ns_to_iso(int(start_time_unix_ms)) if start_time_unix_ms else ""
            duration_ms = _parse_duration_ms(raw.get("durationMs", "0"))

            results.append(TraceSearchResult(
                trace_id=raw.get("traceID", ""),
                root_service=root_service,
                root_name=root_name,
                duration_ms=duration_ms,
                start_time=start_iso,
                span_count=raw.get("spanCount", 0),
                error=raw.get("rootSpanStatus", "").lower() == "error",
            ))

        return TraceSearchResults(results=results, total=len(results))

    except httpx.HTTPStatusError as exc:
        return TraceSearchResults(results=[], total=0, error=f"HTTP {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        return TraceSearchResults(results=[], total=0, error=str(exc))


async def get_trace(trace_id: str) -> TraceDetail:
    """
    Fetch the full span tree for a single trace by its trace ID.
    Returns a flat list of Span objects (AI can traverse parent_span_id to build the tree).
    """
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{TEMPO_URL}/api/traces/{trace_id}")
            resp.raise_for_status()
            body = resp.json()

        spans: List[Span] = []
        error_count = 0
        min_start_ns = None
        max_end_ns = None

        for batch in body.get("batches", []):
            resource = batch.get("resource", {})
            service_name = "unknown"
            for attr in resource.get("attributes", []):
                if attr.get("key") == "service.name":
                    service_name = attr.get("value", {}).get("stringValue", "unknown")
                    break

            for scope_span in batch.get("scopeSpans", []):
                for raw_span in scope_span.get("spans", []):
                    start_ns = int(raw_span.get("startTimeUnixNano", 0))
                    end_ns = int(raw_span.get("endTimeUnixNano", 0))
                    duration_ms = (end_ns - start_ns) / 1e6

                    if min_start_ns is None or start_ns < min_start_ns:
                        min_start_ns = start_ns
                    if max_end_ns is None or end_ns > max_end_ns:
                        max_end_ns = end_ns

                    # Decode status
                    status_raw = raw_span.get("status", {})
                    status_code = status_raw.get("code", 0)
                    status = "error" if status_code == 2 else ("ok" if status_code == 1 else "unset")
                    if status == "error":
                        error_count += 1

                    error_message = status_raw.get("message") if status == "error" else None

                    # Decode attributes
                    attributes = []
                    for attr in raw_span.get("attributes", []):
                        val = attr.get("value", {})
                        decoded = (
                            val.get("stringValue")
                            or val.get("intValue")
                            or val.get("doubleValue")
                            or val.get("boolValue")
                        )
                        attributes.append(SpanAttribute(key=attr.get("key", ""), value=decoded))

                    # Parent span ID — empty bytes means root span
                    parent_id = raw_span.get("parentSpanId", "")
                    if isinstance(parent_id, bytes):
                        parent_id = parent_id.hex() if parent_id else None
                    parent_id = parent_id if parent_id else None

                    spans.append(Span(
                        span_id=raw_span.get("spanId", ""),
                        parent_span_id=parent_id,
                        operation_name=raw_span.get("name", ""),
                        service=service_name,
                        start_time=_ns_to_iso(start_ns),
                        duration_ms=round(duration_ms, 3),
                        status=status,
                        attributes=attributes,
                        error_message=error_message,
                    ))

        total_duration_ms = 0.0
        if min_start_ns and max_end_ns:
            total_duration_ms = round((max_end_ns - min_start_ns) / 1e6, 3)

        return TraceDetail(
            trace_id=trace_id,
            duration_ms=total_duration_ms,
            span_count=len(spans),
            error_count=error_count,
            spans=spans,
        )

    except httpx.HTTPStatusError as exc:
        return TraceDetail(trace_id=trace_id, duration_ms=0, span_count=0, error_count=0, spans=[], error=f"HTTP {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        return TraceDetail(trace_id=trace_id, duration_ms=0, span_count=0, error_count=0, spans=[], error=str(exc))
