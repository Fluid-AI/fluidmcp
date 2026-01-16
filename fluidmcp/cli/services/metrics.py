"""
Prometheus-compatible metrics collection for FluidMCP servers.

This module provides a centralized metrics collection system for monitoring
MCP server performance, health, and resource utilization.

Metrics exposed:
- Counters: request_total, error_total, restart_total
- Gauges: active_requests, gpu_memory_bytes, server_status
- Histograms: request_duration_seconds, tool_execution_seconds
"""

import time
from typing import Dict, Any, Optional, List
from collections import defaultdict
from threading import Lock

from loguru import logger


class Metric:
    """Base class for metrics."""

    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or []
        self.samples: Dict[tuple, float] = {}
        self._lock = Lock()

    def _get_label_key(self, label_values: Dict[str, str]) -> tuple:
        """Convert label dict to hashable key."""
        if not self.labels:
            return ()
        return tuple(label_values.get(label, "") for label in self.labels)

    def render(self) -> str:
        """Render metric in Prometheus exposition format."""
        raise NotImplementedError


class Counter(Metric):
    """Counter metric - monotonically increasing value."""

    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None):
        super().__init__(name, description, labels)

    def inc(self, label_values: Optional[Dict[str, str]] = None, amount: float = 1.0):
        """Increment counter."""
        if amount < 0:
            raise ValueError("Counter can only increase")

        label_values = label_values or {}
        key = self._get_label_key(label_values)

        with self._lock:
            self.samples[key] = self.samples.get(key, 0.0) + amount

    def render(self) -> str:
        """Render counter in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} counter"
        ]

        with self._lock:
            for key, value in sorted(self.samples.items()):
                if self.labels:
                    label_str = ",".join(f'{label}="{val}"' for label, val in zip(self.labels, key))
                    lines.append(f"{self.name}{{{label_str}}} {value}")
                else:
                    lines.append(f"{self.name} {value}")

        return "\n".join(lines)


class Gauge(Metric):
    """Gauge metric - value that can go up or down."""

    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None):
        super().__init__(name, description, labels)

    def set(self, value: float, label_values: Optional[Dict[str, str]] = None):
        """Set gauge to specific value."""
        label_values = label_values or {}
        key = self._get_label_key(label_values)

        with self._lock:
            self.samples[key] = value

    def inc(self, label_values: Optional[Dict[str, str]] = None, amount: float = 1.0):
        """Increment gauge."""
        label_values = label_values or {}
        key = self._get_label_key(label_values)

        with self._lock:
            self.samples[key] = self.samples.get(key, 0.0) + amount

    def dec(self, label_values: Optional[Dict[str, str]] = None, amount: float = 1.0):
        """Decrement gauge."""
        self.inc(label_values, -amount)

    def render(self) -> str:
        """Render gauge in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} gauge"
        ]

        with self._lock:
            for key, value in sorted(self.samples.items()):
                if self.labels:
                    label_str = ",".join(f'{label}="{val}"' for label, val in zip(self.labels, key))
                    lines.append(f"{self.name}{{{label_str}}} {value}")
                else:
                    lines.append(f"{self.name} {value}")

        return "\n".join(lines)


