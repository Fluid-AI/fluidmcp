"""
Observability MCP Server for FluidMCP.

Exposes 8 tools that give an AI agent full read access to the observability
stack (Prometheus metrics, Loki logs, Tempo traces) running alongside FluidMCP.

Tools:
  query_metrics       — PromQL range query → metrics time series
  query_logs          — LogQL query → structured log lines
  search_traces       — Tempo search → list of matching traces
  get_trace           — Tempo trace-by-ID → full span tree
  get_active_alerts   — Prometheus alerts API → firing / pending alerts
  get_service_health  — FluidMCP /health + Prometheus server status
  get_error_summary   — composite: error rate + top servers + recent logs + alerts
  correlate           — composite: full trace detail + all logs that share the trace_id

Run standalone:
  python -m fluidmcp.observability.mcp_server.server

Environment variables:
  PROMETHEUS_URL   (default: http://prometheus:9090)
  LOKI_URL         (default: http://loki:3100)
  TEMPO_URL        (default: http://tempo:3200)
  FLUIDMCP_URL     (default: http://fluidmcp:8099)
"""
import asyncio
import os
import re
from typing import Any, Dict, List, Optional

# LogQL stream selectors that must appear in every query to scope it to FluidMCP.
# This prevents MCP callers from reading logs from unrelated services.
_REQUIRED_LOGQL_SELECTORS = ('service="fluidmcp"', "service='fluidmcp'", 'container="fluidmcp"', "container='fluidmcp'")


def _assert_logql_scoped(logql: str) -> Optional[str]:
    """Return an error string if logql does not scope to the fluidmcp service, else None."""
    if not any(sel in logql for sel in _REQUIRED_LOGQL_SELECTORS):
        return (
            'LogQL query must include a FluidMCP scope selector, e.g. {service="fluidmcp"} '
            "or {container=\"fluidmcp\"}. Queries that read from other services are not permitted."
        )
    return None

import httpx
from mcp.server.fastmcp import FastMCP

from .backends import prometheus as prom_client
from .backends import loki as loki_client
from .backends import tempo as tempo_client
from .models import (
    AlertsResult,
    CorrelationResult,
    ErrorSummary,
    LogsResult,
    MetricsResult,
    ServiceHealthResult,
    ServerStatus,
    TraceDetail,
    TraceSearchResults,
)

FLUIDMCP_URL = os.getenv("FLUIDMCP_URL", "http://fluidmcp:8099")

mcp = FastMCP(
    name="observability",
    instructions=(
        "You have access to the full observability stack for a running FluidMCP instance. "
        "Use query_metrics for numerical time-series data (request rates, latency, error rates, GPU memory). "
        "Use query_logs to search log lines by content, level, or time window. "
        "Use search_traces / get_trace to inspect distributed traces and slow requests. "
        "Use get_error_summary for a quick combined view of what is going wrong. "
        "Use correlate(trace_id) to see the logs that belong to a specific request. "
        "All time parameters accept 'now-15m', 'now-1h', ISO-8601 strings, or Unix timestamps."
    ),
)


# ── Tool 1: query_metrics ─────────────────────────────────────────────────────

@mcp.tool()
async def query_metrics(
    promql: str,
    start: str = "now-15m",
    end: str = "now",
    step: str = "60s",
) -> Dict[str, Any]:
    """
    Run a PromQL range query against Prometheus and return time-series data.

    Use this tool to answer questions like:
    - "What is the request rate for the filesystem server over the last hour?"
    - "Show me CPU usage for the past 30 minutes."
    - "What was the p95 latency in the last 15 minutes?"

    Common FluidMCP metrics:
      fluidmcp_requests_total{server_id="..."}
      fluidmcp_errors_total{server_id="..."}
      fluidmcp_request_duration_seconds_bucket{server_id="..."}
      fluidmcp_server_status{server_id="..."}   (0=stopped, 2=running, 3=error)
      fluidmcp_system_cpu_percent
      fluidmcp_process_memory_bytes
      fluidmcp_gpu_memory_utilization_ratio{server_id="..."}

    Args:
        promql: PromQL expression, e.g. 'rate(fluidmcp_requests_total[5m])'
        start:  Start of time range (default: 15 minutes ago)
        end:    End of time range (default: now)
        step:   Resolution step (default: 60s)

    Returns:
        MetricsResult with result_type and a list of labeled time series.
    """
    result = await prom_client.query_range(promql=promql, start=start, end=end, step=step)
    return result.model_dump()


