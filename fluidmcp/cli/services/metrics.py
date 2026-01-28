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
import math
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
        # Validate value to prevent NaN/Inf corruption
        if not isinstance(value, (int, float)):
            logger.warning(f"Invalid histogram value type: {type(value).__name__}")
            return
        if math.isnan(value):  # Explicit NaN check for clarity
            logger.warning(f"Rejecting NaN value for histogram {self.name}")
            return
        if math.isinf(value):  # Block both +inf and -inf
            logger.warning(f"Rejecting infinite value {value} for histogram {self.name}")
            return
        if value < 0:
            logger.warning(f"Rejecting negative value {value} for histogram {self.name}")
            return

        label_values = label_values or {}
        key = self._get_label_key(label_values)

        with self._lock:
            # Explicitly initialize histogram entry for code clarity (defaultdict would also work)
            if key not in self.histograms:
                self.histograms[key] = {
                    "sum": 0.0,
                    "count": 0,
                    "buckets": {bucket: 0 for bucket in self.buckets}
                }

            hist = self.histograms[key]
            hist["sum"] += value
            hist["count"] += 1

            # Increment ALL buckets >= value (Prometheus histograms are cumulative).
            # A value of 0.15 must increment buckets: 0.25, 0.5, 1.0, 2.5, etc.
            # This ensures correct percentile calculations (P50, P95, P99).
            for bucket in self.buckets:
                if value <= bucket:
                    hist["buckets"][bucket] += 1
                    # Continue to increment all larger buckets (don't break!)

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

                # Emit bucket counts (already cumulative from observe())
                bucket_lines = []
                for bucket in self.buckets:
                    count = hist["buckets"][bucket]
                    labels = f"{base_labels},le=\"{bucket}\"" if base_labels else f"le=\"{bucket}\""
                    bucket_lines.append(f"{self.name}_bucket{{{labels}}} {count}")
                lines.extend(bucket_lines)

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

        # Take a snapshot of metrics under lock to avoid holding the registry lock
        # while rendering each metric (which also acquires its own lock)
        with self._lock:
            metrics_snapshot = sorted(self.metrics.values(), key=lambda m: m.name)

        # Render each metric without holding the registry lock
        for metric in metrics_snapshot:
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
        Set server uptime in seconds.

        Args:
            uptime_seconds: Current server uptime in seconds

        Note:
            As of Round 13, uptime is dynamically calculated on every /metrics request
            by storing server start_time in ServerManager and computing elapsed time.
            This method is called from the /metrics endpoint with the current uptime value.
        """
        uptime = self.registry.get_metric("fluidmcp_server_uptime_seconds")
        if uptime:
            uptime.set(uptime_seconds, {"server_id": self.server_id})

    def set_gpu_memory(self, gpu_index: int, memory_bytes: float):
        """
        Set GPU memory usage in bytes.

        Args:
            gpu_index: GPU device index (0, 1, 2, ...)
            memory_bytes: Memory usage in bytes

        Note: GPU monitoring is opt-in and NOT integrated by default.

        This method provides the metrics infrastructure for GPU monitoring but does not
        automatically collect GPU data. To enable GPU monitoring:
        1. Integrate with a GPU monitoring library (e.g., pynvml, GPUtil)
        2. Call this method periodically or during /metrics export
        3. If not implemented, fluidmcp_gpu_memory_bytes metric will remain empty
           and related dashboard panels will show no data

        The metrics and dashboard are provided as a convenience for users who want
        to add GPU monitoring to their deployment.
        """
        gpu_mem = self.registry.get_metric("fluidmcp_gpu_memory_bytes")
        if gpu_mem:
            gpu_mem.set(memory_bytes, {"server_id": self.server_id, "gpu_index": str(gpu_index)})

    def set_gpu_utilization(self, utilization: float):
        """
        Set GPU memory utilization ratio.

        Args:
            utilization: Utilization ratio between 0.0 (empty) and 1.0 (full)

        Note: GPU monitoring is opt-in and NOT integrated by default.

        This method provides the metrics infrastructure for GPU monitoring but does not
        automatically collect GPU data. To enable GPU monitoring:
        1. Integrate with a GPU monitoring library (e.g., pynvml, GPUtil)
        2. Call this method periodically or during /metrics export
        3. If not implemented, fluidmcp_gpu_memory_utilization_ratio metric will remain
           empty and related dashboard panels/alerts will show no data

        The metrics and dashboard are provided as a convenience for users who want
        to add GPU monitoring to their deployment.
        """
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
        """
        Map exception types to fixed error categories to limit metric cardinality.

        Args:
            exc_type: Exception class (typically from __exit__ context manager)

        Returns:
            Error category string for metrics labeling
        """
        # Defensive: ensure exc_type is actually an exception class
        # Note: While __exit__ guarantees exc_type is None or an exception class,
        # this defensive check protects against:
        # 1. Future refactoring that might call this method from other contexts
        # 2. Potential bugs in calling code
        # 3. Edge cases in exception handling
        # Performance overhead is negligible (single isinstance check).
        # (Discussed and intentionally kept in Round 8 review)
        try:
            if not isinstance(exc_type, type) or not issubclass(exc_type, BaseException):
                return 'server_error'
        except TypeError:
            # exc_type is not a class
            return 'server_error'

        # Use issubclass for standard exception hierarchy checks (more robust)
        # IMPORTANT: Check specific exceptions before their base classes
        # Python exception hierarchy: BaseException → Exception → OSError → (PermissionError, ConnectionError, etc.)
        #
        # NOTE: At this point, exc_type has already been validated as an exception class
        # by the initial check above (lines 527-531), so direct issubclass() checks are safe.
        # No additional try-except blocks needed around individual checks.

        # BrokenPipeError: Explicit check first to clarify intent
        # (subclass of both ConnectionError and OSError, but categorized as io_error)
        if issubclass(exc_type, BrokenPipeError):
            return 'io_error'

        # Network errors (TimeoutError and ConnectionError, but not BrokenPipeError)
        if issubclass(exc_type, (TimeoutError, ConnectionError)):
            return 'network_error'

        # Auth errors (PermissionError before OSError)
        if issubclass(exc_type, PermissionError):
            return 'auth_error'

        # I/O errors (OSError and its remaining subclasses)
        if issubclass(exc_type, OSError):
            return 'io_error'

        # Client errors (value/type errors)
        if issubclass(exc_type, (ValueError, TypeError, KeyError, AttributeError)):
            return 'client_error'

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
    """
    Context manager for timing tool executions.

    This utility is provided for MCP hosts that want per-tool execution metrics.
    It is **not** integrated into the default tool execution path in this
    package, and will only emit metrics if the host application explicitly
    wraps its tool calls with `ToolTimer` (or calls
    `MetricsCollector.record_tool_call` directly).

    When used, the following Prometheus metrics are populated:
      - fluidmcp_tool_calls_total
      - fluidmcp_tool_execution_seconds

    If `ToolTimer` is not wired into your tool invocation code, these metrics
    will remain empty and any associated dashboard panels will show no data.

    Usage example (opt-in integration):
        collector = MetricsCollector("server_id")
        with ToolTimer(collector, "tool_name"):
            # Execute tool code here
            pass
    """

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