class Histogram(Metric):
    """Histogram metric - tracks distribution of values."""

    # Default buckets for request latency (in seconds)
    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None,
                 buckets: Optional[List[float]] = None):
        super().__init__(name, description, labels)
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)

        # Store: {label_key: {"sum": float, "count": int, buckets: {le: count}}}
        self.histograms: Dict[tuple, Dict[str, Any]] = defaultdict(lambda: {
            "sum": 0.0,
            "count": 0,
            "buckets": {bucket: 0 for bucket in self.buckets}
        })

    def observe(self, value: float, label_values: Optional[Dict[str, str]] = None):
        """Record an observation."""
        label_values = label_values or {}
        key = self._get_label_key(label_values)

        with self._lock:
            # Initialize histogram entry if it doesn't exist (thread-safe)
            if key not in self.histograms:
                self.histograms[key] = {
                    "sum": 0.0,
                    "count": 0,
                    "buckets": {bucket: 0 for bucket in self.buckets}
                }

            hist = self.histograms[key]
            hist["sum"] += value
            hist["count"] += 1

            # Update bucket counts: increment only the smallest matching bucket.
            # Cumulative counts are computed during render().
            # Note: Values exceeding all buckets are tracked in +Inf bucket via hist["count"]
            for bucket in self.buckets:
                if value <= bucket:
                    hist["buckets"][bucket] += 1
                    break

    def render(self) -> str:
        """Render histogram in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} histogram"
        ]

        with self._lock:
            for key, hist in sorted(self.histograms.items()):
                base_labels = ""
                if self.labels:
                    base_labels = ",".join(f'{label}="{val}"' for label, val in zip(self.labels, key))

                # Emit bucket counts
                cumulative = 0
                for bucket in self.buckets:
                    cumulative += hist["buckets"][bucket]
                    labels = f"{base_labels},le=\"{bucket}\"" if base_labels else f"le=\"{bucket}\""
                    lines.append(f"{self.name}_bucket{{{labels}}} {cumulative}")

                # Emit +Inf bucket
                labels = f"{base_labels},le=\"+Inf\"" if base_labels else "le=\"+Inf\""
                lines.append(f"{self.name}_bucket{{{labels}}} {hist['count']}")

                # Emit sum and count
                if base_labels:
                    lines.append(f"{self.name}_sum{{{base_labels}}} {hist['sum']}")
                    lines.append(f"{self.name}_count{{{base_labels}}} {hist['count']}")
                else:
                    lines.append(f"{self.name}_sum {hist['sum']}")
                    lines.append(f"{self.name}_count {hist['count']}")

        return "\n".join(lines)


class MetricsRegistry:
    """Central registry for all metrics."""

    def __init__(self):
        self.metrics: Dict[str, Metric] = {}
        self._lock = Lock()

        # Initialize standard metrics
        self._register_standard_metrics()

    def _register_standard_metrics(self):
        """Register standard FluidMCP metrics."""

        # Request metrics
        self.register(Counter(
            "fluidmcp_requests_total",
            "Total number of requests processed",
            labels=["server_id", "method", "status"]
        ))

        self.register(Counter(
            "fluidmcp_errors_total",
            "Total number of errors encountered",
            labels=["server_id", "error_type"]
        ))

        self.register(Gauge(
            "fluidmcp_active_requests",
            "Number of requests currently being processed",
            labels=["server_id"]
        ))

        self.register(Histogram(
            "fluidmcp_request_duration_seconds",
            "Request processing duration in seconds",
            labels=["server_id", "method"]
        ))

        # Server lifecycle metrics
        self.register(Gauge(
            "fluidmcp_server_status",
            "Server status (0=stopped, 1=starting, 2=running, 3=error, 4=restarting)",
            labels=["server_id"]
        ))

        self.register(Counter(
            "fluidmcp_server_restarts_total",
            "Total number of server restarts",
            labels=["server_id", "reason"]
        ))

        self.register(Gauge(
            "fluidmcp_server_uptime_seconds",
            "Server uptime in seconds since last start",
            labels=["server_id"]
        ))

        # Resource metrics
        self.register(Gauge(
            "fluidmcp_gpu_memory_bytes",
            "GPU memory usage in bytes",
            labels=["server_id", "gpu_index"]
        ))

        self.register(Gauge(
            "fluidmcp_gpu_memory_utilization_ratio",
            "GPU memory utilization ratio (0.0-1.0)",
            labels=["server_id"]
        ))

        # Tool execution metrics
        self.register(Counter(
            "fluidmcp_tool_calls_total",
            "Total number of tool calls executed",
            labels=["server_id", "tool_name", "status"]
        ))

        self.register(Histogram(
            "fluidmcp_tool_execution_seconds",
            "Tool execution duration in seconds",
            labels=["server_id", "tool_name"]
        ))

        # Streaming metrics
        self.register(Counter(
            "fluidmcp_streaming_requests_total",
            "Total number of streaming requests",
            labels=["server_id", "completion_status"]
        ))

        self.register(Gauge(
            "fluidmcp_active_streams",
            "Number of active streaming connections",
            labels=["server_id"]
        ))

    def register(self, metric: Metric):
        """Register a metric."""
        with self._lock:
            if metric.name in self.metrics:
                logger.warning(f"Metric {metric.name} already registered, replacing")
            self.metrics[metric.name] = metric

    def get_metric(self, name: str) -> Optional[Metric]:
        """Get a registered metric by name."""
        with self._lock:
            return self.metrics.get(name)

    def render_all(self) -> str:
        """Render all metrics in Prometheus exposition format."""
        lines = []

        with self._lock:
            for metric in sorted(self.metrics.values(), key=lambda m: m.name):
                lines.append(metric.render())
                lines.append("")  # Blank line between metrics

        return "\n".join(lines)


# Global registry instance
_registry = MetricsRegistry()


def get_registry() -> MetricsRegistry:
    """Get the global metrics registry."""
    return _registry


class MetricsCollector:
    """Helper class for collecting metrics during operations."""

    def __init__(self, server_id: str):
        self.server_id = server_id
        self.registry = get_registry()

    def record_request(self, method: str, status: str, duration: float):
        """Record a completed request."""
        # Increment request counter
        requests = self.registry.get_metric("fluidmcp_requests_total")
        if requests:
            requests.inc({"server_id": self.server_id, "method": method, "status": status})

        # Record duration
        duration_hist = self.registry.get_metric("fluidmcp_request_duration_seconds")
        if duration_hist:
            duration_hist.observe(duration, {"server_id": self.server_id, "method": method})

    def record_error(self, error_type: str):
        """Record an error."""
        errors = self.registry.get_metric("fluidmcp_errors_total")
        if errors:
            errors.inc({"server_id": self.server_id, "error_type": error_type})

    def increment_active_requests(self):
        """Increment active request count."""
        active = self.registry.get_metric("fluidmcp_active_requests")
        if active:
            active.inc({"server_id": self.server_id})

    def decrement_active_requests(self):
        """Decrement active request count."""
        active = self.registry.get_metric("fluidmcp_active_requests")
        if active:
            active.dec({"server_id": self.server_id})

    def set_server_status(self, status_code: int):
        """Set server status code."""
        status = self.registry.get_metric("fluidmcp_server_status")
        if status:
            status.set(status_code, {"server_id": self.server_id})

    def record_restart(self, reason: str):
        """Record a server restart."""
        restarts = self.registry.get_metric("fluidmcp_server_restarts_total")
        if restarts:
            restarts.inc({"server_id": self.server_id, "reason": reason})

    def set_uptime(self, uptime_seconds: float):
        """
        Set server uptime.

        Note: This should be calculated on-demand during metrics export (e.g., from
        server start_time) rather than set once at startup. The server_manager should
        update this metric periodically or compute it dynamically when /metrics is accessed.
        """
        uptime = self.registry.get_metric("fluidmcp_server_uptime_seconds")
        if uptime:
            uptime.set(uptime_seconds, {"server_id": self.server_id})

    def set_gpu_memory(self, gpu_index: int, memory_bytes: float):
        """Set GPU memory usage."""
        gpu_mem = self.registry.get_metric("fluidmcp_gpu_memory_bytes")
        if gpu_mem:
            gpu_mem.set(memory_bytes, {"server_id": self.server_id, "gpu_index": str(gpu_index)})

    def set_gpu_utilization(self, utilization: float):
        """Set GPU memory utilization ratio."""
        gpu_util = self.registry.get_metric("fluidmcp_gpu_memory_utilization_ratio")
        if gpu_util:
            gpu_util.set(utilization, {"server_id": self.server_id})

    def record_tool_call(self, tool_name: str, status: str, duration: float):
        """Record a tool call."""
        # Increment tool call counter
        tool_calls = self.registry.get_metric("fluidmcp_tool_calls_total")
        if tool_calls:
            tool_calls.inc({"server_id": self.server_id, "tool_name": tool_name, "status": status})

        # Record duration
        tool_duration = self.registry.get_metric("fluidmcp_tool_execution_seconds")
        if tool_duration:
            tool_duration.observe(duration, {"server_id": self.server_id, "tool_name": tool_name})

    def record_streaming_request(self, completion_status: str):
        """Record a streaming request."""
        streaming = self.registry.get_metric("fluidmcp_streaming_requests_total")
        if streaming:
            streaming.inc({"server_id": self.server_id, "completion_status": completion_status})

    def increment_active_streams(self):
        """Increment active stream count."""
        streams = self.registry.get_metric("fluidmcp_active_streams")
        if streams:
            streams.inc({"server_id": self.server_id})

    def decrement_active_streams(self):
        """Decrement active stream count."""
        streams = self.registry.get_metric("fluidmcp_active_streams")
        if streams:
            streams.dec({"server_id": self.server_id})


class RequestTimer:
    """Context manager for timing requests."""

    def __init__(self, collector: MetricsCollector, method: str):
        self.collector = collector
        self.method = method
        self.start_time = None
        self.status = "success"

    def __enter__(self):
        self.start_time = time.time()
        self.collector.increment_active_requests()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type is not None:
            self.status = "error"
            # Map exception types to fixed categories to prevent unbounded cardinality
            error_category = self._categorize_error(exc_type)
            self.collector.record_error(error_category)

        self.collector.record_request(self.method, self.status, duration)
        self.collector.decrement_active_requests()

        return False  # Don't suppress exceptions

    @staticmethod
    def _categorize_error(exc_type) -> str:
        """Map exception types to fixed error categories to limit metric cardinality."""
        # Defensive: ensure exc_type is actually an exception class
        try:
            if not isinstance(exc_type, type) or not issubclass(exc_type, BaseException):
                return 'server_error'
        except TypeError:
            # exc_type is not a class
            return 'server_error'

        # Use issubclass for standard exception hierarchy checks (more robust)
        # IMPORTANT: Check specific exceptions before their base classes
        # Python exception hierarchy: BaseException → Exception → OSError → (PermissionError, ConnectionError, etc.)

        # Network errors (TimeoutError and ConnectionError before OSError)
        try:
            if issubclass(exc_type, (TimeoutError, ConnectionError)) and not issubclass(exc_type, BrokenPipeError):
                return 'network_error'
        except TypeError:
            # issubclass() raised TypeError - exc_type is not a valid class
            pass

        # Auth errors (PermissionError before OSError)
        try:
            if issubclass(exc_type, PermissionError):
                return 'auth_error'
        except TypeError:
            # issubclass() raised TypeError - exc_type is not a valid class
            pass

        # I/O errors (OSError and its remaining subclasses)
        try:
            if issubclass(exc_type, (OSError, IOError)):
                return 'io_error'
        except TypeError:
            # issubclass() raised TypeError - exc_type is not a valid class
            pass

        # Client errors (value/type errors)
        try:
            if issubclass(exc_type, (ValueError, TypeError, KeyError, AttributeError)):
                return 'client_error'
        except TypeError:
            # issubclass() raised TypeError - exc_type is not a valid class
            pass

        # Fallback to name-based matching for non-stdlib exceptions
        exc_name = exc_type.__name__

        # HTTP-related exceptions (often from external libraries)
        if exc_name in ('HTTPError', 'RequestException', 'ConnectionTimeout', 'HTTPException'):
            return 'network_error'

        # Auth exceptions from external libraries
        if exc_name in ('AuthenticationError', 'Unauthorized', 'Forbidden'):
            return 'auth_error'

        # Default category for unknown exceptions
        return 'server_error'


class ToolTimer:
    """Context manager for timing tool executions."""

    def __init__(self, collector: MetricsCollector, tool_name: str):
        self.collector = collector
        self.tool_name = tool_name
        self.start_time = None
        self.status = "success"

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type is not None:
            self.status = "error"

        self.collector.record_tool_call(self.tool_name, self.status, duration)

        return False  # Don't suppress exceptions