# ── Tool 2: query_logs ────────────────────────────────────────────────────────

@mcp.tool()
async def query_logs(
    logql: str = '{service="fluidmcp"}',
    start: str = "now-15m",
    end: str = "now",
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Query Loki for log lines using a LogQL expression.

    Use this tool to answer questions like:
    - "Show me the last 30 error logs."
    - "Find any logs mentioning 'timeout' in the last hour."
    - "What did the filesystem server log in the last 5 minutes?"

    LogQL cheat-sheet:
      All logs:             {service="fluidmcp"}
      Errors only:          {service="fluidmcp", level="error"}
      Text search:          {service="fluidmcp"} |= "timeout"
      Regex filter:         {service="fluidmcp"} |~ "error|exception"
      By container:         {container="fluidmcp"}

    Args:
        logql:  LogQL stream selector + optional filter pipeline
        start:  Start time (default: 15 minutes ago)
        end:    End time (default: now)
        limit:  Max log lines to return (default: 50, max: 500)

    Returns:
        LogsResult with a list of LogLine objects (timestamp, message, labels,
        trace_id, span_id when available).
    """
    err = _assert_logql_scoped(logql)
    if err:
        return LogsResult(query=logql, lines=[], total=0, error=err).model_dump()
    limit = min(limit, 500)
    result = await loki_client.query_logs(logql=logql, start=start, end=end, limit=limit)
    return result.model_dump()


# ── Tool 3: search_traces ─────────────────────────────────────────────────────

@mcp.tool()
async def search_traces(
    service: str = "fluidmcp",
    operation: Optional[str] = None,
    min_duration_ms: Optional[float] = None,
    max_duration_ms: Optional[float] = None,
    tags: Optional[Dict[str, str]] = None,
    start: str = "now-1h",
    end: str = "now",
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search Grafana Tempo for distributed traces matching the given criteria.

    Use this tool to answer questions like:
    - "Find the slowest requests in the last hour."
    - "Show me any failed traces for the filesystem server."
    - "Find traces for the tools/call operation that took more than 2 seconds."

    Args:
        service:          Service name to filter by (default: fluidmcp)
        operation:        Root span operation name, e.g. 'POST /filesystem/mcp'
        min_duration_ms:  Only return traces longer than this (milliseconds)
        max_duration_ms:  Only return traces shorter than this (milliseconds)
        tags:             Additional span tags to filter, e.g. {"http.status_code": "500"}
        start:            Start time (default: 1 hour ago)
        end:              End time (default: now)
        limit:            Max traces to return (default: 20)

    Returns:
        TraceSearchResults with trace_id, duration_ms, span_count, error flag.
    """
    result = await tempo_client.search_traces(
        service=service,
        operation=operation,
        tags=tags,
        min_duration_ms=min_duration_ms,
        max_duration_ms=max_duration_ms,
        start=start,
        end=end,
        limit=limit,
    )
    return result.model_dump()


# ── Tool 4: get_trace ─────────────────────────────────────────────────────────

@mcp.tool()
async def get_trace(trace_id: str) -> Dict[str, Any]:
    """
    Fetch the full span tree for a specific trace by its trace ID.

    Use this tool when you have a trace_id (from search_traces, query_logs,
    or an error log) and want to understand exactly what happened during
    that request — which services were called, in what order, and where time was spent.

    The returned spans include:
    - operation_name: what the span represents (e.g. 'POST /filesystem/mcp')
    - duration_ms: how long this span took
    - status: 'ok', 'error', or 'unset'
    - parent_span_id: use this to reconstruct the call tree
    - attributes: HTTP method, status code, MCP operation, etc.

    Args:
        trace_id: 32-character hex trace ID

    Returns:
        TraceDetail with full span list, total duration, and error count.
    """
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
        return TraceDetail(
            trace_id=trace_id,
            duration_ms=0,
            span_count=0,
            error_count=0,
            spans=[],
            error="Invalid trace_id: must be exactly 32 lowercase hex characters",
        ).model_dump()
    result = await tempo_client.get_trace(trace_id=trace_id)
    return result.model_dump()


# ── Tool 5: get_active_alerts ─────────────────────────────────────────────────

@mcp.tool()
async def get_active_alerts() -> Dict[str, Any]:
    """
    Get all currently firing or pending Prometheus alerts.

    Use this tool to answer questions like:
    - "Are there any active alerts right now?"
    - "Is there a high error rate alert firing?"
    - "What is the current severity of issues?"

    Alert severities: critical, warning, info.
    Alert states: firing (active), pending (condition met but not yet for required duration).

    Returns:
        AlertsResult with separate lists for firing and pending alerts,
        each including name, severity, summary, description, and labels.
    """
    result = await prom_client.get_alerts()
    return result.model_dump()


# ── Tool 6: get_service_health ────────────────────────────────────────────────

@mcp.tool()
async def get_service_health() -> Dict[str, Any]:
    """
    Get the current health status of FluidMCP and all registered MCP servers.

    Combines:
    - FluidMCP /health endpoint (gateway status, database connection)
    - Prometheus metrics for per-server status, request rate, and error rate

    Use this tool first when triaging an issue to understand which components
    are affected before diving into logs or traces.

    Returns:
        ServiceHealthResult with gateway_status, database status, and a list
        of ServerStatus objects (status, uptime, request_rate, error_rate).
    """
    gateway_status = "unknown"
    db_status = "unknown"
    servers: List[ServerStatus] = []

    # 1. FluidMCP /health
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{FLUIDMCP_URL}/health")
            resp.raise_for_status()
            health = resp.json()
        gateway_status = health.get("status", "unknown")
        db_raw = health.get("database", {})
        # /health may return database as a plain string or as {"status": "..."} object
        if isinstance(db_raw, str):
            db_status = db_raw
        else:
            db_status = db_raw.get("status", "unknown")
    except Exception as exc:
        gateway_status = f"unreachable ({exc})"

    # 2. Per-server status from Prometheus (fluidmcp_server_status gauge)
    status_result = await prom_client.query_instant(
        "fluidmcp_server_status"
    )
    status_map: Dict[str, str] = {}
    STATUS_NAMES = {0: "stopped", 1: "starting", 2: "running", 3: "error", 4: "restarting"}
    for series in status_result.series:
        server_id = series.metric.get("server_id", "unknown")
        try:
            code = int(float(series.values[0].value))
        except (IndexError, ValueError):
            code = -1
        status_map[server_id] = STATUS_NAMES.get(code, "unknown")

    # 3. Per-server request rate and error rate
    req_result = await prom_client.query_instant(
        "sum by(server_id) (rate(fluidmcp_requests_total[5m]))"
    )
    req_map: Dict[str, float] = {}
    for series in req_result.series:
        sid = series.metric.get("server_id", "unknown")
        try:
            req_map[sid] = round(float(series.values[0].value), 4)
        except (IndexError, ValueError):
            req_map[sid] = 0.0

    err_result = await prom_client.query_instant(
        "sum by(server_id) (rate(fluidmcp_errors_total[5m]))"
    )
    err_map: Dict[str, float] = {}
    for series in err_result.series:
        sid = series.metric.get("server_id", "unknown")
        try:
            err_map[sid] = round(float(series.values[0].value), 6)
        except (IndexError, ValueError):
            err_map[sid] = 0.0

    for server_id, status in status_map.items():
        servers.append(ServerStatus(
            server_id=server_id,
            status=status,
            request_rate=req_map.get(server_id),
            error_rate=err_map.get(server_id),
        ))

    result = ServiceHealthResult(
        gateway_status=gateway_status,
        database=db_status,
        servers=servers,
    )
    return result.model_dump()


# ── Tool 7: get_error_summary ─────────────────────────────────────────────────

@mcp.tool()
async def get_error_summary(window: str = "15m") -> Dict[str, Any]:
    """
    Get a combined error picture across metrics, logs, and alerts.

    This composite tool runs three parallel queries:
    1. Prometheus: overall error rate + error counts by server
    2. Loki: most recent ERROR-level log lines
    3. Prometheus: currently firing alerts

    Use this as your first tool when asked "what's wrong?" or
    "summarise the health of the system".

    Args:
        window: Time window to analyse (default: '15m', e.g. '30m', '1h', '6h')

    Returns:
        ErrorSummary with:
          - total_errors: raw error count over the window
          - error_rate: errors per second (averaged over window)
          - top_servers: servers ranked by error count
          - recent_error_logs: last 20 ERROR log lines
          - active_alerts: currently firing Prometheus alerts
    """
    # Run all three queries concurrently
    error_rate_task = asyncio.create_task(prom_client.get_error_rate(window=window))
    top_servers_task = asyncio.create_task(prom_client.get_error_counts_by_server(window=window))
    error_logs_task = asyncio.create_task(loki_client.get_error_logs(window=window, limit=20))
    alerts_task = asyncio.create_task(prom_client.get_alerts())
    total_errors_task = asyncio.create_task(
        prom_client.query_instant(f"sum(increase(fluidmcp_errors_total[{window}]))")
    )

    (
        error_rate,
        top_servers,
        error_logs_result,
        alerts_result,
        total_errors_result,
    ) = await asyncio.gather(
        error_rate_task,
        top_servers_task,
        error_logs_task,
        alerts_task,
        total_errors_task,
    )

    total_errors = 0
    if total_errors_result.series:
        try:
            total_errors = int(float(total_errors_result.series[0].values[0].value))
        except (IndexError, ValueError):
            pass

    result = ErrorSummary(
        window=window,
        total_errors=total_errors,
        error_rate=error_rate,
        top_servers=top_servers,
        recent_error_logs=error_logs_result.lines,
        active_alerts=alerts_result.firing,
    )
    return result.model_dump()


# ── Tool 8: correlate ─────────────────────────────────────────────────────────

@mcp.tool()
async def correlate(trace_id: str, log_window: str = "1h") -> Dict[str, Any]:
    """
    Given a trace ID, fetch the full trace span tree AND all log lines
    that were emitted during that request.

    This composite tool joins two signals:
    1. Tempo: full span tree for the trace (which services were called, timing, errors)
    2. Loki: all log lines whose trace_id field matches (the exact log messages
       that were written while handling that request)

    Use this to deeply understand a specific failed or slow request.
    For example: "I see trace abc123 was slow — what happened?"

    Args:
        trace_id:   32-char hex trace ID (from search_traces, query_logs, or an error)
        log_window: How far back to search Loki for logs (default: '1h')

    Returns:
        CorrelationResult with:
          - trace: full TraceDetail (spans, duration, errors)
          - logs: log lines matching the trace_id
          - log_count: total matching log lines
    """
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
        return CorrelationResult(
            trace_id=trace_id,
            trace=None,
            logs=[],
            log_count=0,
            error="Invalid trace_id: must be exactly 32 lowercase hex characters",
        ).model_dump()

    # Fetch trace and logs in parallel
    trace_task = asyncio.create_task(tempo_client.get_trace(trace_id=trace_id))
    logs_task = asyncio.create_task(
        loki_client.get_logs_for_trace(trace_id=trace_id, window=log_window)
    )

    trace_result, logs_result = await asyncio.gather(trace_task, logs_task)

    result = CorrelationResult(
        trace_id=trace_id,
        trace=trace_result if not trace_result.error else None,
        logs=logs_result.lines,
        log_count=logs_result.total,
        error=trace_result.error or logs_result.error,
    )
    return result.model_dump()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
