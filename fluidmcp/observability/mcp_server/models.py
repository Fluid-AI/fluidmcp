"""
Pydantic response models for the Observability MCP server.

All tool return values are typed here so the AI always receives
consistent, well-named fields regardless of the backend wire format.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


# ── Shared primitives ─────────────────────────────────────────────────────────

class MetricSample(BaseModel):
    timestamp: float
    value: str


class MetricSeries(BaseModel):
    metric: Dict[str, str]        # label set, e.g. {"server_id": "filesystem", ...}
    values: List[MetricSample]


class MetricsResult(BaseModel):
    query: str
    result_type: str              # "matrix" | "vector" | "scalar"
    series: List[MetricSeries]
    error: Optional[str] = None


# ── Logs ──────────────────────────────────────────────────────────────────────

class LogLine(BaseModel):
    timestamp: str                # RFC3339 nanosecond string from Loki
    message: str
    labels: Dict[str, str]        # stream labels, e.g. {"level": "error", ...}
    trace_id: Optional[str] = None
    span_id: Optional[str] = None


class LogsResult(BaseModel):
    query: str
    lines: List[LogLine]
    total: int
    error: Optional[str] = None


# ── Traces ────────────────────────────────────────────────────────────────────

class TraceSearchResult(BaseModel):
    trace_id: str
    root_service: str
    root_name: str                # root span operation name
    duration_ms: float
    start_time: str               # ISO8601
    span_count: int
    error: bool


class TraceSearchResults(BaseModel):
    results: List[TraceSearchResult]
    total: int
    error: Optional[str] = None


class SpanAttribute(BaseModel):
    key: str
    value: Any


class Span(BaseModel):
    span_id: str
    parent_span_id: Optional[str] = None
    operation_name: str
    service: str
    start_time: str
    duration_ms: float
    status: str                   # "ok" | "error" | "unset"
    attributes: List[SpanAttribute]
    error_message: Optional[str] = None


class TraceDetail(BaseModel):
    trace_id: str
    duration_ms: float
    span_count: int
    error_count: int
    spans: List[Span]
    error: Optional[str] = None


# ── Alerts ────────────────────────────────────────────────────────────────────

class Alert(BaseModel):
    name: str
    state: str                    # "firing" | "pending" | "inactive"
    severity: str
    summary: str
    description: str
    labels: Dict[str, str]
    fired_at: Optional[str] = None


class AlertsResult(BaseModel):
    firing: List[Alert]
    pending: List[Alert]
    total_firing: int
    error: Optional[str] = None


# ── Service health ────────────────────────────────────────────────────────────

class ServerStatus(BaseModel):
    server_id: str
    status: str                   # "running" | "stopped" | "error"
    uptime_seconds: Optional[float] = None
    request_rate: Optional[float] = None
    error_rate: Optional[float] = None


class ServiceHealthResult(BaseModel):
    gateway_status: str           # "healthy" | "degraded" | "starting"
    database: str
    servers: List[ServerStatus]
    error: Optional[str] = None


# ── Composite: error summary ──────────────────────────────────────────────────

class ErrorSummary(BaseModel):
    window: str
    total_errors: int
    error_rate: Optional[float] = None   # errors/sec averaged over window
    top_servers: List[Dict[str, Any]]    # [{server_id, errors, rate}]
    recent_error_logs: List[LogLine]
    active_alerts: List[Alert]
    error: Optional[str] = None


# ── Composite: trace+log correlation ─────────────────────────────────────────

class CorrelationResult(BaseModel):
    trace_id: str
    trace: Optional[TraceDetail] = None
    logs: List[LogLine]
    log_count: int
    error: Optional[str] = None
